from __future__ import annotations

import asyncio
import json
from threading import Event
from time import sleep

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import pac_poc.beta_api as beta_api_module
from pac_poc.asr import ASREvent
from pac_poc.beta_api import (
    BETA_MODEL,
    BetaAPIDependencies,
    BetaAPISettings,
    CLOUD_PROVIDERS,
    MAX_CHAT_REQUEST_BYTES,
    create_beta_api,
    create_beta_app,
    _run_voice_worker,
    _stream_with_keepalives,
)
from pac_poc.model_gateway import (
    LocalModelRequest,
    ModelGateway,
    LocalOnlyPolicy,
    ProviderStreamChunk,
)
from pac_poc.remote_providers import RemoteProviderError
from pac_poc.security_poc import LocalAPISession


def test_beta_app_factory_and_error_envelope_do_not_echo_invalid_request_values() -> None:
    async def run() -> None:
        app = create_beta_app(
            dependencies=BetaAPIDependencies(session=LocalAPISession(token="factory-token"))
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            denied = await client.post("/chat/stream", json={})
            sentinel = "sk-" + ("x" * 32)
            invalid = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer factory-token"},
                json={"messages": [], "unexpected_secret": sentinel},
            )
        assert denied.status_code == 401
        assert denied.json()["error"]["code"] == "unauthorized"
        assert denied.json()["error"]["trace_id"] == denied.headers["x-trace-id"]
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"
        assert invalid.json()["error"]["trace_id"] == invalid.headers["x-trace-id"]
        assert sentinel not in invalid.text

    asyncio.run(run())


def test_beta_api_settings_only_allow_restrictive_valid_limits() -> None:
    settings = BetaAPISettings(max_context_chars=12_000, max_voice_pcm_bytes=320_000)
    assert settings.max_voice_seconds == 10

    with pytest.raises(ValueError):
        BetaAPISettings(max_context_chars=True)
    with pytest.raises(ValueError):
        BetaAPISettings(max_voice_pcm_bytes=960_001)
    with pytest.raises(ValueError):
        BetaAPISettings(max_voice_pcm_bytes=320_001)
    with pytest.raises(ValueError):
        BetaAPISettings(voice_stream_lock_wait_seconds=float("inf"))
    with pytest.raises(ValueError):
        BetaAPISettings(chat_stream_keepalive_seconds=True)


class StubLocalAdapter:
    is_local = True

    def __init__(self) -> None:
        self.request: LocalModelRequest | None = None

    async def generate(self, request: LocalModelRequest) -> str:
        self.request = request
        return ""

    async def call_with_tools(self, request: LocalModelRequest):
        raise AssertionError("chat endpoint must not invoke tools")

    async def stream(self, request: LocalModelRequest):
        self.request = request
        yield "本机"
        yield "回答"


class DelayedLocalAdapter(StubLocalAdapter):
    async def stream(self, request: LocalModelRequest):
        self.request = request
        await asyncio.sleep(0.04)
        yield "可见回复"


class StubCloudAdapter:
    is_local = False

    def __init__(self) -> None:
        self.request: LocalModelRequest | None = None
        self.calls = 0

    async def generate(self, request: LocalModelRequest) -> str:
        raise AssertionError("stream endpoint must use streaming")

    async def call_with_tools(self, request: LocalModelRequest):
        raise AssertionError("chat endpoint must not invoke tools")

    async def stream(self, request: LocalModelRequest):
        self.calls += 1
        self.request = request
        yield "云端回答"


class FailingCloudAdapter:
    is_local = False

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        self.calls = 0

    async def generate(self, request: LocalModelRequest) -> str:
        raise AssertionError("stream endpoint must use streaming")

    async def call_with_tools(self, request: LocalModelRequest):
        raise AssertionError("chat endpoint must not invoke tools")

    async def stream(self, request: LocalModelRequest):
        self.calls += 1
        if False:
            yield "unreachable"
        response_marker = "synthetic-provider-body-sentinel"
        raise RemoteProviderError(
            f"Provider returned {response_marker}", status_code=self.status_code
        )


class FailingLocalAdapter:
    is_local = True

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LocalModelRequest) -> str:
        raise AssertionError("chat endpoint must use streaming")

    async def call_with_tools(self, request: LocalModelRequest):
        raise AssertionError("chat endpoint must not invoke tools")

    async def stream(self, request: LocalModelRequest):
        self.calls += 1
        if False:
            yield "unreachable"
        raise RuntimeError("private-local-runtime-detail")


class FailingLocalTransportAdapter:
    is_local = True

    def __init__(self, error: httpx.RequestError) -> None:
        self.error = error

    async def generate(self, request: LocalModelRequest) -> str:
        raise AssertionError("chat endpoint must use streaming")

    async def call_with_tools(self, request: LocalModelRequest):
        raise AssertionError("chat endpoint must not invoke tools")

    async def stream(self, request: LocalModelRequest):
        if False:
            yield "unreachable"
        raise self.error


class SpyCredentials:
    def __init__(self) -> None:
        self.reads = 0

    def get(self, account: str) -> str:
        self.reads += 1
        return "synthetic-test-credential"


class StubVoiceTranscriber:
    def __init__(self) -> None:
        self.frames: list[tuple[bytes, int]] = []
        self.started = 0
        self.ended = 0
        self.aborted = 0

    def begin_stream(self) -> None:
        self.started += 1

    def accept_stream_frame(self, pcm: bytes, sequence: int) -> ASREvent:
        self.frames.append((pcm, sequence))
        return ASREvent("partial", "你好", sequence, "rev_partial")

    def end_stream(self, sequence: int) -> ASREvent:
        self.ended += 1
        return ASREvent("final", "你好", sequence, "rev_final")

    def abort_stream(self) -> None:
        self.aborted += 1

    def transcribe_pcm16le(self, pcm: bytes) -> str:
        raise AssertionError("streaming voice route must not use batch transcription")


class SlowCleanupVoiceTranscriber(StubVoiceTranscriber):
    def abort_stream(self) -> None:
        sleep(0.2)
        super().abort_stream()


class QuietVoiceTranscriber(StubVoiceTranscriber):
    def __init__(self) -> None:
        super().__init__()
        self.accepted_sequences: list[int] = []

    def accept_stream_frame(self, pcm: bytes, sequence: int) -> ASREvent | None:
        self.accepted_sequences.append(sequence)
        return None


class UnexpectedFailureVoiceTranscriber(StubVoiceTranscriber):
    def accept_stream_frame(self, pcm: bytes, sequence: int) -> ASREvent:
        raise LookupError("synthetic recognizer failure")


def test_beta_chat_stream_is_authenticated_local_and_non_persistent() -> None:
    async def run() -> None:
        adapter = StubLocalAdapter()
        gateway = ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy())
        app = create_beta_api(session=LocalAPISession(token="test-token"), gateway=gateway)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            denied = await client.post("/chat/stream", json={"messages": [{"role": "user", "content": "你好"}]})
            assert denied.status_code == 401
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer test-token"},
                json={"messages": [{"role": "user", "content": "你好"}]},
            )
            run_id = response.headers["x-pac-run-id"]
            run_status = await client.get(f"/chat/runs/{run_id}", headers={"authorization": "Bearer test-token"})
            usage_denied = await client.get("/usage")
            usage = await client.get("/usage", headers={"authorization": "Bearer test-token"})
        assert response.status_code == 200
        assert '"delta": "本机"' in response.text
        assert '"delta": "回答"' in response.text
        assert '"done":true' in response.text
        assert run_id in response.text
        assert run_status.json()["status"] == "completed"
        assert usage_denied.status_code == 401
        assert usage.json()["retention"] == "process_memory_only"
        assert usage.json()["summary"]["record_count"] == 1
        usage_record = usage.json()["records"][0]
        assert usage_record["run_id"] == run_id
        assert usage_record["status"] == "completed"
        assert usage_record["usage_state"] == "unknown"
        assert usage_record["cost_state"] == "unknown"
        assert usage_record["prompt_tokens"] is None
        assert usage_record["cost_amount"] is None
        assert "你好" not in usage.text
        assert adapter.request is not None
        assert adapter.request.model == BETA_MODEL
        assert adapter.request.provider == "ollama"
        assert adapter.request.messages == [{"role": "user", "content": "你好"}]

    asyncio.run(run())


def test_beta_usage_ledger_records_provider_reported_stream_tokens() -> None:
    class Adapter(StubLocalAdapter):
        async def stream_with_usage(self, request: LocalModelRequest):
            self.request = request
            yield ProviderStreamChunk(text="done")
            yield ProviderStreamChunk(
                prompt_tokens=11, completion_tokens=4, cached_prompt_tokens=5,
                cost_amount=0.00012, cost_currency="USD"
            )

    async def run() -> None:
        gateway = ModelGateway(adapters={"ollama": Adapter()}, policy=LocalOnlyPolicy())
        app = create_beta_api(session=LocalAPISession(token="test-token"), gateway=gateway)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer test-token"},
                json={"messages": [{"role": "user", "content": "count tokens"}]},
            )
            usage = await client.get("/usage", headers={"authorization": "Bearer test-token"})
        assert response.status_code == 200
        assert '"delta": "done"' in response.text
        record = usage.json()["records"][0]
        assert record["prompt_tokens"] == 11
        assert record["completion_tokens"] == 4
        assert record["cached_prompt_tokens"] == 5
        assert record["usage_state"] == "actual"
        assert record["cost_state"] == "actual"
        assert record["cost_amount"] == 0.00012
        assert record["cost_currency"] == "USD"

    asyncio.run(run())


def test_model_capability_endpoint_is_authenticated_and_exact_match_only() -> None:
    async def run() -> None:
        app = create_beta_api(session=LocalAPISession(token="test-token"))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            denied = await client.get(
                "/model-capabilities", params={"provider_id": "ollama", "model_id": "qwen3.5:0.8b"}
            )
            known = await client.get(
                "/model-capabilities",
                headers={"authorization": "Bearer test-token"},
                params={"provider_id": "ollama", "model_id": "qwen3.5:0.8b"},
            )
            unknown = await client.get(
                "/model-capabilities",
                headers={"authorization": "Bearer test-token"},
                params={"provider_id": "ollama", "model_id": "qwen3.5:8b"},
            )
        assert denied.status_code == 401
        report = known.json()
        assert report["verified_at"] == "2026-11-09T00:00:00Z"
        assert report["capabilities"]["streaming"] == "supported"
        assert report["capabilities"]["tools"] == "limited"
        assert unknown.json()["verified_at"] is None
        assert set(unknown.json()["capabilities"].values()) == {"unknown"}

    asyncio.run(run())


def test_user_selected_text_import_is_bounded_ephemeral_and_local_only() -> None:
    async def run() -> None:
        adapter = StubLocalAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
        )
        headers = {"authorization": "Bearer test-token"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            imported = await client.post(
                "/imports/text?filename=notes.md",
                headers={**headers, "content-type": "application/octet-stream"},
                content="项目计划：先完成本机测试版。".encode(),
            )
            import_id = imported.json()["import_id"]
            cloud_blocked = await client.post(
                "/chat/stream",
                headers=headers,
                json={
                    "provider": "deepseek",
                    "model": CLOUD_PROVIDERS["deepseek"].model,
                    "confirmed_for_this_request": True,
                    "import_ids": [import_id],
                    "messages": [{"role": "user", "content": "总结文件"}],
                },
            )
            local = await client.post(
                "/chat/stream",
                headers=headers,
                json={
                    "import_ids": [import_id],
                    "messages": [{"role": "user", "content": "总结文件"}],
                },
            )
            removed = await client.delete(f"/imports/{import_id}", headers=headers)
            missing = await client.post(
                "/chat/stream",
                headers=headers,
                json={
                    "import_ids": [import_id],
                    "messages": [{"role": "user", "content": "再总结"}],
                },
            )

        assert imported.status_code == 201
        assert cloud_blocked.status_code == 403
        assert local.status_code == 200
        assert adapter.request is not None
        assert adapter.request.messages[0]["role"] == "system"
        assert "不可信数据" in adapter.request.messages[0]["content"]
        assert "项目计划：先完成本机测试版。" in adapter.request.messages[-1]["content"]
        assert removed.status_code == 200
        assert missing.status_code == 404

    asyncio.run(run())


def test_text_import_rejects_a_concurrent_upload_before_reading_its_body() -> None:
    async def run() -> None:
        app = create_beta_api(session=LocalAPISession(token="test-token"))
        headers = {
            "authorization": "Bearer test-token",
            "content-type": "application/octet-stream",
        }
        first_chunk_sent = asyncio.Event()
        release_first = asyncio.Event()
        second_body_read = False

        async def first_body():
            yield b"first"
            first_chunk_sent.set()
            await release_first.wait()
            yield b" continued"

        async def second_body():
            nonlocal second_body_read
            second_body_read = True
            yield b"second"

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            first_request = asyncio.create_task(client.post(
                "/imports/text?filename=first.txt", headers=headers, content=first_body()
            ))
            await asyncio.wait_for(first_chunk_sent.wait(), timeout=1)
            try:
                second = await client.post(
                    "/imports/text?filename=second.txt", headers=headers, content=second_body()
                )
            finally:
                release_first.set()
            first = await first_request

        assert second.status_code == 409
        assert not second_body_read
        assert first.status_code == 201
        assert first.json()["byte_count"] == len(b"first continued")

    asyncio.run(run())


def test_user_selected_text_import_rejects_unsupported_or_invalid_files() -> None:
    async def run() -> None:
        app = create_beta_api(session=LocalAPISession(token="test-token"))
        headers = {"authorization": "Bearer test-token", "content-type": "application/octet-stream"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            pdf = await client.post("/imports/text?filename=doc.pdf", headers=headers, content=b"%PDF")
            binary = await client.post("/imports/text?filename=doc.txt", headers=headers, content=b"\xff\x00")
            path = await client.post("/imports/text?filename=../secret.txt", headers=headers, content=b"text")

        assert pdf.status_code == 422
        assert binary.status_code == 422
        assert path.status_code == 422

    asyncio.run(run())


def test_untrusted_document_framing_counts_against_the_context_limit() -> None:
    async def run() -> None:
        adapter = StubLocalAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
            settings=BetaAPISettings(max_context_chars=800),
        )
        headers = {"authorization": "Bearer test-token", "content-type": "application/octet-stream"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            imported = await client.post(
                "/imports/text?filename=quotes.txt",
                headers=headers,
                content=("\"" * 500).encode(),
            )
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer test-token"},
                json={
                    "import_ids": [imported.json()["import_id"]],
                    "messages": [{"role": "user", "content": "Summarize"}],
                },
            )

        assert imported.status_code == 201
        assert response.status_code == 413
        assert adapter.request is None

    asyncio.run(run())


def test_oversized_import_is_rejected_before_orchestrator_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class UnexpectedOrchestrator:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("oversized imported text reached context serialization")

    monkeypatch.setattr(beta_api_module, "MainAssistantOrchestrator", UnexpectedOrchestrator)

    async def run() -> None:
        app = create_beta_api(session=LocalAPISession(token="test-token"))
        headers = {"authorization": "Bearer test-token", "content-type": "application/octet-stream"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            imported = await client.post(
                "/imports/text?filename=large.txt", headers=headers, content=b"x" * 100_000
            )
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer test-token"},
                json={
                    "import_ids": [imported.json()["import_id"]],
                    "messages": [{"role": "user", "content": "Summarize"}],
                },
            )

        assert imported.status_code == 201
        assert response.status_code == 413

    asyncio.run(run())


def test_beta_chat_stream_sends_keepalives_without_exposing_thinking() -> None:
    async def run() -> None:
        adapter = DelayedLocalAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
            settings=BetaAPISettings(chat_stream_keepalive_seconds=0.01),
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer test-token"},
                json={"messages": [{"role": "user", "content": "synthetic local prompt"}]},
            )
        assert response.status_code == 200
        assert ": keep-alive\n\n" in response.text
        assert '"delta": "可见回复"' in response.text
        assert '"thinking"' not in response.text

    asyncio.run(run())


def test_chat_stream_disconnect_cancels_pending_upstream_delta() -> None:
    async def run() -> None:
        upstream_closed = asyncio.Event()

        async def upstream():
            try:
                await asyncio.Event().wait()
                yield "unreachable"
            finally:
                upstream_closed.set()

        stream = _stream_with_keepalives(upstream(), interval_seconds=0.01)
        assert await anext(stream) is None
        await stream.aclose()
        assert upstream_closed.is_set()

    asyncio.run(run())


def test_voice_worker_cancellation_waits_for_blocking_call_to_finish() -> None:
    async def run() -> None:
        worker_started = Event()
        release_worker = Event()

        def blocking_call() -> None:
            worker_started.set()
            release_worker.wait(timeout=2)

        task = asyncio.create_task(_run_voice_worker(blocking_call))
        assert await asyncio.to_thread(worker_started.wait, 1)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release_worker.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())


def test_chat_http_disconnect_marks_run_cancelled_and_closes_upstream() -> None:
    async def run() -> None:
        upstream_started = asyncio.Event()
        upstream_closed = asyncio.Event()
        disconnect = asyncio.Queue()
        response_started = asyncio.Event()
        response_headers: list[tuple[bytes, bytes]] = []

        class BlockingLocalAdapter(StubLocalAdapter):
            async def stream(self, request: LocalModelRequest):
                self.request = request
                upstream_started.set()
                try:
                    await asyncio.Event().wait()
                    yield "unreachable"
                finally:
                    upstream_closed.set()

        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(
                adapters={"ollama": BlockingLocalAdapter()}, policy=LocalOnlyPolicy()
            ),
        )
        body = json.dumps({
            "messages": [{"role": "user", "content": "synthetic disconnect test"}]
        }).encode()
        request_delivered = False

        async def receive():
            nonlocal request_delivered
            if not request_delivered:
                request_delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await disconnect.get()

        async def send(message):
            if message["type"] == "http.response.start":
                response_headers.extend(message["headers"])
                response_started.set()

        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/chat/stream",
            "raw_path": b"/chat/stream",
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"127.0.0.1"),
                (b"authorization", b"Bearer test-token"),
                (b"content-type", b"application/json"),
            ],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 80),
        }

        request_task = asyncio.create_task(app(scope, receive, send))
        await response_started.wait()
        await upstream_started.wait()
        disconnect.put_nowait({"type": "http.disconnect"})
        await request_task

        headers = dict(response_headers)
        run_id = headers[b"x-pac-run-id"].decode()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            auth = {"authorization": "Bearer test-token"}
            run_response = await client.get(f"/chat/runs/{run_id}", headers=auth)
            usage_response = await client.get("/usage?limit=1", headers=auth)

        assert run_response.status_code == 200
        assert run_response.json()["status"] == "cancelled"
        assert usage_response.status_code == 200
        record = usage_response.json()["records"][0]
        assert record["run_id"] == run_id
        assert record["status"] == "cancelled"
        assert upstream_closed.is_set()

    asyncio.run(run())


def test_beta_chat_rejects_oversized_context_and_unknown_fields() -> None:
    async def run() -> None:
        app = create_beta_api(session=LocalAPISession(token="test-token"), gateway=ModelGateway(
            adapters={"ollama": StubLocalAdapter()}, policy=LocalOnlyPolicy()
        ))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            headers = {"authorization": "Bearer test-token"}
            oversized = await client.post(
                "/chat/stream", headers=headers,
                json={"messages": [{"role": "user", "content": "x" * 16_001}]},
            )
            extra = await client.post(
                "/chat/stream", headers=headers,
                json={"messages": [{"role": "user", "content": "hi", "tool": True}]},
            )
        assert oversized.status_code == 422
        assert extra.status_code == 422

    asyncio.run(run())


def test_chat_request_body_limit_applies_to_chunked_requests_without_length() -> None:
    async def run() -> None:
        adapter = StubLocalAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
        )

        async def oversized_chunks():
            yield b" " * MAX_CHAT_REQUEST_BYTES
            yield b" "

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={
                    "authorization": "Bearer test-token",
                    "content-type": "application/json",
                },
                content=oversized_chunks(),
            )

        assert response.status_code == 413
        assert adapter.request is None

    asyncio.run(run())


def test_chat_body_limit_allows_large_valid_unicode_context() -> None:
    async def run() -> None:
        adapter = StubLocalAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
        )
        body = json.dumps(
            {"messages": [{"role": "user", "content": "🙂" * 13_000} for _ in range(3)]}
        ).encode()
        assert len(body) <= MAX_CHAT_REQUEST_BYTES

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={
                    "authorization": "Bearer test-token",
                    "content-type": "application/json",
                },
                content=body,
            )

        assert response.status_code == 200
        assert adapter.request is not None

    asyncio.run(run())


def test_chat_rejects_non_json_content_type_before_reading_body() -> None:
    async def run() -> None:
        app = create_beta_api(session=LocalAPISession(token="test-token"))
        body_read = False

        async def body_chunks():
            nonlocal body_read
            body_read = True
            yield b'{"messages":[]}'

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={
                    "authorization": "Bearer test-token",
                    "content-type": "text/plain",
                },
                content=body_chunks(),
            )

        assert response.status_code == 415
        assert not body_read

    asyncio.run(run())


def test_cloud_chat_requires_one_time_consent_before_adapter_access() -> None:
    async def run() -> None:
        adapter = StubCloudAdapter()
        credentials = SpyCredentials()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            credentials=credentials,
            remote_adapters_override={"deepseek": adapter},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            headers = {"authorization": "Bearer test-token"}
            body = {
                "provider": "deepseek",
                "model": "deepseek-flash",
                "messages": [{"role": "user", "content": "合成测试消息"}],
            }
            denied = await client.post("/chat/stream", headers=headers, json=body)
            assert denied.status_code == 403
            assert adapter.calls == 0
            assert credentials.reads == 0

            sensitive = await client.post(
                "/chat/stream",
                headers=headers,
                json={
                    **body,
                    "messages": [{"role": "user", "content": "sk-" + ("x" * 24)}],
                    "confirmed_for_this_request": True,
                },
            )
            assert sensitive.status_code == 403
            assert adapter.calls == 0
            assert credentials.reads == 0

            allowed = await client.post(
                "/chat/stream",
                headers=headers,
                json={**body, "confirmed_for_this_request": True},
            )
        assert allowed.status_code == 200
        assert '"delta": "云端回答"' in allowed.text
        assert adapter.calls == 1
        assert adapter.request is not None
        assert adapter.request.provider == "deepseek"
        assert adapter.request.model == "deepseek-flash"
        assert adapter.request.region == "china"
        assert adapter.request.purpose == "beta-interactive-chat"
        assert adapter.request.data_level.value == "L2"
        assert credentials.reads == 0

    asyncio.run(run())


@pytest.mark.parametrize(
    ("status_code", "expected_message"),
    [
        (401, "云端 API Key 认证失败"),
        (402, "余额或套餐额度不足"),
        (403, "云端服务拒绝了本次请求"),
        (429, "请求频率受限"),
        (503, "HTTP 503"),
    ],
)
def test_cloud_provider_errors_are_sanitized_and_never_fallback(
    status_code: int, expected_message: str
) -> None:
    adapter = FailingCloudAdapter(status_code)
    app = create_beta_api(
        session=LocalAPISession(token="test-token"),
        remote_adapters_override={"deepseek": adapter},
    )
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            headers={"authorization": "Bearer test-token", "host": "127.0.0.1"},
            json={
                "provider": "deepseek",
                "model": CLOUD_PROVIDERS["deepseek"].model,
                "confirmed_for_this_request": True,
                "messages": [{"role": "user", "content": "synthetic error test"}],
            },
        )
        assert response.status_code == 200, response.text
        run_id = response.headers["x-pac-run-id"]
        run_status = client.get(
            f"/chat/runs/{run_id}",
            headers={"authorization": "Bearer test-token", "host": "127.0.0.1"},
        )

    assert response.status_code == 200
    assert expected_message in response.text
    assert "synthetic-provider-body-sentinel" not in response.text
    assert adapter.calls == 1
    assert run_status.json()["status"] == "failed"


def test_local_model_error_is_sanitized_and_recorded_as_unknown_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Simulate a wall-clock adjustment before the event stream records usage.
    monkeypatch.setattr(beta_api_module, "time", lambda: 0.0)
    adapter = FailingLocalAdapter()
    gateway = ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy())
    app = create_beta_api(
        session=LocalAPISession(token="test-token"),
        gateway=gateway,
    )
    headers = {"authorization": "Bearer test-token", "host": "127.0.0.1"}
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            headers=headers,
            json={
                "provider": "ollama",
                "model": BETA_MODEL,
                "messages": [{"role": "user", "content": "synthetic local error test"}],
            },
        )
        usage_response = client.get("/usage", headers=headers)

    assert response.status_code == 200
    assert "本机模型请求失败，请确认 Ollama 正在运行且模型已安装" in response.text
    assert "private-local-runtime-detail" not in response.text
    assert adapter.calls == 1
    record = usage_response.json()["records"][0]
    assert record["status"] == "failed"
    assert record["usage_state"] == "unknown"
    assert record["cost_state"] == "unknown"
    assert record["completed_at"] >= record["started_at"]


@pytest.mark.parametrize(
    ("error_type", "expected_message"),
    [
        (httpx.ConnectError, "无法连接本机 Ollama"),
        (httpx.ReadTimeout, "等待本机 Ollama 响应超时"),
    ],
)
def test_local_transport_errors_use_local_recovery_guidance(
    error_type: type[httpx.RequestError], expected_message: str
) -> None:
    request = httpx.Request("POST", "http://127.0.0.1:11434/api/chat")
    adapter = FailingLocalTransportAdapter(error_type("synthetic transport marker", request=request))
    app = create_beta_api(
        session=LocalAPISession(token="test-token"),
        gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
    )
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            headers={"authorization": "Bearer test-token", "host": "127.0.0.1"},
            json={
                "provider": "ollama",
                "model": BETA_MODEL,
                "messages": [{"role": "user", "content": "synthetic transport error test"}],
            },
        )

    assert response.status_code == 200
    assert expected_message in response.text
    assert "云端" not in response.text
    assert "synthetic transport marker" not in response.text


def test_qwen_application_route_is_available_with_exact_region_and_model() -> None:
    async def run() -> None:
        adapter = StubCloudAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            remote_adapters_override={"qwen-app": adapter},
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer test-token"},
                json={
                    "provider": "qwen-app",
                    "model": "qwen3.8-flash",
                    "confirmed_for_this_request": True,
                    "messages": [{"role": "user", "content": "synthetic"}],
                },
            )
        assert response.status_code == 200
        assert adapter.request is not None
        assert adapter.request.provider == "qwen-app"
        assert adapter.request.model == "qwen3.8-flash"
        assert adapter.request.region == "china"
        assert adapter.request.data_level.value == "L2"

    asyncio.run(run())


def test_authenticated_voice_websocket_streams_partial_then_final() -> None:
    transcriber = SlowCleanupVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            pcm = b"\x01\x00" * 3_200
            websocket.send_bytes((0).to_bytes(4, "big") + pcm)
            partial = websocket.receive_json()
            assert partial == {
                "type": "partial",
                "text": "你好",
                "sequence": 0,
                "revision_id": "rev_partial",
            }
            websocket.send_json({"type": "end"})
            final = websocket.receive_json()
            assert final["type"] == "final"
            assert final["text"] == "你好"
            assert websocket.receive_json() == {"type": "ended"}

        # The completion event must only arrive after the single-session ASR lock
        # has been released, so an immediate next recording can reconnect.
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_json({"type": "end"})
            assert websocket.receive_json()["type"] == "final"
            assert websocket.receive_json() == {"type": "ended"}

    assert transcriber.started == 2
    assert transcriber.frames == [(pcm, 0)]
    assert transcriber.ended == 2
    assert transcriber.aborted == 2


def test_voice_transcribe_bounds_chunked_body_before_batch_asr() -> None:
    class BatchVoiceTranscriber(StubVoiceTranscriber):
        def __init__(self) -> None:
            super().__init__()
            self.transcribed: list[bytes] = []

        def transcribe_pcm16le(self, pcm: bytes) -> str:
            self.transcribed.append(pcm)
            return "recognized"

    async def run() -> None:
        transcriber = BatchVoiceTranscriber()
        app = create_beta_api(
            session=LocalAPISession(token="voice-token"),
            voice_transcriber_override=transcriber,
            settings=BetaAPISettings(max_voice_pcm_bytes=32_000),
        )

        async def valid_chunks():
            yield b"\x00" * 16_000
            yield b"\x00" * 16_000

        async def oversized_chunks():
            yield b"\x00" * 32_000
            yield b"\x00\x00"

        headers = {
            "authorization": "Bearer voice-token",
            "content-type": "application/octet-stream",
        }
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            valid = await client.post("/voice/transcribe", headers=headers, content=valid_chunks())
            oversized = await client.post(
                "/voice/transcribe", headers=headers, content=oversized_chunks()
            )

        assert valid.status_code == 200
        assert valid.json() == {"text": "recognized"}
        assert oversized.status_code == 413
        assert transcriber.transcribed == [b"\x00" * 32_000]

    asyncio.run(run())


def test_concurrent_batch_voice_request_fails_when_asr_session_is_busy() -> None:
    class BlockingBatchVoiceTranscriber(StubVoiceTranscriber):
        def __init__(self) -> None:
            super().__init__()
            self.started = Event()
            self.release = Event()

        def transcribe_pcm16le(self, pcm: bytes) -> str:
            self.started.set()
            self.release.wait(timeout=2)
            return "recognized"

    async def run() -> None:
        transcriber = BlockingBatchVoiceTranscriber()
        app = create_beta_api(
            session=LocalAPISession(token="voice-token"),
            voice_transcriber_override=transcriber,
            settings=BetaAPISettings(
                max_voice_pcm_bytes=32_000,
                voice_stream_lock_wait_seconds=0.02,
            ),
        )
        headers = {
            "authorization": "Bearer voice-token",
            "content-type": "application/octet-stream",
        }

        async def audio_chunks():
            yield b"\x00" * 32_000

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            first_task = asyncio.create_task(
                client.post("/voice/transcribe", headers=headers, content=audio_chunks())
            )
            assert await asyncio.to_thread(transcriber.started.wait, 1)
            second = await client.post(
                "/voice/transcribe", headers=headers, content=audio_chunks()
            )
            transcriber.release.set()
            first = await first_task

        assert first.status_code == 200
        assert second.status_code == 409

    asyncio.run(run())


def test_voice_websocket_reports_busy_after_authenticated_handshake() -> None:
    transcriber = StubVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as active:
            active.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert active.receive_json() == {"type": "ready"}

            with client.websocket_connect(
                "/voice/stream",
                headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
            ) as busy:
                busy.send_json({
                    "type": "start",
                    "sample_rate_hz": 16_000,
                    "channels": 1,
                    "encoding": "pcm_s16le",
                    "frame_duration_ms": 200,
                })
                error = busy.receive_json()
                assert error == {
                    "type": "error",
                    "message": "本机语音识别正忙，请稍后重试；音频未发送到云端",
                }

            active.send_json({"type": "end"})
            assert active.receive_json()["type"] == "final"
            assert active.receive_json() == {"type": "ended"}

    assert transcriber.started == 1
    assert transcriber.ended == 1
    assert transcriber.aborted == 1


def test_voice_websocket_abort_clears_session_and_allows_immediate_restart() -> None:
    transcriber = StubVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_json({"type": "abort"})
            assert websocket.receive_json() == {"type": "ended"}

        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_json({"type": "end"})
            assert websocket.receive_json()["type"] == "final"
            assert websocket.receive_json() == {"type": "ended"}

    assert transcriber.started == 2
    assert transcriber.ended == 1
    assert transcriber.aborted == 2


def test_voice_websocket_reports_unexpected_asr_failure_and_releases_session() -> None:
    transcriber = UnexpectedFailureVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_bytes((0).to_bytes(4, "big") + b"\x01\x00" * 3_200)
            error = websocket.receive_json()
            assert error == {
                "type": "error",
                "message": "本机语音识别发生内部错误（LookupError）；音频未发送到云端",
            }

        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_json({"type": "abort"})
            assert websocket.receive_json() == {"type": "ended"}

    assert transcriber.started == 2
    assert transcriber.aborted == 2


def test_voice_websocket_rejects_bad_token_and_out_of_order_frames() -> None:
    transcriber = StubVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/voice/stream",
                headers={"authorization": "Bearer wrong-token", "host": "127.0.0.1"},
            ):
                pass

        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_bytes((1).to_bytes(4, "big") + b"\x00\x00" * 3_200)
            error = websocket.receive_json()
            assert error == {"type": "error", "message": "音频帧格式或序号无效"}

    assert transcriber.started == 1
    assert transcriber.frames == []
    assert transcriber.aborted == 1


def test_voice_websocket_caps_stream_at_thirty_seconds() -> None:
    transcriber = QuietVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            pcm_200ms = b"\x00\x00" * 3_200
            for sequence in range(150):
                websocket.send_bytes(sequence.to_bytes(4, "big") + pcm_200ms)
            websocket.send_bytes((150).to_bytes(4, "big") + b"\x00\x00")
            assert websocket.receive_json() == {
                "type": "error",
                "message": "录音超过 30 秒上限",
            }

    assert transcriber.accepted_sequences == list(range(150))
    assert transcriber.aborted == 1


def test_voice_websocket_disconnect_aborts_and_clears_stream() -> None:
    transcriber = StubVoiceTranscriber()
    app = create_beta_api(
        session=LocalAPISession(token="voice-token"),
        voice_transcriber_override=transcriber,
    )
    with TestClient(app) as client:
        with client.websocket_connect(
            "/voice/stream",
            headers={"authorization": "Bearer voice-token", "host": "127.0.0.1"},
        ) as websocket:
            websocket.send_json({
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            })
            assert websocket.receive_json() == {"type": "ready"}
            websocket.send_bytes((0).to_bytes(4, "big") + b"\x00\x00" * 3_200)
            assert websocket.receive_json()["type"] == "partial"
            websocket.close()

    assert transcriber.ended == 0
    assert transcriber.aborted == 1


def test_persistent_chat_history_round_trips_and_can_be_manually_deleted(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    store = EncryptedApplicationStore(path=(tmp_path / "history.db").resolve(), key=b"h" * 32)
    store.open()
    adapter = StubLocalAdapter()
    app = create_beta_api(
        session=LocalAPISession(token="history-token"),
        gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        headers = {"authorization": "Bearer history-token"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            initial = await client.get("/chat/history", headers=headers)
            conversation_id = initial.json()["conversation_id"]
            response = await client.post(
                "/chat/stream",
                headers=headers,
                json={
                    "conversation_id": conversation_id,
                    "messages": [{"role": "user", "content": "记住项目标题"}],
                },
            )
            history = await client.get("/chat/history", headers=headers)
            deleted = await client.delete("/chat/history", headers=headers)
            after_delete = await client.get("/chat/history", headers=headers)
        assert initial.status_code == 200
        assert response.status_code == 200
        assert '"done":true' in response.text
        assert history.json()["messages"] == [
            {"role": "user", "content": "记住项目标题"},
            {"role": "assistant", "content": "本机回答"},
        ]
        assert deleted.json() == {"deleted": True}
        assert after_delete.json()["messages"] == []

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_persistent_task_api_enforces_transitions_and_requires_storage(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    app_without_storage = create_beta_api(session=LocalAPISession(token="no-tasks-token"))
    store = EncryptedApplicationStore(path=(tmp_path / "tasks.db").resolve(), key=b"t" * 32)
    store.open()
    app = create_beta_api(
        session=LocalAPISession(token="task-token"), persistence_store=store
    )

    async def run() -> None:
        headers = {"authorization": "Bearer task-token"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app_without_storage), base_url="http://127.0.0.1"
        ) as no_store_client:
            assert (await no_store_client.get("/tasks", headers={"authorization": "Bearer no-tasks-token"})).status_code == 503
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            created = await client.post("/tasks", headers=headers, json={
                "title": "Read calendar", "priority": 2,
                "idempotency_key": "33333333-3333-4333-8333-333333333333",
            })
            task = created.json()
            ready = await client.patch(f"/tasks/{task['id']}/status", headers=headers, json={"status": "READY"})
            invalid = await client.patch(f"/tasks/{task['id']}/status", headers=headers, json={"status": "COMPLETED"})
            listed = await client.get("/tasks", headers=headers)
            deleted = await client.delete(f"/tasks/{task['id']}", headers=headers)
        assert created.status_code == 201
        assert ready.json()["status"] == "READY"
        assert invalid.status_code == 409
        assert len(listed.json()["tasks"]) == 1
        assert deleted.json() == {"deleted": True}

    try:
        asyncio.run(run())
    finally:
        store.close()
