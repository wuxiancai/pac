from __future__ import annotations

import asyncio
from time import sleep

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from pac_poc.asr import ASREvent
from pac_poc.beta_api import BETA_MODEL, create_beta_api
from pac_poc.model_gateway import LocalModelRequest, ModelGateway, LocalOnlyPolicy
from pac_poc.security_poc import LocalAPISession


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
        assert response.status_code == 200
        assert '"delta": "本机"' in response.text
        assert '"delta": "回答"' in response.text
        assert '"done":true' in response.text
        assert adapter.request is not None
        assert adapter.request.model == BETA_MODEL
        assert adapter.request.provider == "ollama"
        assert adapter.request.messages == [{"role": "user", "content": "你好"}]

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
                    "messages": [{"role": "user", "content": "sk-1234567890abcdefghijklmnop"}],
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
