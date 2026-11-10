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
from typing import Any, Callable, Literal, Protocol
from uuid import UUID

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    ProviderStreamChunk,
    OllamaAdapter,
)
from .imported_text import (
    MAX_IMPORTED_FILE_BYTES,
    ImportRejected,
    ImportedTextRegistry,
)
from .persistence import EncryptedApplicationStore, PersistentStoreError, default_database_path
from .orchestrator import (
    ConversationTurn,
    MainAssistantOrchestrator,
    RunRegistry,
    RunStatus,
)
from .model_capabilities import Capability, ModelCapabilityRegistry
from .beta_capabilities import load_beta_capability_registry
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
from .usage import UsageLedger, UsageRecord, UsageState, usage_record_to_dict


BETA_MODEL = "qwen3.5:0.8b"
BETA_SOURCE = "beta-gui-chat"
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 16_000
MAX_CONTEXT_CHARS = 40_000
MAX_CHAT_REQUEST_BYTES = 512 * 1024
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


class ChatPersistenceUnavailable(RuntimeError):
    """Safe marker for a local chat write failure."""


class ConfirmedMemoryCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(min_length=1, max_length=512)
    content: str = Field(min_length=1, max_length=20_000)
    category: Literal[
        "fact", "preference", "goal", "event", "decision", "commitment", "relationship", "project"
    ]
    confirmed: bool
    source_message_id: UUID | None = None


class TaskCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=20_000)
    priority: int = Field(default=0, ge=0, le=5)
    schedule_at: str | None = Field(default=None, max_length=32)
    idempotency_key: UUID


class TaskTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "PENDING", "READY", "RUNNING", "WAITING", "PAUSED",
        "PARTIAL", "COMPLETED", "FAILED", "CANCELLED",
    ]
    error_code: str | None = Field(default=None, max_length=64)


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
    import_ids: list[UUID] = Field(default_factory=list, max_length=4)
    conversation_id: UUID | None = None


class BetaVoiceTranscriber(Protocol):
    def begin_stream(self) -> None: ...

    def accept_stream_frame(self, pcm: bytes, sequence: int) -> ASREvent | None: ...

    def end_stream(self, sequence: int) -> ASREvent | None: ...

    def abort_stream(self) -> None: ...

    def transcribe_pcm16le(self, pcm: bytes) -> str: ...


async def _stream_with_keepalives(
    source: AsyncIterator[ProviderStreamChunk], interval_seconds: float
) -> AsyncIterator[ProviderStreamChunk | None]:
    """Keep an SSE response active without exposing upstream thinking content."""
    iterator = source.__aiter__()

    async def next_value() -> ProviderStreamChunk:
        return await iterator.__anext__()

    next_delta: asyncio.Task[ProviderStreamChunk] = asyncio.create_task(next_value())
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


async def _run_voice_worker(function: Callable[..., Any], *args: Any) -> Any:
    """Wait for a blocking ASR call to finish before cancellation cleanup proceeds."""
    worker = asyncio.create_task(asyncio.to_thread(function, *args))
    try:
        return await asyncio.shield(worker)
    except asyncio.CancelledError:
        try:
            await worker
        except Exception:
            pass
        raise


@dataclass(frozen=True)
class BetaAPIDependencies:
    """Explicit composition inputs for the in-memory beta application factory."""

    session: LocalAPISession
    gateway: ModelGateway | None = None
    credentials: CredentialProvider | None = None
    remote_adapters: Mapping[str, LocalProviderAdapter] | None = None
    voice_transcriber: BetaVoiceTranscriber | None = None
    capability_registry: ModelCapabilityRegistry | None = None
    settings: BetaAPISettings = DEFAULT_BETA_API_SETTINGS
    database_key: bytes | None = None
    persistence_store: EncryptedApplicationStore | None = None


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
    database_key: bytes | None = None,
    persistence_store: EncryptedApplicationStore | None = None,
) -> FastAPI:
    """Compatibility composition root for the injected beta app factory."""
    return create_beta_app(dependencies=BetaAPIDependencies(
        session=session,
        gateway=gateway,
        credentials=credentials,
        remote_adapters=remote_adapters_override,
        voice_transcriber=voice_transcriber_override,
        settings=settings,
        database_key=database_key,
        persistence_store=persistence_store,
    ))


def create_beta_app(*, dependencies: BetaAPIDependencies) -> FastAPI:
    """Build the authenticated in-memory beta API from explicit dependencies."""
    session = dependencies.session
    gateway = dependencies.gateway
    credentials = dependencies.credentials
    remote_adapters_override = dependencies.remote_adapters
    voice_transcriber_override = dependencies.voice_transcriber
    settings = dependencies.settings
    if dependencies.database_key is not None and dependencies.persistence_store is not None:
        raise ValueError("provide either a database key or an opened persistence store")
    persistent_store: EncryptedApplicationStore | None = dependencies.persistence_store
    capability_registry = (
        dependencies.capability_registry
        if dependencies.capability_registry is not None
        else load_beta_capability_registry()
    )
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
    run_registry = RunRegistry()
    usage_ledger = UsageLedger()
    imported_text = ImportedTextRegistry()
    import_request_lock = asyncio.Lock()
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
            started = True
            await _run_voice_worker(voice_transcriber.begin_stream)
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
                    event = await _run_voice_worker(
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
                        event = await _run_voice_worker(voice_transcriber.end_stream, sequence)
                        if event is not None:
                            await websocket.send_json({
                                "type": "final",
                                "text": event.text,
                                "sequence": event.sequence,
                                "revision_id": event.revision_id,
                            })
                        if started:
                            await _run_voice_worker(voice_transcriber.abort_stream)
                            started = False
                        voice_stream_lock.release()
                        lock_acquired = False
                        await websocket.send_json({"type": "ended"})
                        break
                    if command == {"type": "abort"}:
                        if started:
                            await _run_voice_worker(voice_transcriber.abort_stream)
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
                    await _run_voice_worker(voice_transcriber.abort_stream)
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
                declared_length = int(content_length)
                if declared_length < 0:
                    raise HTTPException(status_code=400, detail="invalid content length")
                if declared_length > settings.max_voice_pcm_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"audio exceeds {settings.max_voice_seconds} seconds",
                    )
            except ValueError:
                raise HTTPException(status_code=400, detail="invalid content length") from None
        pcm_data = bytearray()
        async for chunk in request.stream():
            if len(pcm_data) + len(chunk) > settings.max_voice_pcm_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"audio exceeds {settings.max_voice_seconds} seconds",
                )
            pcm_data.extend(chunk)
        pcm = bytes(pcm_data)
        if not pcm or len(pcm) % 2:
            raise HTTPException(status_code=422, detail="audio must be non-empty PCM16LE")
        if len(pcm) > settings.max_voice_pcm_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"audio exceeds {settings.max_voice_seconds} seconds",
            )
        try:
            try:
                await asyncio.wait_for(
                    voice_stream_lock.acquire(),
                    timeout=settings.voice_stream_lock_wait_seconds,
                )
            except TimeoutError:
                raise HTTPException(
                    status_code=409, detail="local voice recognition is busy"
                ) from None
            try:
                text = await _run_voice_worker(voice_transcriber.transcribe_pcm16le, pcm)
            finally:
                voice_stream_lock.release()
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

    @router.get("/chat/runs/{run_id}")
    async def get_chat_run(run_id: str) -> dict[str, str | float]:
        run = run_registry.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return {
            "run_id": run.run_id,
            "assistant": run.assistant_key,
            "status": run.status.value,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }

    @router.get("/usage")
    async def get_usage(limit: int = Query(default=50, ge=1, le=100)) -> dict[str, object]:
        return {
            "retention": "process_memory_only",
            "summary": usage_ledger.summary(),
            "records": [
                usage_record_to_dict(record)
                for record in usage_ledger.list_records(limit=limit)
            ],
        }

    @router.get("/model-capabilities")
    async def get_model_capabilities(
        provider_id: str = Query(min_length=1, max_length=64),
        model_id: str = Query(min_length=1, max_length=128),
    ) -> dict[str, object]:
        report = capability_registry.report(provider_id, model_id)
        return {
            "provider_id": provider_id,
            "model_id": model_id,
            "verified_at": report.verified_at if report is not None else None,
            "evidence_refs": list(report.evidence_refs) if report is not None else [],
            "region": report.region if report is not None else None,
            "capabilities": {
                capability.value: capability_registry.state(
                    provider_id, model_id, capability
                ).value
                for capability in Capability
            },
        }

    @router.post("/imports/text", status_code=201)
    async def import_selected_text(request: Request) -> dict[str, str | int]:
        # Do not let concurrent authenticated uploads each allocate a 10 MiB body
        # before the registry's aggregate in-memory limit is checked.
        if import_request_lock.locked():
            raise HTTPException(status_code=409, detail="another file import is in progress")
        await import_request_lock.acquire()
        try:
            return await _receive_imported_text(request, imported_text)
        finally:
            import_request_lock.release()

    async def _receive_imported_text(
        request: Request, registry: ImportedTextRegistry
    ) -> dict[str, str | int]:
        display_name = request.query_params.get("filename", "")
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_IMPORTED_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="file exceeds the 10 MB limit")
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="invalid content length") from exc
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() not in {
            "application/octet-stream",
            "text/plain",
        }:
            raise HTTPException(status_code=415, detail="unsupported file content type")
        data = bytearray()
        async for chunk in request.stream():
            if len(data) + len(chunk) > MAX_IMPORTED_FILE_BYTES:
                raise HTTPException(status_code=413, detail="file exceeds the 10 MB limit")
            data.extend(chunk)
        try:
            document = registry.add(display_name, bytes(data))
        except ImportRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "import_id": document.import_id,
            "display_name": document.display_name,
            "byte_count": document.byte_count,
            "character_count": document.character_count,
        }

    @router.delete("/imports/{import_id}")
    async def remove_imported_text(import_id: str) -> dict[str, bool]:
        if not imported_text.remove(import_id):
            raise HTTPException(status_code=404, detail="import not found")
        return {"removed": True}

    @router.get("/memories")
    async def list_memories(limit: int = Query(default=200, ge=1, le=500)) -> dict[str, object]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent memory storage is unavailable")
        try:
            return {"memories": persistent_store.list_memories(limit=limit)}
        except Exception:
            raise HTTPException(status_code=503, detail="memories are unavailable") from None

    @router.get("/memories/search")
    async def search_memories(q: str = Query(min_length=1, max_length=256), limit: int = Query(default=50, ge=1, le=200)) -> dict[str, object]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent memory storage is unavailable")
        try:
            return {"memories": persistent_store.search_memories(q, limit=limit)}
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="memory search query is invalid") from exc
        except Exception:
            raise HTTPException(status_code=503, detail="memory search is unavailable") from None

    @router.post("/memories", status_code=201)
    async def create_memory(payload: ConfirmedMemoryCreateRequest) -> dict[str, object]:
        if not payload.confirmed:
            raise HTTPException(status_code=409, detail="explicit user confirmation is required")
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent memory storage is unavailable")
        try:
            return persistent_store.create_confirmed_memory(
                subject=payload.subject,
                content=payload.content,
                category=payload.category,
                source_message_id=str(payload.source_message_id) if payload.source_message_id else None,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="source message not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="memory details are invalid") from exc
        except Exception:
            raise HTTPException(status_code=503, detail="memory could not be saved") from None

    @router.delete("/memories/{memory_id}")
    async def delete_memory(memory_id: UUID) -> dict[str, bool]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent memory storage is unavailable")
        try:
            return {"deleted": persistent_store.delete_memory(str(memory_id))}
        except Exception:
            raise HTTPException(status_code=503, detail="memory could not be deleted") from None

    @router.get("/tasks")
    async def list_tasks(include_completed: bool = True, limit: int = Query(default=100, ge=1, le=500)) -> dict[str, object]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent task storage is unavailable")
        try:
            persistent_store.purge_expired_completed_tasks()
            return {"tasks": persistent_store.list_tasks(include_completed=include_completed, limit=limit)}
        except PersistentStoreError as exc:
            raise HTTPException(status_code=503, detail="tasks are unavailable") from exc
        except Exception:
            raise HTTPException(status_code=503, detail="tasks are unavailable") from None

    @router.post("/tasks", status_code=201)
    async def create_task(payload: TaskCreateRequest) -> dict[str, object]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent task storage is unavailable")
        try:
            return persistent_store.create_task(
                title=payload.title,
                description=payload.description,
                priority=payload.priority,
                schedule_at=payload.schedule_at,
                idempotency_key=str(payload.idempotency_key),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PersistentStoreError as exc:
            raise HTTPException(status_code=503, detail="task could not be saved") from exc
        except Exception:
            raise HTTPException(status_code=503, detail="task could not be saved") from None

    @router.patch("/tasks/{task_id}/status")
    async def transition_task(task_id: UUID, payload: TaskTransitionRequest) -> dict[str, object]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent task storage is unavailable")
        try:
            return persistent_store.transition_task(
                str(task_id), payload.status, error_code=payload.error_code
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="task not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail="task status transition is not allowed") from exc
        except PersistentStoreError as exc:
            raise HTTPException(status_code=503, detail="task could not be updated") from exc
        except Exception:
            raise HTTPException(status_code=503, detail="task could not be updated") from None

    @router.delete("/tasks/{task_id}")
    async def delete_task(task_id: UUID) -> dict[str, bool]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent task storage is unavailable")
        try:
            return {"deleted": persistent_store.delete_task(str(task_id))}
        except PersistentStoreError as exc:
            raise HTTPException(status_code=503, detail="task could not be deleted") from exc
        except Exception:
            raise HTTPException(status_code=503, detail="task could not be deleted") from None

    @router.get("/chat/history")
    async def get_chat_history() -> dict[str, object]:
        if persistent_store is None:
            return {"conversation_id": None, "messages": []}
        try:
            snapshot = persistent_store.load_conversation()
        except PersistentStoreError as exc:
            raise HTTPException(status_code=503, detail="chat history is unavailable") from exc
        return {"conversation_id": snapshot["id"], "messages": snapshot["messages"]}

    @router.delete("/chat/history")
    async def delete_chat_history() -> dict[str, bool]:
        if persistent_store is None:
            raise HTTPException(status_code=503, detail="persistent storage is unavailable")
        try:
            snapshot = persistent_store.load_conversation()
            deleted = persistent_store.delete_conversation(str(snapshot["id"]))
        except (KeyError, PersistentStoreError) as exc:
            raise HTTPException(status_code=503, detail="chat history could not be deleted") from exc
        return {"deleted": deleted}

    @router.post("/chat/stream")
    async def stream_chat(request: Request) -> StreamingResponse:
        content_type = request.headers.get("content-type")
        if content_type is not None:
            media_type = content_type.split(";", 1)[0].strip().lower()
            if media_type != "application/json" and not media_type.endswith("+json"):
                raise HTTPException(status_code=415, detail="expected a JSON chat request")
        request_data = bytearray()
        async for chunk in request.stream():
            if len(request_data) + len(chunk) > MAX_CHAT_REQUEST_BYTES:
                raise HTTPException(status_code=413, detail="chat request body is too large")
            request_data.extend(chunk)
        try:
            payload = StreamChatRequest.model_validate_json(bytes(request_data))
        except ValidationError as exc:
            raise RequestValidationError(exc.errors(), body=bytes(request_data)) from exc
        conversation_id: str | None = None
        if persistent_store is not None:
            try:
                snapshot = persistent_store.load_conversation(
                    str(payload.conversation_id) if payload.conversation_id else None
                )
                conversation_id = str(snapshot["id"])
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="conversation not found") from exc
            except PersistentStoreError as exc:
                raise HTTPException(status_code=503, detail="chat history is unavailable") from exc
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
        if payload.provider in CLOUD_PROVIDERS and payload.import_ids:
            raise HTTPException(
                status_code=403,
                detail="selected documents are available to local models only",
            )
        try:
            imported_documents = imported_text.get_many(
                tuple(str(item) for item in payload.import_ids)
            )
        except ImportRejected as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="selected file is no longer available") from exc
        # Reject obviously oversized contexts before ContextBuilder JSON-encodes
        # potentially multi-megabyte documents. Escaping and framing can only
        # increase the final size, which is still checked after request building.
        if total_chars + sum(item.character_count for item in imported_documents) > settings.max_context_chars:
            raise HTTPException(status_code=413, detail="conversation context is too long")
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
            documents=imported_documents,
        )
        orchestrator = MainAssistantOrchestrator(
            selected_gateway, capability_registry=capability_registry
        )
        model_request = orchestrator.prepare_request(turn)
        actual_context_chars = sum(len(item["content"]) for item in model_request.messages)
        if actual_context_chars > settings.max_context_chars:
            raise HTTPException(status_code=413, detail="conversation context is too long")
        try:
            run = run_registry.create(turn.assistant_key)
            run_registry.transition(run.run_id, RunStatus.RUNNING)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail="too many active chat runs") from exc
        started_monotonic = monotonic()

        async def events() -> AsyncIterator[str]:
            prompt_tokens: int | None = None
            completion_tokens: int | None = None
            cached_prompt_tokens: int | None = None
            cost_amount: float | None = None
            cost_currency: str | None = None
            assistant_output: list[str] = []

            def persist_turn(status: RunStatus) -> None:
                if persistent_store is None or conversation_id is None:
                    return
                if payload.messages[-1].role != "user":
                    return
                try:
                    persistent_store.append_chat_turn(
                        conversation_id=conversation_id,
                        run_id=run.run_id,
                        user_content=payload.messages[-1].content,
                        assistant_content="".join(assistant_output),
                        provider=payload.provider,
                        model=payload.model,
                        status=status.name,
                    )
                except Exception:
                    raise ChatPersistenceUnavailable from None

            try:
                async for delta in _stream_with_keepalives(
                    orchestrator.stream_request_with_usage(model_request),
                    settings.chat_stream_keepalive_seconds,
                ):
                    if delta is None:
                        yield ": keep-alive\n\n"
                        continue
                    if delta.prompt_tokens is not None:
                        prompt_tokens = delta.prompt_tokens
                    if delta.completion_tokens is not None:
                        completion_tokens = delta.completion_tokens
                    if delta.cached_prompt_tokens is not None:
                        cached_prompt_tokens = delta.cached_prompt_tokens
                    if delta.cost_amount is not None and delta.cost_currency is not None:
                        cost_amount = delta.cost_amount
                        cost_currency = delta.cost_currency
                    if delta.text:
                        assistant_output.append(delta.text)
                        yield "data: " + json.dumps({"delta": delta.text}, ensure_ascii=False) + "\n\n"
                persist_turn(RunStatus.COMPLETED)
                run_registry.transition(run.run_id, RunStatus.COMPLETED)
                yield "data: " + json.dumps(
                    {"done": True, "run_id": run.run_id}, separators=(",", ":")
                ) + "\n\n"
            except ChatPersistenceUnavailable:
                run_registry.transition(run.run_id, RunStatus.FAILED)
                yield "data: " + json.dumps(
                    {"error": "无法将本轮聊天安全保存到本机加密数据库；请检查磁盘空间后重试。"},
                    ensure_ascii=False,
                ) + "\n\n"
            except RemoteProviderError as exc:
                run_registry.transition(run.run_id, RunStatus.FAILED)
                try:
                    persist_turn(RunStatus.FAILED)
                except Exception:
                    pass
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
                run_registry.transition(run.run_id, RunStatus.FAILED)
                try:
                    persist_turn(RunStatus.FAILED)
                except Exception:
                    pass
                message = "本机无法从 Keychain 读取已保存的云端凭据；未能发起云端请求。"
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            except httpx.RequestError as exc:
                run_registry.transition(run.run_id, RunStatus.FAILED)
                try:
                    persist_turn(RunStatus.FAILED)
                except Exception:
                    pass
                if payload.provider == "ollama":
                    if isinstance(
                        exc, (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)
                    ):
                        message = "无法连接本机 Ollama；请确认 Ollama 正在运行且本机地址可访问。"
                    elif isinstance(exc, httpx.TimeoutException):
                        message = (
                            "等待本机 Ollama 响应超时；它可能仍在本机生成，"
                            "请检查 Ollama 状态后再重试。"
                        )
                    else:
                        message = "与本机 Ollama 通信失败；本机生成状态可能未知，请检查服务状态后再重试。"
                else:
                    message = (
                        "连接云端服务失败或超时；服务端是否收到请求无法确认，"
                        "请先检查服务商用量记录再重试。"
                    )
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            except Exception:
                run_registry.transition(run.run_id, RunStatus.FAILED)
                try:
                    persist_turn(RunStatus.FAILED)
                except Exception:
                    pass
                # Keep local service details and upstream error text out of the UI stream.
                if payload.provider == "ollama":
                    message = "本机模型请求失败，请确认 Ollama 正在运行且模型已安装。"
                else:
                    message = (
                        "云端请求处理失败；错误详情已省略，服务端是否收到请求未知。"
                        "请先检查服务商用量记录再重试；不会自动切换 Provider。"
                    )
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            finally:
                current = run_registry.get(run.run_id)
                if current is not None and current.status is RunStatus.RUNNING:
                    current = run_registry.transition(run.run_id, RunStatus.CANCELLED)
                else:
                    current = run_registry.get(run.run_id)
                if current is not None and current.status is RunStatus.CANCELLED:
                    try:
                        persist_turn(RunStatus.CANCELLED)
                    except Exception:
                        pass
                if current is not None:
                    completed_at = current.updated_at
                    usage_ledger.record(
                        UsageRecord(
                            run_id=run.run_id,
                            provider=payload.provider,
                            model=payload.model,
                            region=region,
                            purpose=purpose,
                            data_level=data_level,
                            status=current.status,
                            started_at=run.created_at,
                            completed_at=completed_at,
                            latency_ms=max(0, round((monotonic() - started_monotonic) * 1000)),
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                            cached_prompt_tokens=cached_prompt_tokens,
                            usage_state=(
                                UsageState.ACTUAL
                                if prompt_tokens is not None or completion_tokens is not None
                                else UsageState.UNKNOWN
                            ),
                            cost_amount=cost_amount,
                            cost_currency=cost_currency,
                            cost_state=(
                                UsageState.ACTUAL
                                if cost_amount is not None and cost_currency is not None
                                else UsageState.UNKNOWN
                            ),
                        )
                    )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-PAC-Run-ID": run.run_id},
        )

    app.include_router(router)
    if dependencies.database_key is not None:
        persistent_store = EncryptedApplicationStore(
            path=default_database_path(), key=dependencies.database_key
        )
        persistent_store.open()
        persistent_store.purge_expired_completed_tasks()
        app.router.on_shutdown.append(persistent_store.close)
    return app
