from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from pac_poc.model_gateway import (
    LocalModelRequest,
    LocalOnlyPolicy,
    ModelGateway,
    OllamaAdapter,
    PolicyDenied,
)


def request(provider: str = "local-a") -> LocalModelRequest:
    return LocalModelRequest(
        provider=provider,
        model="test-model",
        messages=({"role": "user", "content": "Say hello."},),
    )


class StaticLocalAdapter:
    is_local = True

    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = 0

    async def generate(self, request: LocalModelRequest) -> str:
        self.calls += 1
        return self.answer

    async def stream(self, request: LocalModelRequest):
        yield self.answer


def test_gateway_routes_the_same_request_to_distinct_local_adapters() -> None:
    first = StaticLocalAdapter("answer-a")
    second = StaticLocalAdapter("answer-b")
    gateway = ModelGateway(
        adapters={"local-a": first, "local-b": second},
        policy=LocalOnlyPolicy(),
    )

    assert asyncio.run(gateway.generate(request("local-a"))) == "answer-a"
    assert asyncio.run(gateway.generate(request("local-b"))) == "answer-b"
    assert (first.calls, second.calls) == (1, 1)


def test_gateway_denies_nonlocal_adapter_before_request() -> None:
    remote = StaticLocalAdapter("must not be returned")
    remote.is_local = False
    gateway = ModelGateway(
        adapters={"remote": remote},
        policy=LocalOnlyPolicy(),
    )

    async def call() -> str:
        return await gateway.generate(request("remote"))

    with pytest.raises(PolicyDenied):
        asyncio.run(call())

    assert remote.calls == 0


def test_ollama_adapter_rejects_non_loopback_endpoint() -> None:
    with pytest.raises(ValueError, match="loopback"):
        OllamaAdapter(base_url="https://example.com")


def test_ollama_adapter_normalizes_local_chat_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "127.0.0.1"
        assert request.url.path == "/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "test-model"
        assert payload["stream"] is False
        return httpx.Response(200, json={"message": {"content": "你好"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OllamaAdapter(base_url="http://127.0.0.1:11434", client=client)
    async def call() -> str:
        try:
            return await adapter.generate(request("ollama"))
        finally:
            await client.aclose()

    assert asyncio.run(call()) == "你好"


def test_ollama_stream_emits_local_text_deltas() -> None:
    lines = [
        json.dumps({"message": {"content": "你"}, "done": False}),
        json.dumps({"message": {"content": "好"}, "done": False}),
        json.dumps({"done": True}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text="\n".join(lines) + "\n")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OllamaAdapter(base_url="http://localhost:11434", client=client)
    async def collect() -> list[str]:
        try:
            return [chunk async for chunk in adapter.stream(request("ollama"))]
        finally:
            await client.aclose()

    assert asyncio.run(collect()) == ["你", "好"]
