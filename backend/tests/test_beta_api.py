from __future__ import annotations

import asyncio
import json
from pathlib import Path
from threading import Event
from time import sleep
from uuid import UUID, uuid4

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
    _retention_cleanup_loop,
    _run_voice_worker,
    _stream_with_keepalives,
)
from pac_poc.model_gateway import (
    LocalModelRequest,
    ModelGateway,
    LocalOnlyPolicy,
    ProviderStreamChunk,
)
from pac_poc.persistence import EncryptedApplicationStore
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


def test_chat_rejects_unregistered_assistant_profile() -> None:
    async def run() -> None:
        app = create_beta_app(
            dependencies=BetaAPIDependencies(session=LocalAPISession(token="profile-token"))
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/chat/stream",
                headers={"authorization": "Bearer profile-token"},
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "assistant_key": "arbitrary_agent",
                },
            )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

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
            def __init__(self) -> None:
                super().__init__()
                self.calls = 0

            async def stream(self, request: LocalModelRequest):
                self.request = request
                self.calls += 1
                upstream_started.set()
                try:
                    await asyncio.Event().wait()
                    yield "unreachable"
                finally:
                    upstream_closed.set()

        adapter = BlockingLocalAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            gateway=ModelGateway(
                adapters={"ollama": adapter}, policy=LocalOnlyPolicy()
            ),
        )
        body = json.dumps({
            "messages": [{"role": "user", "content": "synthetic disconnect test"}],
            "collaborator_keys": ["project_assistant", "meeting_assistant"],
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
        assert adapter.calls == 1

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


def test_cloud_chat_requires_one_time_consent_before_adapter_access(tmp_path: Path) -> None:
    store = EncryptedApplicationStore(
        path=(tmp_path / "cloud-budget-consent.db").resolve(), key=b"b" * 32
    )
    store.open()

    async def run() -> None:
        adapter = StubCloudAdapter()
        credentials = SpyCredentials()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            credentials=credentials,
            remote_adapters_override={"deepseek": adapter},
            persistence_store=store,
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
            usage = await client.get("/usage", headers=headers)
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
        assert usage.json()["budget"]["is_estimate"] is True
        assert usage.json()["budget"]["estimated_spent_cny"] > 0
        events = usage.json()["audit_events"]
        assert [event["decision"] for event in events[:2]] == ["SUCCEEDED", "ATTEMPTED"]
        assert all(event["provider_id"] == "deepseek" for event in events)
        assert all(event["data_sensitivity"] == "L2" for event in events)
        assert "合成测试消息" not in json.dumps(events, ensure_ascii=False)
        assert "sk-" not in json.dumps(events, ensure_ascii=False)
        assert usage.json()["audit_retention"] == "encrypted_metadata_30_days"
        assert {event["reason_code"] for event in events} >= {
            "user_confirmation_missing", "secret_pattern_blocked"
        }

    asyncio.run(run())
    store.close()


def test_cloud_budget_blocks_at_monthly_limit_before_adapter_access(tmp_path: Path) -> None:
    store = EncryptedApplicationStore(
        path=(tmp_path / "cloud-budget-limit.db").resolve(), key=b"l" * 32
    )
    store.open()
    store.add_monthly_cloud_budget_estimate(
        beta_api_module._budget_month_key(), amount_micros=100_000_000,
        price_version="2026-11-10",
    )
    adapter = StubCloudAdapter()
    app = create_beta_api(
        session=LocalAPISession(token="budget-token"),
        remote_adapters_override={"deepseek": adapter},
        persistence_store=store,
    )
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            headers={"authorization": "Bearer budget-token", "host": "127.0.0.1"},
            json={
                "provider": "deepseek",
                "model": "deepseek-flash",
                "confirmed_for_this_request": True,
                "messages": [{"role": "user", "content": "synthetic budget limit"}],
            },
        )
        usage = client.get(
            "/usage", headers={"authorization": "Bearer budget-token", "host": "127.0.0.1"}
        )
    assert response.status_code == 429
    assert "估算" in response.json()["detail"]
    assert adapter.calls == 0
    assert usage.json()["budget"]["blocked"] is True
    assert usage.json()["budget"]["warning_reached"] is True
    assert usage.json()["audit_events"][0]["decision"] == "DENIED"
    assert usage.json()["audit_events"][0]["reason_code"] == "monthly_budget_limit"
    store.close()


def test_cloud_context_limit_rejection_is_audited_before_provider_access(tmp_path: Path) -> None:
    store = EncryptedApplicationStore(
        path=(tmp_path / "cloud-context-audit.db").resolve(), key=b"c" * 32
    )
    store.open()
    adapter = StubCloudAdapter()
    app = create_beta_api(
        session=LocalAPISession(token="context-token"),
        remote_adapters_override={"deepseek": adapter},
        persistence_store=store,
        settings=BetaAPISettings(max_context_chars=800),
    )

    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            headers={"authorization": "Bearer context-token", "host": "127.0.0.1"},
            json={
                "provider": "deepseek",
                "model": "deepseek-flash",
                "confirmed_for_this_request": True,
                "messages": [{"role": "user", "content": "x" * 900}],
            },
        )
        usage = client.get(
            "/usage", headers={"authorization": "Bearer context-token", "host": "127.0.0.1"}
        )

    assert response.status_code == 413
    assert adapter.calls == 0
    assert [event["reason_code"] for event in usage.json()["audit_events"]] == [
        "context_limit_exceeded"
    ]
    store.close()


def test_calendar_event_audit_is_metadata_only_and_status_scoped(tmp_path: Path) -> None:
    store = EncryptedApplicationStore(
        path=(tmp_path / "calendar-event-audit.db").resolve(), key=b"a" * 32
    )
    store.open()
    app = create_beta_api(
        session=LocalAPISession(token="calendar-audit-token"), persistence_store=store
    )
    headers = {
        "authorization": "Bearer calendar-audit-token",
        "host": "127.0.0.1",
    }
    trace_id = str(uuid4())
    resource_id = str(uuid4())
    with TestClient(app) as client:
        unauthenticated = client.post(
            "/security-audit/calendar-event",
            headers={"host": "127.0.0.1"},
            json={"trace_id": trace_id, "resource_id": resource_id,
                  "decision": "ATTEMPTED", "reason_code": "user_approved"},
        )
        denied = client.post(
            "/security-audit/calendar-event",
            headers=headers,
            json={"trace_id": trace_id, "resource_id": resource_id,
                  "decision": "SUCCEEDED", "reason_code": "user_approved"},
        )
        attempted = client.post(
            "/security-audit/calendar-event",
            headers=headers,
            json={"trace_id": trace_id, "resource_id": resource_id,
                  "decision": "ATTEMPTED", "reason_code": "user_approved"},
        )
        succeeded = client.post(
            "/security-audit/calendar-event",
            headers=headers,
            json={"trace_id": trace_id, "resource_id": resource_id,
                  "decision": "SUCCEEDED", "reason_code": "event_created"},
        )
        failed = client.post(
            "/security-audit/calendar-event",
            headers=headers,
            json={"trace_id": trace_id, "resource_id": resource_id,
                  "decision": "FAILED", "reason_code": "audit_finalization_failed"},
        )
        usage = client.get("/usage", headers=headers)

    assert unauthenticated.status_code == 401
    assert denied.status_code == 422
    assert attempted.status_code == 201 and attempted.json() == {"recorded": True}
    assert succeeded.status_code == 201
    assert failed.status_code == 201
    events = usage.json()["audit_events"]
    assert [event["decision"] for event in events[:3]] == ["FAILED", "SUCCEEDED", "ATTEMPTED"]
    assert events[0]["reason_code"] == "audit_finalization_failed"
    assert all(event["action"] == "calendar_event_create" for event in events)
    assert all(event["provider_id"] == "eventkit" for event in events)
    assert all(event["data_sensitivity"] == "L2" for event in events)
    assert not any("title" in event or "start" in event or "notes" in event for event in events)
    store.close()


def test_completed_task_and_security_audit_retention_cleanup_runs_periodically() -> None:
    class StoreStub:
        task_purges = 0
        audit_purges = 0

        def purge_expired_completed_tasks(self) -> int:
            self.task_purges += 1
            return 0

        def purge_expired_security_audit_events(self) -> int:
            self.audit_purges += 1
            return 0

    async def run() -> None:
        store = StoreStub()
        waits = 0

        async def controlled_sleep(delay_seconds: float) -> None:
            nonlocal waits
            assert delay_seconds == 6 * 60 * 60
            waits += 1
            if waits == 2:
                raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await _retention_cleanup_loop(store, sleep=controlled_sleep)
        assert waits == 2
        assert store.task_purges == store.audit_purges == 1

    asyncio.run(run())


def test_database_key_app_factory_purges_expired_completed_tasks_on_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    database_path = tmp_path / "startup-retention.db"
    monkeypatch.setattr(beta_api_module, "default_database_path", lambda: database_path)
    seed_store = EncryptedApplicationStore(path=database_path, key=b"t" * 32)
    seed_store.open()
    now = datetime.now(timezone.utc)
    with seed_store.connection() as connection, connection.begin():
        for task_id, completed_at in (
            ("startup-expired-task", now - timedelta(days=31)),
            ("startup-recent-task", now - timedelta(days=29)),
        ):
            timestamp = completed_at.isoformat()
            connection.execute(
                text(
                    "INSERT INTO tasks(id,title,status,priority,retry_count,idempotency_key,"
                    "created_at,updated_at,started_at,completed_at) "
                    "VALUES(:id,:id,'COMPLETED',0,0,:key,:time,:time,:time,:time)"
                ),
                {"id": task_id, "key": f"{task_id}-key", "time": timestamp},
            )
    seed_store.close()

    app = create_beta_app(
        dependencies=BetaAPIDependencies(
            session=LocalAPISession(token="startup-retention-token"),
            database_key=b"t" * 32,
        )
    )
    with TestClient(app):
        store = EncryptedApplicationStore(path=database_path, key=b"t" * 32)
        store.open()
        try:
            remaining_ids = {task["id"] for task in store.list_tasks()}
            assert remaining_ids == {"startup-recent-task"}
        finally:
            store.close()


def test_database_key_app_starts_and_stops_audit_maintenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = Event()
    stopped = Event()
    monkeypatch.setattr(
        beta_api_module, "default_database_path", lambda: tmp_path / "maintenance.db"
    )

    async def wait_for_shutdown(_store: object) -> None:
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()

    monkeypatch.setattr(beta_api_module, "_retention_cleanup_loop", wait_for_shutdown)
    app = create_beta_app(
        dependencies=BetaAPIDependencies(
            session=LocalAPISession(token="maintenance-token"), database_key=b"m" * 32
        )
    )

    with TestClient(app):
        assert started.wait(timeout=5)
    assert stopped.wait(timeout=5)


def test_usage_snapshot_includes_in_flight_cloud_budget_reservations(tmp_path: Path) -> None:
    store = EncryptedApplicationStore(
        path=(tmp_path / "cloud-budget-reservation-summary.db").resolve(), key=b"r" * 32
    )
    store.open()
    store.reserve_monthly_cloud_budget(
        beta_api_module._budget_month_key(),
        reservation_id="usage-summary-reservation",
        amount_micros=85_000_000,
        limit_micros=100_000_000,
        expires_at="2999-01-01T00:00:00+00:00",
    )
    app = create_beta_api(
        session=LocalAPISession(token="budget-summary-token"), persistence_store=store
    )
    with TestClient(app) as client:
        response = client.get(
            "/usage",
            headers={"authorization": "Bearer budget-summary-token", "host": "127.0.0.1"},
        )
    assert response.status_code == 200
    budget = response.json()["budget"]
    assert budget["estimated_spent_cny"] == 0
    assert budget["estimated_in_flight_cny"] == 85
    assert budget["estimated_projected_cny"] == 85
    assert budget["warning_reached"] is True
    assert budget["blocked"] is False
    store.close()


def test_cloud_request_fails_closed_without_encrypted_budget_storage() -> None:
    adapter = StubCloudAdapter()
    app = create_beta_api(
        session=LocalAPISession(token="missing-budget-token"),
        remote_adapters_override={"deepseek": adapter},
    )
    with TestClient(app) as client:
        response = client.post(
            "/chat/stream",
            headers={
                "authorization": "Bearer missing-budget-token",
                "host": "127.0.0.1",
            },
            json={
                "provider": "deepseek",
                "model": "deepseek-flash",
                "confirmed_for_this_request": True,
                "messages": [{"role": "user", "content": "synthetic budget storage test"}],
            },
        )
    assert response.status_code == 503
    assert "budget storage" in response.json()["detail"]
    assert adapter.calls == 0


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
    status_code: int, expected_message: str, tmp_path: Path
) -> None:
    adapter = FailingCloudAdapter(status_code)
    store = EncryptedApplicationStore(
        path=(tmp_path / f"cloud-error-{status_code}.db").resolve(), key=b"e" * 32
    )
    store.open()
    app = create_beta_api(
        session=LocalAPISession(token="test-token"),
        remote_adapters_override={"deepseek": adapter},
        persistence_store=store,
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
    store.close()


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


def test_qwen_application_route_is_available_with_exact_region_and_model(tmp_path: Path) -> None:
    store = EncryptedApplicationStore(
        path=(tmp_path / "qwen-budget.db").resolve(), key=b"q" * 32
    )
    store.open()

    async def run() -> None:
        adapter = StubCloudAdapter()
        app = create_beta_api(
            session=LocalAPISession(token="test-token"),
            remote_adapters_override={"qwen-app": adapter},
            persistence_store=store,
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
    store.close()


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
            source_id = history.json()["messages"][0]["id"]
            memory = await client.post("/memories", headers=headers, json={
                "subject": "Project title", "content": "Project Atlas",
                "category": "fact", "confirmed": True, "source_message_id": source_id,
            })
            source = await client.get(f"/memories/{memory.json()['id']}/source", headers=headers)
            deleted = await client.delete("/chat/history", headers=headers)
            after_delete = await client.get("/chat/history", headers=headers)
            memories = await client.get("/memories", headers=headers)
            source_after_delete = await client.get(
                f"/memories/{memory.json()['id']}/source", headers=headers
            )
        assert initial.status_code == 200
        assert response.status_code == 200
        assert '"done":true' in response.text
        assert [
            {"role": message["role"], "content": message["content"]}
            for message in history.json()["messages"]
        ] == [
            {"role": "user", "content": "记住项目标题"},
            {"role": "assistant", "content": "本机回答"},
        ]
        assert all(UUID(message["id"]) for message in history.json()["messages"])
        assert memory.status_code == 201
        assert memory.json()["source_message_id"] == source_id
        assert source.json()["source"]["content"] == "记住项目标题"
        assert source.json()["source"]["conversation_id"] == conversation_id
        assert deleted.json() == {"deleted": True}
        assert after_delete.json()["messages"] == []
        assert memories.json()["memories"][0]["source_message_id"] is None
        assert source_after_delete.json()["source"] is None

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_confirmed_memory_can_reference_message_from_another_conversation(tmp_path) -> None:
    store = EncryptedApplicationStore(path=(tmp_path / "cross-conversation-memory.db").resolve(), key=b"x" * 32)
    store.open()
    first = store.get_or_create_default_conversation()
    second = store.create_conversation(title="另一个本机会话")
    store.append_chat_turn(
        conversation_id=str(first["id"]), run_id=str(uuid4()), user_content="第一会话内容",
        assistant_content="第一会话回答", provider="ollama", model="local", status="COMPLETED",
    )
    store.append_chat_turn(
        conversation_id=str(second["id"]), run_id=str(uuid4()), user_content="跨会话来源内容",
        assistant_content="第二会话回答", provider="ollama", model="local", status="COMPLETED",
    )
    source_message_id = store.load_conversation(str(second["id"]))["messages"][0]["id"]
    app = create_beta_api(
        session=LocalAPISession(token="cross-memory-token"),
        gateway=ModelGateway(adapters={"ollama": StubLocalAdapter()}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            response = await client.post(
                "/memories",
                headers={"authorization": "Bearer cross-memory-token"},
                json={
                    "subject": "第二会话来源", "content": "已确认内容", "category": "fact",
                    "confirmed": True, "source_message_id": source_message_id,
                },
            )
            source = await client.get(
                f"/memories/{response.json()['id']}/source",
                headers={"authorization": "Bearer cross-memory-token"},
            )
        assert response.status_code == 201
        assert source.json()["source"]["conversation_id"] == second["id"]
        assert source.json()["source"]["conversation_title"] == "另一个本机会话"
        assert source.json()["source"]["content"] == "跨会话来源内容"

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_chat_history_api_returns_bounded_keyset_pages(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    store = EncryptedApplicationStore(path=(tmp_path / "history-pages.db").resolve(), key=b"p" * 32)
    store.open()
    conversation = store.get_or_create_default_conversation()
    for number in range(3):
        store.append_chat_turn(
            conversation_id=str(conversation["id"]), run_id=f"history-page-{number}",
            user_content=f"user-{number}", assistant_content=f"assistant-{number}",
            provider="ollama", model="fixture", status="COMPLETED",
        )
    app = create_beta_api(
        session=LocalAPISession(token="history-page-token"),
        gateway=ModelGateway(adapters={"ollama": StubLocalAdapter()}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            headers = {"authorization": "Bearer history-page-token"}
            latest = await client.get(
                "/chat/history", headers=headers,
                params={"conversation_id": conversation["id"], "limit": 3},
            )
            older = await client.get(
                "/chat/history", headers=headers,
                params={
                    "conversation_id": conversation["id"], "limit": 3,
                    "before_message_id": latest.json()["messages"][0]["id"],
                },
            )
        assert latest.status_code == older.status_code == 200
        assert [message["content"] for message in latest.json()["messages"]] == [
            "assistant-1", "user-2", "assistant-2",
        ]
        assert latest.json()["has_more"] is True
        assert [message["content"] for message in older.json()["messages"]] == [
            "user-0", "assistant-0", "user-1",
        ]
        assert older.json()["has_more"] is False

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_persistent_task_api_enforces_transitions_and_requires_storage(tmp_path) -> None:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import text

    from pac_poc.persistence import EncryptedApplicationStore

    app_without_storage = create_beta_api(session=LocalAPISession(token="no-tasks-token"))
    store = EncryptedApplicationStore(path=(tmp_path / "tasks.db").resolve(), key=b"t" * 32)
    store.open()
    app = create_beta_api(
        session=LocalAPISession(token="task-token"), persistence_store=store
    )
    cleanup_now = datetime.now(timezone.utc)
    seeded_tasks = [
        ("api-expired-task", cleanup_now - timedelta(days=31)),
        ("api-recent-task", cleanup_now - timedelta(days=29)),
    ]
    stored_ids_after_listing: set[str] = set()
    with store.connection() as connection, connection.begin():
        for task_id, completed_at in seeded_tasks:
            timestamp = completed_at.isoformat()
            connection.execute(text(
                "INSERT INTO tasks(id,title,status,priority,retry_count,idempotency_key,"
                "created_at,updated_at,started_at,completed_at) "
                "VALUES(:id,:id,'COMPLETED',0,0,:key,:time,:time,:time,:time)"
            ), {"id": task_id, "key": f"{task_id}-key", "time": timestamp})

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
                "schedule_at": "2026-11-11T10:30:00+08:00",
                "idempotency_key": "33333333-3333-4333-8333-333333333333",
            })
            task = created.json()
            ready = await client.patch(f"/tasks/{task['id']}/status", headers=headers, json={"status": "READY"})
            invalid = await client.patch(f"/tasks/{task['id']}/status", headers=headers, json={"status": "COMPLETED"})
            listed = await client.get("/tasks", headers=headers)
            stored_ids_after_listing.update(item["id"] for item in store.list_tasks())
            deleted = await client.delete(f"/tasks/{task['id']}", headers=headers)
        assert created.status_code == 201
        assert created.json()["schedule_at"] == "2026-11-11T10:30:00+08:00"
        assert task["allowed_transitions"] == ["CANCELLED", "READY"]
        assert ready.json()["status"] == "READY"
        assert ready.json()["allowed_transitions"] == ["CANCELLED", "PAUSED", "RUNNING"]
        assert invalid.status_code == 409
        listed_ids = {item["id"] for item in listed.json()["tasks"]}
        assert listed_ids == {task["id"], "api-recent-task"}
        assert stored_ids_after_listing == listed_ids
        assert deleted.json() == {"deleted": True}

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_skills_api_returns_fixed_local_catalog_and_chat_applies_explicit_selection(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    store = EncryptedApplicationStore(path=(tmp_path / "skills.db").resolve(), key=b"s" * 32)
    store.open()
    adapter = StubLocalAdapter()
    gateway = ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy())
    app = create_beta_api(
        session=LocalAPISession(token="skill-token"),
        gateway=gateway,
        persistence_store=store,
    )

    async def run() -> None:
        headers = {"authorization": "Bearer skill-token"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            catalog = await client.get("/skills", headers=headers)
            invalid = await client.post("/chat/stream", headers=headers, json={
                "messages": [{"role": "user", "content": "review"}],
                "skill_keys": ["arbitrary_tool"],
            })
            response = await client.post("/chat/stream", headers=headers, json={
                "messages": [{"role": "user", "content": "review"}],
                "skill_keys": ["risk_review"],
            })
        assert catalog.status_code == 200
        assert {item["skill_key"] for item in catalog.json()["skills"]} == {
            "risk_review", "decision_brief", "action_items"
        }
        assert "definition_json" not in catalog.json()["skills"][0]
        assert invalid.status_code == 422
        assert response.status_code == 200
        assert adapter.request is not None
        assert adapter.request.messages[0]["role"] == "system"
        assert "风险审查" in adapter.request.messages[0]["content"] or "风险" in adapter.request.messages[0]["content"]

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_multi_agent_collaboration_runs_selected_local_roles_sequentially(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    class CollaborationAdapter:
        is_local = True

        def __init__(self) -> None:
            self.requests = []

        async def generate(self, request):
            raise AssertionError("collaboration must stream")

        async def call_with_tools(self, request):
            raise AssertionError("collaboration must not invoke tools")

        async def stream(self, request):
            self.requests.append(request)
            systems = "\n".join(item["content"] for item in request.messages if item["role"] == "system")
            if "你是项目助理" in systems:
                yield "项目建议"
            elif "你是会议助理" in systems:
                yield "会议建议"
            else:
                assert "项目建议" in "\n".join(item["content"] for item in request.messages)
                assert "会议建议" in "\n".join(item["content"] for item in request.messages)
                yield "综合建议"

    store = EncryptedApplicationStore(path=(tmp_path / "collaboration.db").resolve(), key=b"c" * 32)
    store.open()
    adapter = CollaborationAdapter()
    app = create_beta_api(
        session=LocalAPISession(token="collab-token"),
        gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        headers = {"authorization": "Bearer collab-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            single = await client.post("/chat/stream", headers=headers, json={
                "messages": [{"role": "user", "content": "分析"}],
                "collaborator_keys": ["project_assistant"],
            })
            cloud = await client.post("/chat/stream", headers=headers, json={
                "provider": "deepseek", "messages": [{"role": "user", "content": "分析"}],
                "collaborator_keys": ["project_assistant", "meeting_assistant"],
            })
            response = await client.post("/chat/stream", headers=headers, json={
                "messages": [{"role": "user", "content": "分析"}],
                "collaborator_keys": ["project_assistant", "meeting_assistant"],
            })
        assert single.status_code == 422
        assert cloud.status_code == 403
        assert response.status_code == 200
        assert "项目助理观点" in response.text
        assert "会议助理观点" in response.text
        assert "综合建议" in response.text
        assert len(adapter.requests) == 3
        assert [request.thinking_enabled for request in adapter.requests] == [False, False, False]
        assert "你是项目助理" in adapter.requests[0].messages[0]["content"]
        assert "你是会议助理" in adapter.requests[1].messages[0]["content"]
        project_system = "\n".join(
            item["content"] for item in adapter.requests[0].messages if item["role"] == "system"
        )
        meeting_system = "\n".join(
            item["content"] for item in adapter.requests[1].messages if item["role"] == "system"
        )
        assert "只围绕用户本轮明确目标分析" in project_system
        assert "严格遵守用户要求的数量、单项长度、语言、顺序和输出格式" in meeting_system
        assert "用户明确列出的每个事项都必须逐项回应，不得漏掉或用概括项替代" in project_system
        assert "不得编造用户未提供的日期、时长、数量或预算" in project_system
        synthesis_system = adapter.requests[2].messages[0]["content"]
        synthesis_reference = adapter.requests[2].messages[-2]
        synthesis_user = adapter.requests[2].messages[-1]
        assert "不得仅因其由模型生成就称其无效或拒绝" in synthesis_system
        assert "不扩展到无关领域" in synthesis_system
        assert "严格遵守用户要求的数量、单项长度、顺序和输出格式" in synthesis_system
        assert "用户明确列出的每个事项都必须逐项回应，不得漏掉或用概括项替代" in synthesis_system
        assert "不得编造用户未提供的日期、时长、数量或预算" in synthesis_system
        assert synthesis_reference["role"] == "user"
        assert "专业助理结构化参考建议" in synthesis_reference["content"]
        assert synthesis_user == {"role": "user", "content": "分析"}

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_multi_agent_output_limit_fails_run_before_synthesis(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    class OversizedSpecialistAdapter:
        is_local = True

        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, request):
            raise AssertionError("collaboration must stream")

        async def call_with_tools(self, request):
            raise AssertionError("collaboration must not invoke tools")

        async def stream(self, request):
            self.calls += 1
            yield "x" * 4_001

    store = EncryptedApplicationStore(path=(tmp_path / "collab-limit.db").resolve(), key=b"l" * 32)
    store.open()
    adapter = OversizedSpecialistAdapter()
    app = create_beta_api(
        session=LocalAPISession(token="collab-limit-token"),
        gateway=ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        headers = {"authorization": "Bearer collab-limit-token"}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1") as client:
            response = await client.post("/chat/stream", headers=headers, json={
                "messages": [{"role": "user", "content": "分析"}],
                "collaborator_keys": ["project_assistant", "meeting_assistant"],
            })
            assert response.status_code == 200
            assert "协作输出超过本机上下文上限" in response.text
            assert '"done":true' not in response.text
            run_id = response.headers["x-pac-run-id"]
            run_status = await client.get(f"/chat/runs/{run_id}", headers=headers)
        assert adapter.calls == 1
        assert run_status.json()["status"] == "failed"

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_memory_api_requires_explicit_confirmation_and_supports_search_delete(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    store = EncryptedApplicationStore(path=(tmp_path / "memories.db").resolve(), key=b"m" * 32)
    store.open()
    app = create_beta_api(session=LocalAPISession(token="memory-token"), persistence_store=store)

    async def run() -> None:
        headers = {"authorization": "Bearer memory-token"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            unconfirmed = await client.post("/memories", headers=headers, json={
                "subject": "Project Atlas", "content": "Use local encryption",
                "category": "decision", "confirmed": False,
            })
            created = await client.post("/memories", headers=headers, json={
                "subject": "Project Atlas", "content": "Use local encryption",
                "category": "decision", "confirmed": True,
            })
            unconfirmed_update = await client.put(f"/memories/{created.json()['id']}", headers=headers, json={
                "subject": "Project Atlas", "content": "Use local encrypted storage",
                "category": "decision", "confirmed": False,
            })
            updated = await client.put(f"/memories/{created.json()['id']}", headers=headers, json={
                "subject": "Project Atlas", "content": "Use local encrypted storage",
                "category": "decision", "confirmed": True,
            })
            versions = await client.get(
                f"/memories/{created.json()['id']}/versions", headers=headers
            )
            search = await client.get("/memories/search", headers=headers, params={"q": "local encrypted storage"})
            listed = await client.get("/memories", headers=headers)
            deleted = await client.delete(f"/memories/{created.json()['id']}", headers=headers)
        assert unconfirmed.status_code == 409
        assert created.status_code == 201
        assert unconfirmed_update.status_code == 409
        assert updated.json()["content"] == "Use local encrypted storage"
        assert versions.status_code == 200
        assert [version["version_no"] for version in versions.json()["versions"]] == [1, 2]
        assert versions.json()["versions"][0]["snapshot"]["content"] == "Use local encryption"
        assert len(search.json()["memories"]) == 1
        assert listed.json()["memories"][0]["claim_type"] == "user_confirmed_fact"
        assert deleted.json() == {"deleted": True}

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_backup_export_api_requires_local_auth_and_never_returns_password(tmp_path) -> None:
    from pac_poc.backup import read_backup_header
    from pac_poc.persistence import EncryptedApplicationStore

    database_key = b"b" * 32
    store = EncryptedApplicationStore(path=(tmp_path / "backup-api.db").resolve(), key=database_key)
    store.open()
    app = create_beta_api(
        session=LocalAPISession(token="backup-token"),
        gateway=ModelGateway(adapters={"ollama": StubLocalAdapter()}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )
    destination = tmp_path / "manual.pacbackup"

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            denied = await client.post("/backups/export", json={
                "destination_path": str(destination), "password": "private passphrase",
            })
            exported = await client.post("/backups/export", headers={
                "authorization": "Bearer backup-token",
            }, json={
                "destination_path": str(destination), "password": "private passphrase",
            })
            duplicate = await client.post("/backups/export", headers={
                "authorization": "Bearer backup-token",
            }, json={
                "destination_path": str(destination), "password": "private passphrase",
            })
        assert denied.status_code == 401
        assert exported.status_code == 201
        assert exported.json() == {"created": True, "bytes_written": destination.stat().st_size}
        assert "private passphrase" not in exported.text
        assert "destination" not in exported.text
        assert duplicate.status_code == 409
        assert read_backup_header(
            destination, password="private passphrase", database_key=database_key  # pragma: allowlist secret
        )[0].source_key_fingerprint

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_backup_restore_api_requires_local_auth_and_returns_only_prebackup_location(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    database_key = b"z" * 32
    store = EncryptedApplicationStore(path=(tmp_path / "restore-api.db").resolve(), key=database_key)
    store.open()
    conversation = store.get_or_create_default_conversation()
    store.append_chat_turn(
        conversation_id=str(conversation["id"]), run_id="api-restore",
        user_content="restore source", assistant_content="restored reply",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    backup = tmp_path / "restore-api.pacbackup"
    store.export_encrypted_backup(backup, password="api passphrase")  # pragma: allowlist secret
    store.append_chat_turn(
        conversation_id=str(conversation["id"]), run_id="api-later",
        user_content="remove this turn", assistant_content="later",
        provider="ollama", model="fixture", status="COMPLETED",
    )
    app = create_beta_api(
        session=LocalAPISession(token="restore-token"),
        gateway=ModelGateway(adapters={"ollama": StubLocalAdapter()}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            denied = await client.post("/backups/restore", json={
                "source_path": str(backup), "password": "api passphrase",
            })
            restored = await client.post("/backups/restore", headers={
                "authorization": "Bearer restore-token",
            }, json={"source_path": str(backup), "password": "api passphrase"})
        assert denied.status_code == 401
        assert restored.status_code == 200
        assert restored.json()["restored"] is True
        assert Path(restored.json()["prebackup_path"]).is_file()
        assert "api passphrase" not in restored.text
        assert "remove this turn" not in str(store.load_conversation(str(conversation["id"])))

    try:
        asyncio.run(run())
    finally:
        store.close()


def test_conversation_api_can_create_list_select_and_delete_one_conversation(tmp_path) -> None:
    from pac_poc.persistence import EncryptedApplicationStore

    store = EncryptedApplicationStore(path=(tmp_path / "conversations.db").resolve(), key=b"c" * 32)
    store.open()
    app = create_beta_api(
        session=LocalAPISession(token="conversation-token"),
        gateway=ModelGateway(adapters={"ollama": StubLocalAdapter()}, policy=LocalOnlyPolicy()),
        persistence_store=store,
    )

    async def run() -> None:
        headers = {"authorization": "Bearer conversation-token"}
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1"
        ) as client:
            first = (await client.get("/chat/history", headers=headers)).json()
            second_response = await client.post("/conversations", headers=headers, json={"title": "Second"})
            second = second_response.json()
            renamed = await client.patch(
                f"/conversations/{second['id']}", headers=headers, json={"title": "Planning"}
            )
            await client.post("/chat/stream", headers=headers, json={
                "conversation_id": first["conversation_id"],
                "messages": [{"role": "user", "content": "first message"}],
            })
            await client.post("/chat/stream", headers=headers, json={
                "conversation_id": second["id"],
                "messages": [{"role": "user", "content": "second message"}],
            })
            listed = await client.get("/conversations", headers=headers)
            selected = await client.get(f"/conversations/{second['id']}", headers=headers)
            deleted = await client.delete(f"/conversations/{first['conversation_id']}", headers=headers)
            remaining = await client.get("/conversations", headers=headers)
        assert second_response.status_code == 201
        assert renamed.status_code == 200
        assert renamed.json()["title"] == "Planning"
        assert len(listed.json()["conversations"]) == 2
        assert selected.json()["title"] == "Planning"
        assert [message["content"] for message in selected.json()["messages"]] == [
            "second message", "本机回答"
        ]
        assert deleted.json() == {"deleted": True}
        assert [item["id"] for item in remaining.json()["conversations"]] == [second["id"]]

    try:
        asyncio.run(run())
    finally:
        store.close()
