from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .model_gateway import LocalModelRequest, LocalOnlyPolicy, ModelGateway, OllamaAdapter
from .security_poc import LocalAPISession, create_local_api


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


def create_beta_api(*, session: LocalAPISession, gateway: ModelGateway | None = None) -> FastAPI:
    """Build the beta's authenticated loopback API; chat data remains in memory."""
    app = create_local_api(session=session)
    model_gateway = gateway or ModelGateway(
        adapters={"ollama": OllamaAdapter()},
        policy=LocalOnlyPolicy(),
    )
    router = APIRouter()

    @router.post("/chat/stream")
    async def stream_chat(payload: StreamChatRequest) -> StreamingResponse:
        total_chars = sum(len(message.content) for message in payload.messages)
        if total_chars > MAX_CONTEXT_CHARS:
            raise HTTPException(status_code=413, detail="conversation context is too long")
        messages = [{"role": item.role, "content": item.content} for item in payload.messages]
        request = LocalModelRequest(provider="ollama", model=BETA_MODEL, messages=messages)

        async def events() -> AsyncIterator[str]:
            try:
                async for delta in model_gateway.stream(request):
                    yield "data: " + json.dumps({"delta": delta}, ensure_ascii=False) + "\n\n"
                yield "data: {\"done\":true}\n\n"
            except Exception:
                # Keep local service details and upstream error text out of the UI stream.
                yield "data: {\"error\":\"本机模型请求失败，请确认 Ollama 正在运行且模型已安装。\"}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    app.include_router(router)
    return app
