from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from time import time
from typing import Literal

import httpx
from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .keychain_credentials import (
    CredentialProvider,
    CredentialUnavailable,
    MacOSKeychainCredentialProvider,
)
from .model_gateway import (
    ConsentAwarePolicy,
    LocalModelRequest,
    LocalProviderAdapter,
    LocalOnlyPolicy,
    ModelGateway,
    OllamaAdapter,
)
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
)
from .voice_transcription import LocalVoiceTranscriber


BETA_MODEL = "qwen3.5:0.8b"
BETA_SOURCE = "beta-gui-chat"
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 16_000
MAX_CONTEXT_CHARS = 40_000
MAX_VOICE_PCM_BYTES = 960_000  # 30 seconds of 16 kHz mono PCM16
VOICE_MODEL_DIR = (
    Path(__file__).resolve().parent.parent
    / ".poc-data"
    / "models"
    / "sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20"
)


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
) -> FastAPI:
    """Build the beta's authenticated loopback API; chat data remains in memory."""
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
    voice_transcriber = LocalVoiceTranscriber(VOICE_MODEL_DIR)
    router = APIRouter()

    @router.post("/voice/transcribe")
    async def transcribe_voice(request: Request) -> dict[str, str]:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
            raise HTTPException(status_code=415, detail="expected in-memory PCM audio")
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_VOICE_PCM_BYTES:
                    raise HTTPException(status_code=413, detail="audio exceeds 30 seconds")
            except ValueError:
                raise HTTPException(status_code=400, detail="invalid content length") from None
        pcm = await request.body()
        if not pcm or len(pcm) % 2:
            raise HTTPException(status_code=422, detail="audio must be non-empty PCM16LE")
        if len(pcm) > MAX_VOICE_PCM_BYTES:
            raise HTTPException(status_code=413, detail="audio exceeds 30 seconds")
        try:
            text = await asyncio.to_thread(voice_transcriber.transcribe_pcm16le, pcm)
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
        if total_chars > MAX_CONTEXT_CHARS:
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
        request = LocalModelRequest(
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
                async for delta in selected_gateway.stream(request):
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
