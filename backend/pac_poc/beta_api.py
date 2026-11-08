from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
from time import time
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .keychain_credentials import CredentialProvider, MacOSKeychainCredentialProvider
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
    OutboundPolicy,
    create_local_api,
)


BETA_MODEL = "qwen3.5:0.8b"
MAX_MESSAGES = 20
MAX_MESSAGE_CHARS = 16_000
MAX_CONTEXT_CHARS = 40_000


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
    router = APIRouter()

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
        # authorize a later request or another provider/model/region.
        consent = ConsentManager()
        consent.grant(ConsentGrant(
            provider=config.provider,
            model=config.model,
            region=config.region,
            purpose="beta-interactive-chat",
            data_levels=frozenset({DataLevel.L2}),
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
        else:
            region = ""
            purpose = ""
            data_level = DataLevel.L0
        request = LocalModelRequest(
            provider=payload.provider,
            model=payload.model,
            messages=messages,
            region=region,
            purpose=purpose,
            data_level=data_level,
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
                else:
                    message = "云端模型请求失败；已停止发送，不会自动切换 Provider。"
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"
            except Exception:
                # Keep local service details and upstream error text out of the UI stream.
                if payload.provider == "ollama":
                    message = "本机模型请求失败，请确认 Ollama 正在运行且模型已安装。"
                else:
                    message = "云端凭据不可用或请求失败；已停止发送，不会自动切换 Provider。"
                yield "data: " + json.dumps({"error": message}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    app.include_router(router)
    return app
