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


def test_gateway_denies_nonlocal_adapter_before_opening_stream() -> None:
    remote = StaticLocalAdapter("must not be returned")
    remote.is_local = False
    gateway = ModelGateway(adapters={"remote": remote}, policy=LocalOnlyPolicy())

    async def collect() -> list[str]:
        return [chunk async for chunk in gateway.stream(request("remote"))]

    with pytest.raises(PolicyDenied):
        asyncio.run(collect())

    assert remote.calls == 0


def test_closing_gateway_stream_closes_adapter_stream() -> None:
    class CleanupAdapter(StaticLocalAdapter):
        def __init__(self) -> None:
            super().__init__("unused")
            self.closed = False

        async def stream(self, request: LocalModelRequest):
            try:
                yield "first"
                await asyncio.Event().wait()
            finally:
                self.closed = True

    adapter = CleanupAdapter()
    gateway = ModelGateway(adapters={"local": adapter}, policy=LocalOnlyPolicy())

    async def consume_then_close() -> tuple[str, bool]:
        stream = gateway.stream(request("local"))
        first = await anext(stream)
        await stream.aclose()
        return first, adapter.closed

    assert asyncio.run(consume_then_close()) == ("first", True)


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


@pytest.mark.parametrize("thinking_enabled", [True, False])
def test_ollama_adapter_passes_explicit_thinking_preference(thinking_enabled: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["think"] is thinking_enabled
        return httpx.Response(200, json={"message": {"content": "ok"}})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OllamaAdapter(client=client)

    async def call() -> str:
        try:
            return await adapter.generate(
                LocalModelRequest(
                    provider="ollama",
                    model="test-model",
                    messages=({"role": "user", "content": "hello"},),
                    thinking_enabled=thinking_enabled,
                )
            )
        finally:
            await client.aclose()

    assert asyncio.run(call()) == "ok"


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
