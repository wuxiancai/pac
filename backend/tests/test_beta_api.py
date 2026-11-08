from __future__ import annotations

import asyncio

import httpx

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
