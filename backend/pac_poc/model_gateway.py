from __future__ import annotations

import ipaddress
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from pac_poc.security_poc import (
    ConsentOperationLease,
    DataLevel,
    ModelAction,
    OutboundPolicy,
    OutboundRequest,
)


@dataclass(frozen=True)
class LocalModelRequest:
    provider: str
    model: str
    messages: Sequence[Mapping[str, str]]
    region: str = ""
    purpose: str = ""
    data_level: DataLevel = DataLevel.L0
    source: str = ""
    tools: Sequence[Mapping[str, object]] = ()
    response_format: Mapping[str, object] | None = None
    tool_choice: Mapping[str, object] | str | None = None
    thinking_enabled: bool | None = None


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: Mapping[str, object]


@dataclass(frozen=True)
class ToolCallResult:
    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    model: str | None = None
    provider: str | None = None
    region: str | None = None


@dataclass(frozen=True)
class ProviderStreamChunk:
    """A text delta and optional provider reported usage from the same stream."""

    text: str = ""
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_prompt_tokens: int | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None


class LocalProviderAdapter(Protocol):
    is_local: bool

    async def generate(self, request: LocalModelRequest) -> str: ...

    def stream(self, request: LocalModelRequest) -> AsyncIterator[str]: ...

    async def call_with_tools(self, request: LocalModelRequest) -> ToolCallResult: ...


class ModelRequestPolicy(Protocol):
    def authorize(
        self,
        adapter: LocalProviderAdapter,
        request: LocalModelRequest,
        action: ModelAction,
    ) -> None: ...


class PolicyDenied(PermissionError):
    """The request violates the local-only POC egress policy."""


class ProviderNotFound(LookupError):
    """The requested provider is not registered in the local Gateway."""


class ProviderCapabilityUnsupported(RuntimeError):
    """The selected adapter does not implement the requested capability."""


class LocalOnlyPolicy:
    def authorize(
        self,
        adapter: LocalProviderAdapter,
        request: LocalModelRequest,
        action: ModelAction,
    ) -> None:
        del request, action
        if not adapter.is_local:
            raise PolicyDenied("local-only POC denies non-local providers")


class ConsentAwarePolicy:
    """Allow local adapters; require exact active Consent/Policy for every remote adapter."""

    def __init__(self, outbound_policy: OutboundPolicy) -> None:
        self._outbound_policy = outbound_policy

    def authorize(
        self,
        adapter: LocalProviderAdapter,
        request: LocalModelRequest,
        action: ModelAction,
    ) -> None:
        if adapter.is_local:
            return
        if not request.region.strip() or not request.purpose.strip():
            raise PolicyDenied("remote request requires an explicit region and purpose")
        if not request.source.strip():
            raise PolicyDenied("remote request requires an explicit source scope")
        authorized = self._outbound_policy.authorize(self._outbound_request(request, action))
        if not authorized:
            raise PolicyDenied("remote request lacks matching active Consent and Policy")

    def begin_operation(
        self,
        adapter: LocalProviderAdapter,
        request: LocalModelRequest,
        action: ModelAction,
    ) -> ConsentOperationLease | None:
        if adapter.is_local:
            return None
        if not request.region.strip() or not request.purpose.strip():
            raise PolicyDenied("remote request requires an explicit region and purpose")
        if not request.source.strip():
            raise PolicyDenied("remote request requires an explicit source scope")
        lease = self._outbound_policy.begin_authorized_request(
            self._outbound_request(request, action)
        )
        if lease is None:
            raise PolicyDenied("remote request lacks matching active Consent and Policy")
        return lease

    @staticmethod
    def _outbound_request(
        request: LocalModelRequest, action: ModelAction
    ) -> OutboundRequest:
        return OutboundRequest(
            provider=request.provider,
            model=request.model,
            region=request.region,
            purpose=request.purpose,
            data_level=request.data_level,
            action=action,
            source=request.source,
        )


class ModelGateway:
    """Small local-only routing seam used by the Phase 0 provider POC."""

    def __init__(
        self,
        *,
        adapters: Mapping[str, LocalProviderAdapter],
        policy: ModelRequestPolicy,
    ) -> None:
        self._adapters = dict(adapters)
        self._policy = policy

    async def generate(self, request: LocalModelRequest) -> str:
        adapter = self._get_authorized_adapter(request, ModelAction.GENERATE)
        lease = self._begin_operation(adapter, request, ModelAction.GENERATE)
        try:
            return await adapter.generate(request)
        finally:
            self._close_operation(lease)

    async def generate_with_metadata(self, request: LocalModelRequest) -> Any:
        adapter = self._get_authorized_adapter(request, ModelAction.GENERATE)
        generate_with_metadata = getattr(adapter, "generate_with_metadata", None)
        if not callable(generate_with_metadata):
            raise ProviderCapabilityUnsupported(
                f"provider {request.provider} does not expose response metadata"
            )
        lease = self._begin_operation(adapter, request, ModelAction.GENERATE)
        try:
            return await generate_with_metadata(request)
        finally:
            self._close_operation(lease)

    async def stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        adapter = self._get_authorized_adapter(request, ModelAction.STREAM)
        lease = self._begin_operation(adapter, request, ModelAction.STREAM)
        try:
            stream = adapter.stream(request)
            try:
                async for chunk in stream:
                    yield chunk
            finally:
                close = getattr(stream, "aclose", None)
                if close is not None:
                    await close()
        finally:
            self._close_operation(lease)

    async def stream_with_usage(
        self, request: LocalModelRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        adapter = self._get_authorized_adapter(request, ModelAction.STREAM)
        lease = self._begin_operation(adapter, request, ModelAction.STREAM)
        try:
            stream_with_usage = getattr(adapter, "stream_with_usage", None)
            if callable(stream_with_usage):
                stream = stream_with_usage(request)
                async for chunk in stream:
                    yield chunk
            else:
                stream = adapter.stream(request)
                async for text in stream:
                    yield ProviderStreamChunk(text=text)
        finally:
            try:
                close = getattr(locals().get("stream"), "aclose", None)
                if close is not None:
                    await close()
            finally:
                self._close_operation(lease)

    async def call_with_tools(self, request: LocalModelRequest) -> ToolCallResult:
        adapter = self._get_authorized_adapter(request, ModelAction.TOOL_PROPOSAL)
        call = getattr(adapter, "call_with_tools", None)
        if not callable(call):
            raise ProviderCapabilityUnsupported(
                f"provider {request.provider} does not support tool calls"
            )
        lease = self._begin_operation(adapter, request, ModelAction.TOOL_PROPOSAL)
        try:
            return await call(request)
        finally:
            self._close_operation(lease)

    def _begin_operation(
        self,
        adapter: LocalProviderAdapter,
        request: LocalModelRequest,
        action: ModelAction,
    ) -> ConsentOperationLease | None:
        begin = getattr(self._policy, "begin_operation", None)
        if callable(begin):
            return begin(adapter, request, action)
        return None

    @staticmethod
    def _close_operation(lease: ConsentOperationLease | None) -> None:
        if lease is not None:
            lease.close()

    def _get_authorized_adapter(
        self, request: LocalModelRequest, action: ModelAction
    ) -> LocalProviderAdapter:
        try:
            adapter = self._adapters[request.provider]
        except KeyError as exc:
            raise ProviderNotFound(request.provider) from exc
        self._policy.authorize(adapter, request, action)
        return adapter


class OllamaAdapter:
    """HTTP adapter for an Ollama server bound to this Mac's loopback interface."""

    is_local = True

    def __init__(self, *, base_url: str = "http://127.0.0.1:11434", client: httpx.AsyncClient | None = None) -> None:
        parsed = urlparse(base_url)
        host = parsed.hostname
        if parsed.scheme != "http" or host is None or not self._is_loopback(host):
            raise ValueError("Ollama endpoint must use HTTP on a loopback address")
        self._base_url = base_url.rstrip("/")
        self._client = client

    async def generate(self, request: LocalModelRequest) -> str:
        response = await self._post(request, stream=False)
        payload = response.json()
        try:
            return payload["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise RuntimeError("Ollama returned an invalid chat response") from exc

    async def call_with_tools(self, request: LocalModelRequest) -> ToolCallResult:
        if not request.tools:
            raise ValueError("tool call request must include at least one tool schema")
        response = await self._post(request, stream=False)
        try:
            message = response.json()["message"]
            text = message.get("content", "")
            raw_calls = message.get("tool_calls", [])
            if not isinstance(text, str) or not isinstance(raw_calls, list):
                raise TypeError
            calls: list[ToolCall] = []
            for raw_call in raw_calls:
                function = raw_call["function"]
                name = function["name"]
                arguments = function["arguments"]
                if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                    raise TypeError
                calls.append(ToolCall(name=name, arguments=arguments))
            return ToolCallResult(text=text, tool_calls=tuple(calls))
        except (KeyError, TypeError, AttributeError) as exc:
            raise RuntimeError("Ollama returned an invalid tool-call response") from exc

    async def stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        async for chunk in self.stream_with_usage(request):
            if chunk.text:
                yield chunk.text

    async def stream_with_usage(
        self, request: LocalModelRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        client = self._client or httpx.AsyncClient(timeout=120.0)
        owns_client = self._client is None
        try:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json=self._payload(request, stream=True),
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        event = json.loads(line)
                        content = event.get("message", {}).get("content", "")
                        prompt_tokens = self._optional_nonnegative_int(event.get("prompt_eval_count"))
                        completion_tokens = self._optional_nonnegative_int(event.get("eval_count"))
                    except (json.JSONDecodeError, AttributeError) as exc:
                        raise RuntimeError("Ollama returned an invalid stream event") from exc
                    if content or prompt_tokens is not None or completion_tokens is not None:
                        yield ProviderStreamChunk(
                            text=content,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens,
                        )
        finally:
            if owns_client:
                await client.aclose()

    async def _post(self, request: LocalModelRequest, *, stream: bool) -> httpx.Response:
        if self._client is not None:
            response = await self._client.post(
                f"{self._base_url}/api/chat", json=self._payload(request, stream=stream)
            )
        else:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self._base_url}/api/chat", json=self._payload(request, stream=stream)
                )
        response.raise_for_status()
        return response

    @staticmethod
    def _payload(request: LocalModelRequest, *, stream: bool) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": request.model,
            "messages": list(request.messages),
            "stream": stream,
        }
        if request.tools:
            payload["tools"] = list(request.tools)
        return payload

    @staticmethod
    def _optional_nonnegative_int(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    @staticmethod
    def _is_loopback(host: str) -> bool:
        if host.lower() == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
