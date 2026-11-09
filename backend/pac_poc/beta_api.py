from __future__ import annotations

import asyncio
import hmac
import json
import math
import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic, time
from typing import Literal, Protocol

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .keychain_credentials import (
    CredentialProvider,
    CredentialUnavailable,
    MacOSKeychainCredentialProvider,
)
from .model_gateway import (
    ConsentAwarePolicy,
    LocalProviderAdapter,
    LocalOnlyPolicy,
    ModelGateway,
    OllamaAdapter,
)
from .orchestrator import ConversationTurn, MainAssistantOrchestrator
from .remote_providers import (
    DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG,
    QWEN_APP_API_CONFIG,
    OpenAICompatibleRemoteAdapter,
    RemoteProviderConfig,
    RemoteProviderError,
)
from .security_poc import (
    ConsentGrant,
    ConsentManager,
    DataLevel,
    LocalAPISession,
    ModelAction,
    OutboundPolicy,
    create_local_api,
    _is_loopback_host,
)
from .asr import ASREvent
from .voice_transcription import LocalVoiceTranscriber


BETA_MODEL = "qwen3.5:0.8b"
BETA_SOURCE = "beta-gui-chat"
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 16_000
MAX_CONTEXT_CHARS = 40_000
MAX_VOICE_PCM_BYTES = 960_000  # 30 seconds of 16 kHz mono PCM16
VOICE_STREAM_LOCK_WAIT_SECONDS = 2.0
CHAT_STREAM_KEEPALIVE_SECONDS = 15.0
VOICE_MODEL_DIR = (
    Path(__file__).resolve().parent.parent
    / ".poc-data"
    / "models"
    / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
)


@dataclass(frozen=True)
class BetaAPISettings:
    """Non-secret, process-local runtime limits and resource locations."""

    max_context_chars: int = MAX_CONTEXT_CHARS
    max_voice_pcm_bytes: int = MAX_VOICE_PCM_BYTES
    voice_stream_lock_wait_seconds: float = VOICE_STREAM_LOCK_WAIT_SECONDS
    chat_stream_keepalive_seconds: float = CHAT_STREAM_KEEPALIVE_SECONDS
    voice_model_dir: Path = VOICE_MODEL_DIR

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_context_chars, bool)
            or not isinstance(self.max_context_chars, int)
            or not 0 < self.max_context_chars <= MAX_CONTEXT_CHARS
        ):
            raise ValueError("context limit must be positive and cannot exceed the Beta limit")
        if (
            isinstance(self.max_voice_pcm_bytes, bool)
            or not isinstance(self.max_voice_pcm_bytes, int)
            or not 0 < self.max_voice_pcm_bytes <= MAX_VOICE_PCM_BYTES
        ):
            raise ValueError("PCM byte limit must be positive and cannot exceed 30 seconds")
        if self.max_voice_pcm_bytes % 32_000:
            raise ValueError("PCM byte limit must represent a whole second of 16 kHz mono PCM16")
        timeout = self.voice_stream_lock_wait_seconds
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise ValueError("voice stream lock timeout must be finite and positive")
        keepalive = self.chat_stream_keepalive_seconds
        if (
            isinstance(keepalive, bool)
            or not isinstance(keepalive, (int, float))
            or not math.isfinite(keepalive)
            or keepalive <= 0
        ):
            raise ValueError("chat stream keepalive must be finite and positive")
        if not isinstance(self.voice_model_dir, Path) or not self.voice_model_dir.is_absolute():
            raise ValueError("voice model directory must be absolute")

    @property
    def max_voice_seconds(self) -> int:
        return self.max_voice_pcm_bytes // 32_000


DEFAULT_BETA_API_SETTINGS = BetaAPISettings()


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class StreamChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_MESSAGES)
    provider: Literal["ollama", "deepseek", "openrouter", "qwen-app"] = "ollama"
    model: str = Field(default=BETA_MODEL, min_length=1, max_length=128)
    confirmed_for_this_request: bool = False


class BetaVoiceTranscriber(Protocol):
    def begin_stream(self) -> None: ...

    def accept_stream_frame(self, pcm: bytes, sequence: int) -> ASREvent | None: ...

    def end_stream(self, sequence: int) -> ASREvent | None: ...

    def abort_stream(self) -> None: ...

    def transcribe_pcm16le(self, pcm: bytes) -> str: ...


async def _stream_with_keepalives(
    source: AsyncIterator[str], interval_seconds: float
) -> AsyncIterator[str | None]:
    """Keep an SSE response active without exposing upstream thinking content."""
    iterator = source.__aiter__()

    async def next_value() -> str:
        return await iterator.__anext__()

    next_delta: asyncio.Task[str] = asyncio.create_task(next_value())
    try:
        while True:
            completed, _ = await asyncio.wait({next_delta}, timeout=interval_seconds)
            if not completed:
                yield None
                continue
            try:
                delta = next_delta.result()
            except StopAsyncIteration:
                break
            yield delta
            next_delta = asyncio.create_task(next_value())
    finally:
        if not next_delta.done():
            next_delta.cancel()
        await asyncio.gather(next_delta, return_exceptions=True)
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()


@dataclass(frozen=True)
class BetaAPIDependencies:
    """Explicit composition inputs for the in-memory beta application factory."""

    session: LocalAPISession
    gateway: ModelGateway | None = None
    credentials: CredentialProvider | None = None
    remote_adapters: Mapping[str, LocalProviderAdapter] | None = None
    voice_transcriber: BetaVoiceTranscriber | None = None
    settings: BetaAPISettings = DEFAULT_BETA_API_SETTINGS


CLOUD_PROVIDERS: dict[str, RemoteProviderConfig] = {
    "deepseek": DEEPSEEK_PROBE_CONFIG,
    "openrouter": OPENROUTER_PROBE_CONFIG,
    "qwen-app": QWEN_APP_API_CONFIG,
}


def _is_valid_local_model_name(value: str) -> bool:
    return all(char.isalnum() or char in "._:/-" for char in value)


_L3_SECRET_PATTERN = re.compile(
    r"(?:sk-[A-Za-z0-9_-]{16,}|Bearer\s+[A-Za-z0-9._~-]{16,}|"
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
    re.IGNORECASE,
)


def create_beta_api(
    *,
    session: LocalAPISession,
    gateway: ModelGateway | None = None,
    credentials: CredentialProvider | None = None,
    remote_adapters_override: Mapping[str, LocalProviderAdapter] | None = None,
    voice_transcriber_override: BetaVoiceTranscriber | None = None,
    settings: BetaAPISettings = DEFAULT_BETA_API_SETTINGS,
) -> FastAPI:
    """Compatibility composition root for the injected beta app factory."""
    return create_beta_app(dependencies=BetaAPIDependencies(
        session=session,
        gateway=gateway,
        credentials=credentials,
        remote_adapters=remote_adapters_override,
        voice_transcriber=voice_transcriber_override,
        settings=settings,
    ))


def create_beta_app(*, dependencies: BetaAPIDependencies) -> FastAPI:
    """Build the authenticated in-memory beta API from explicit dependencies."""
    session = dependencies.session
    gateway = dependencies.gateway
    credentials = dependencies.credentials
    remote_adapters_override = dependencies.remote_adapters
    voice_transcriber_override = dependencies.voice_transcriber
    settings = dependencies.settings
    app = create_local_api(session=session)
    ollama = OllamaAdapter()
    credential_provider = credentials or MacOSKeychainCredentialProvider()
    remote_adapters = dict(remote_adapters_override) if remote_adapters_override is not None else {
        provider: OpenAICompatibleRemoteAdapter(
            config,
            credentials=credential_provider,
            max_output_tokens=1024,
        )
        for provider, config in CLOUD_PROVIDERS.items()
    }
    voice_transcriber: BetaVoiceTranscriber = voice_transcriber_override or LocalVoiceTranscriber(
        settings.voice_model_dir
    )
    voice_stream_lock = asyncio.Lock()
    router = APIRouter()

    @router.websocket("/voice/stream")
    async def stream_voice(websocket: WebSocket) -> None:
        authorization = websocket.headers.get("authorization", "")
        candidate = authorization[7:] if authorization.startswith("Bearer ") else ""
        valid = (
            _is_loopback_host(websocket.headers.get("host", ""))
            and websocket.headers.get("origin") is None
            and monotonic() < session.expires_at
            and hmac.compare_digest(candidate.encode(), session.token.encode())
        )
        if not valid:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        try:
            await asyncio.wait_for(
                voice_stream_lock.acquire(),
                timeout=settings.voice_stream_lock_wait_seconds,
            )
        except TimeoutError:
            await websocket.send_json({
                "type": "error",
                "message": "本机语音识别正忙，请稍后重试；音频未发送到云端",
            })
            await websocket.close(code=1013)
            return
        lock_acquired = True
        started = False
        total_bytes = 0
        sequence = 0
        try:
            start = await websocket.receive_json()
            if start != {
                "type": "start",
                "sample_rate_hz": 16_000,
                "channels": 1,
                "encoding": "pcm_s16le",
                "frame_duration_ms": 200,
            }:
                await websocket.send_json({"type": "error", "message": "不支持的本机语音格式"})
                await websocket.close(code=1008)
                return
            await asyncio.to_thread(voice_transcriber.begin_stream)
            started = True
            await websocket.send_json({"type": "ready"})
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    packet = message["bytes"]
                    if len(packet) < 6:
                        await websocket.send_json({"type": "error", "message": "音频帧格式无效"})
                        await websocket.close(code=1008)
                        break
                    frame_sequence = int.from_bytes(packet[:4], "big")
                    pcm = packet[4:]
                    if frame_sequence != sequence or len(pcm) % 2 or len(pcm) > 12_800:
                        await websocket.send_json({"type": "error", "message": "音频帧格式或序号无效"})
                        await websocket.close(code=1008)
                        break
                    total_bytes += len(pcm)
                    if total_bytes > settings.max_voice_pcm_bytes:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"录音超过 {settings.max_voice_seconds} 秒上限",
                        })
                        await websocket.close(code=1008)
                        break
                    event = await asyncio.to_thread(
                        voice_transcriber.accept_stream_frame, pcm, sequence
                    )
                    sequence += 1
                    if event is not None:
                        await websocket.send_json({
                            "type": event.kind,
                            "text": event.text,
                            "sequence": event.sequence,
                            "revision_id": event.revision_id,
                        })
                    continue
                if message.get("text") is not None:
                    try:
                        command = json.loads(message["text"])
                    except json.JSONDecodeError:
                        command = {}
                    if command == {"type": "end"}:
                        event = await asyncio.to_thread(voice_transcriber.end_stream, sequence)
                        if event is not None:
                            await websocket.send_json({
                                "type": "final",
                                "text": event.text,
                                "sequence": event.sequence,
                                "revision_id": event.revision_id,
                            })
                        if started:
                            await asyncio.to_thread(voice_transcriber.abort_stream)
                            started = False
                        voice_stream_lock.release()
                        lock_acquired = False
                        await websocket.send_json({"type": "ended"})
                        break
                    if command == {"type": "abort"}:
                        if started:
                            await asyncio.to_thread(voice_transcriber.abort_stream)
                            started = False
                        if lock_acquired:
                            voice_stream_lock.release()
                            lock_acquired = False
                        await websocket.send_json({"type": "ended"})
                        break
                    await websocket.send_json({"type": "error", "message": "未知语音控制命令"})
                    await websocket.close(code=1008)
                    break
        except WebSocketDisconnect:
            pass
        except (FileNotFoundError, RuntimeError, ValueError):
            try:
                await websocket.send_json({"type": "error", "message": "本机语音识别不可用；音频未发送到云端"})
                await websocket.close(code=1011)
            except RuntimeError:
                pass
        except Exception as error:
            try:
                await websocket.send_json({
                    "type": "error",
                    "message": (
                        "本机语音识别发生内部错误"
                        f"（{type(error).__name__}）；音频未发送到云端"
                    ),
                })
                await websocket.close(code=1011)
            except RuntimeError:
                pass
        finally:
            try:
                if started:
                    await asyncio.to_thread(voice_transcriber.abort_stream)
            finally:
                if lock_acquired:
                    voice_stream_lock.release()

    @router.post("/voice/transcribe")
    async def transcribe_voice(request: Request) -> dict[str, str]:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
            raise HTTPException(status_code=415, detail="expected in-memory PCM audio")
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > settings.max_voice_pcm_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"audio exceeds {settings.max_voice_seconds} seconds",
                    )
            except ValueError:
                raise HTTPException(status_code=400, detail="invalid content length") from None
        pcm = await request.body()
        if not pcm or len(pcm) % 2:
            raise HTTPException(status_code=422, detail="audio must be non-empty PCM16LE")
        if len(pcm) > settings.max_voice_pcm_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"audio exceeds {settings.max_voice_seconds} seconds",
            )
        try:
            if voice_stream_lock.locked():
                raise HTTPException(status_code=409, detail="local voice recognition is busy")
            async with voice_stream_lock:
                text = await asyncio.to_thread(voice_transcriber.transcribe_pcm16le, pcm)
        except HTTPException:
            raise
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="本机双语语音模型尚未安装") from None
        except RuntimeError:
            raise HTTPException(status_code=503, detail="本机语音识别当前不可用") from None
        if not text.strip():
            raise HTTPException(status_code=422, detail="本次录音未识别到语音")
        return {"text": text}

    def gateway_for(payload: StreamChatRequest) -> ModelGateway:
        if payload.provider == "ollama":
            if not _is_valid_local_model_name(payload.model):
                raise HTTPException(status_code=422, detail="invalid local model name")
            if gateway is not None:
                return gateway
            return ModelGateway(adapters={"ollama": ollama}, policy=LocalOnlyPolicy())

        config = CLOUD_PROVIDERS[payload.provider]
        if payload.model != config.model:
            raise HTTPException(status_code=422, detail="unsupported provider model")
        if not payload.confirmed_for_this_request:
            raise HTTPException(status_code=403, detail="one-time user consent is required")
        if gateway is not None:
            return gateway

        # Each HTTP request gets a fresh, exact-match consent grant. It cannot
        # authorize a later request or another provider/model/region. The grant
        # is scoped to streaming only, from the beta chat surface only; a tool
        # proposal or a different source would require a separate grant.
        consent = ConsentManager()
        consent.grant(ConsentGrant(
            provider=config.provider,
            model=config.model,
            region=config.region,
            purpose="beta-interactive-chat",
            data_levels=frozenset({DataLevel.L2}),
            action_scopes=frozenset({ModelAction.STREAM}),
            source_scopes=frozenset({BETA_SOURCE}),
            expires_at=time() + 30,
        ))
        return ModelGateway(
            adapters={payload.provider: remote_adapters[payload.provider]},
            policy=ConsentAwarePolicy(OutboundPolicy(consent)),
        )

    @router.post("/chat/stream")
    async def stream_chat(payload: StreamChatRequest) -> StreamingResponse:
        total_chars = sum(len(message.content) for message in payload.messages)
        if total_chars > settings.max_context_chars:
            raise HTTPException(status_code=413, detail="conversation context is too long")
        if payload.provider in CLOUD_PROVIDERS and any(
            _L3_SECRET_PATTERN.search(item.content) for item in payload.messages
        ):
            raise HTTPException(
                status_code=403,
                detail="sensitive credentials are blocked from cloud requests",
            )
        messages = [{"role": item.role, "content": item.content} for item in payload.messages]
        selected_gateway = gateway_for(payload)
        if payload.provider in CLOUD_PROVIDERS:
            config = CLOUD_PROVIDERS[payload.provider]
            region = config.region
            purpose = "beta-interactive-chat"
            data_level = DataLevel.L2
            source = BETA_SOURCE
        else:
            region = ""
            purpose = ""
            data_level = DataLevel.L0
            source = ""
        turn = ConversationTurn(
            provider=payload.provider,
            model=payload.model,
            messages=messages,
            region=region,
            purpose=purpose,
            data_level=data_level,
            source=source,
        )

        async def events() -> AsyncIterator[str]:
            try:
                async for delta in _stream_with_keepalives(
                    MainAssistantOrchestrator(selected_gateway).stream(turn),
                    settings.chat_stream_keepalive_seconds,
                ):
                    if delta is None:
                        yield ": keep-alive\n\n"
                        continue
                    yield "data: " + json.dumps({"delta": delta}, ensure_ascii=False) + "\n\n"
                yield "data: {\"done\":true}\n\n"
            except RemoteProviderError as exc:
                if exc.is_authentication_error:
                    message = "云端 API Key 认证失败，请检查 Keychain 中保存的密钥。"
                elif exc.status_code == 402:
                    message = "云端账户余额或套餐额度不足。"
                elif exc.status_code == 403:
                    message = "云端服务拒绝了本次请求。"
                elif exc.status_code == 429:
                    message = "云端请求频率受限；请稍后再试。"
                elif exc.status_code is not None:
                    message = (
                        f"云端服务返回 HTTP {exc.status_code}；已停止发送，"
                        "不会自动切换 Provider。"
                    )
                else:
                    message = (
                        "云端服务返回无法识别的响应；是否已计费未知，"
                        "请先检查服务商用量记录再重试。"
                    )
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            except CredentialUnavailable:
                message = "本机无法从 Keychain 读取已保存的云端凭据；未能发起云端请求。"
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            except httpx.RequestError:
                message = (
                    "连接云端服务失败或超时；服务端是否收到请求无法确认，"
                    "请先检查服务商用量记录再重试。"
                )
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            except Exception:
                # Keep local service details and upstream error text out of the UI stream.
                if payload.provider == "ollama":
                    message = "本机模型请求失败，请确认 Ollama 正在运行且模型已安装。"
                else:
                    message = (
                        "云端请求处理失败；错误详情已省略，服务端是否收到请求未知。"
                        "请先检查服务商用量记录再重试；不会自动切换 Provider。"
                    )
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    app.include_router(router)
    return app
