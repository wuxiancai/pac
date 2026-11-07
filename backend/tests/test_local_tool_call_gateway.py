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
    ProviderCapabilityUnsupported,
    ToolCall,
    ToolCallResult,
)


def tool_request(provider: str = "ollama") -> LocalModelRequest:
    return LocalModelRequest(
        provider=provider,
        model="qwen3.5:0.8b",
        messages=({"role": "user", "content": "Use the local lookup tool with key sample."},),
        tools=(
            {
                "type": "function",
                "function": {
                    "name": "lookup",
                    "description": "Return a synthetic value; never execute in this POC.",
                    "parameters": {
                        "type": "object",
                        "properties": {"key": {"type": "string"}},
                        "required": ["key"],
                        "additionalProperties": False,
                    },
                },
            },
        ),
    )


def test_ollama_adapter_transmits_tool_schema_and_parses_proposal_without_execution() -> None:
    expected_tools = list(tool_request().tools)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["tools"] == expected_tools
        assert payload["stream"] is False
        return httpx.Response(
            200,
            json={
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "lookup",
                                "arguments": {"key": "sample"},
                            }
                        }
                    ],
                }
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OllamaAdapter(client=client)

    async def call() -> ToolCallResult:
        try:
            return await adapter.call_with_tools(tool_request())
        finally:
            await client.aclose()

    result = asyncio.run(call())

    assert result.text == ""
    assert result.tool_calls == (ToolCall(name="lookup", arguments={"key": "sample"}),)


def test_ollama_adapter_rejects_malformed_tool_call_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"message": {"content": "", "tool_calls": [{"function": {"name": "lookup"}}]}},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = OllamaAdapter(client=client)

    async def call() -> ToolCallResult:
        try:
            return await adapter.call_with_tools(tool_request())
        finally:
            await client.aclose()

    with pytest.raises(RuntimeError, match="invalid tool-call response"):
        asyncio.run(call())


def test_gateway_routes_tool_call_only_after_local_policy_check() -> None:
    class ToolAdapter:
        is_local = True

        async def generate(self, request: LocalModelRequest) -> str:
            return "unused"

        async def stream(self, request: LocalModelRequest):
            yield "unused"

        async def call_with_tools(self, request: LocalModelRequest) -> ToolCallResult:
            return ToolCallResult("proposal", (ToolCall("lookup", {"key": "sample"}),))

    gateway = ModelGateway(adapters={"ollama": ToolAdapter()}, policy=LocalOnlyPolicy())
    result = asyncio.run(gateway.call_with_tools(tool_request()))

    assert result.tool_calls[0].name == "lookup"


def test_gateway_fails_explicitly_when_adapter_has_no_tool_call_capability() -> None:
    class TextOnlyAdapter:
        is_local = True

        async def generate(self, request: LocalModelRequest) -> str:
            return "text only"

        async def stream(self, request: LocalModelRequest):
            yield "text only"

    gateway = ModelGateway(adapters={"text": TextOnlyAdapter()}, policy=LocalOnlyPolicy())

    with pytest.raises(ProviderCapabilityUnsupported, match="tool calls"):
        asyncio.run(gateway.call_with_tools(tool_request(provider="text")))


def test_local_only_gateway_denies_remote_tool_call_before_adapter() -> None:
    class RemoteToolAdapter:
        is_local = False
        calls = 0

        async def generate(self, request: LocalModelRequest) -> str:
            raise AssertionError("remote adapter must not be called")

        async def stream(self, request: LocalModelRequest):
            raise AssertionError("remote adapter must not be called")
            yield "unreachable"

        async def call_with_tools(self, request: LocalModelRequest) -> ToolCallResult:
            self.calls += 1
            raise AssertionError("remote adapter must not be called")

    adapter = RemoteToolAdapter()
    gateway = ModelGateway(adapters={"ollama": adapter}, policy=LocalOnlyPolicy())

    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.call_with_tools(tool_request()))
    assert adapter.calls == 0
