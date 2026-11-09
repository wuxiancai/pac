from __future__ import annotations

import asyncio
import json
import math
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from pac_poc.keychain_credentials import CredentialProvider
from pac_poc.model_gateway import (
    LocalModelRequest,
    ProviderStreamChunk,
    ToolCall,
    ToolCallResult,
)


@dataclass(frozen=True)
class RemoteProviderConfig:
    provider: str
    account: str
    model: str
    region: str
    endpoint: str


DEEPSEEK_PROBE_CONFIG = RemoteProviderConfig(
    provider="deepseek",
    account="deepseek",
    model="deepseek-flash",
    region="china",
    endpoint="https://api.deepseek.com/chat/completions",
)

OPENROUTER_PROBE_CONFIG = RemoteProviderConfig(
    provider="openrouter",
    account="openrouter",
    model="deepseek/deepseek-v4.1-flash-1017",
    region="global",
    endpoint="https://openrouter.ai/api/v1/chat/completions",
)

QWEN_TOKEN_PLAN_PROBE_CONFIG = RemoteProviderConfig(
    provider="qwen",
    account="qwen",
    model="qwen3.8-flash",
    region="china-beijing",
    endpoint=(
        "https://token-plan.maas.qianwenaiapi.com/"
        "compatible-mode/v1/chat/completions"
    ),
)

QWEN_APP_API_CONFIG = RemoteProviderConfig(
    provider="qwen-app",
    account="qwen-app",
    model="qwen3.8-flash",
    region="china",
    endpoint="https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions",
)


@dataclass(frozen=True)
class RemoteCompletion:
    text: str
    model: str
    provider: str | None
    region: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_prompt_tokens: int | None
    total_tokens: int | None
    cost_usd: float | None
    finish_reason: str | None = None


class RemoteProviderError(RuntimeError):
    """Sanitized Provider error; response bodies and credentials are not retained."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    @property
    def is_client_error(self) -> bool:
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_authentication_error(self) -> bool:
        return self.status_code == 401

    @property
    def is_request_validation_error(self) -> bool:
        return self.status_code in {400, 422}


class OpenAICompatibleRemoteAdapter:
    """Fixed-endpoint OpenAI chat-completions adapter for Phase 0 remote probes."""

    is_local = False
    _MAX_ATTEMPTS = 2
    _RETRY_DELAY_SECONDS = 0.25
    _PRE_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)

    def __init__(
        self,
        config: RemoteProviderConfig,
        *,
        credentials: CredentialProvider,
        client: httpx.AsyncClient | None = None,
        max_output_tokens: int = 64,
    ) -> None:
        parsed = urlsplit(config.endpoint)
        expected_hosts = {
            "deepseek": "api.deepseek.com",
            "openrouter": "openrouter.ai",
            "qwen": "token-plan.maas.qianwenaiapi.com",
            "qwen-app": "maas.qianwenaiapi.com",
        }
        expected_configs = {
            DEEPSEEK_PROBE_CONFIG.provider: DEEPSEEK_PROBE_CONFIG,
            OPENROUTER_PROBE_CONFIG.provider: OPENROUTER_PROBE_CONFIG,
            QWEN_TOKEN_PLAN_PROBE_CONFIG.provider: QWEN_TOKEN_PLAN_PROBE_CONFIG,
            QWEN_APP_API_CONFIG.provider: QWEN_APP_API_CONFIG,
        }
        if (
            config.provider not in expected_hosts
            or parsed.scheme != "https"
            or parsed.hostname != expected_hosts[config.provider]
            or parsed.query
            or parsed.fragment
            or config != expected_configs.get(config.provider)
        ):
            raise ValueError("remote Provider configuration is not allowlisted")
        if not config.account or not config.model or not config.region:
            raise ValueError("remote Provider identity must be complete")
        if not 1 <= max_output_tokens <= 4096:
            raise ValueError("max_output_tokens is outside the supported range")
        self._config = config
        self._credentials = credentials
        self._client = client
        self._max_output_tokens = max_output_tokens

    async def generate(self, request: LocalModelRequest) -> str:
        return (await self.generate_with_metadata(request)).text

    async def generate_with_metadata(self, request: LocalModelRequest) -> RemoteCompletion:
        response = await self._post(request, stream=False)
        payload = self._json_object(response)
        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RemoteProviderError("Provider returned an invalid chat response") from exc
        if not isinstance(content, str):
            raise RemoteProviderError("Provider returned non-text content")
        usage = payload.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        provider, region = self._openrouter_route(payload)
        choice = payload["choices"][0]
        finish_reason = choice.get("finish_reason")
        cost_usd = (
            self._optional_nonnegative_number(usage.get("cost"))
            if self._config.provider == "openrouter"
            else None
        )
        response_model = payload.get("model")
        if not isinstance(response_model, str):
            response_model = self._config.model
        return RemoteCompletion(
            text=content,
            model=response_model,
            provider=provider,
            region=region,
            prompt_tokens=self._optional_nonnegative_int(usage.get("prompt_tokens")),
            completion_tokens=self._optional_nonnegative_int(usage.get("completion_tokens")),
            cached_prompt_tokens=self._cached_prompt_tokens(usage),
            total_tokens=self._optional_nonnegative_int(usage.get("total_tokens")),
            cost_usd=cost_usd,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
        )

    async def stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        async for chunk in self.stream_with_usage(request):
            if chunk.text:
                yield chunk.text

    async def stream_with_usage(
        self, request: LocalModelRequest
    ) -> AsyncIterator[ProviderStreamChunk]:
        self._validate_request(request)
        secret = self._credential_for_request()
        client, owns_client = self._client_or_new()
        try:
            for attempt in range(self._MAX_ATTEMPTS):
                try:
                    async with client.stream(
                        "POST",
                        self._config.endpoint,
                        headers=self._headers_for_request(secret),
                        json=self._payload(request, stream=True),
                    ) as response:
                        retry_delay = (
                            self._rate_limit_retry_delay(response)
                            if response.status_code == 429
                            and attempt + 1 < self._MAX_ATTEMPTS
                            else None
                        )
                        if retry_delay is None:
                            self._raise_for_status(response)
                            async for line in response.aiter_lines():
                                if not line or not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    event = json.loads(data)
                                    raw_usage = event.get("usage")
                                    usage = raw_usage if isinstance(raw_usage, dict) else {}
                                    prompt_tokens = self._optional_nonnegative_int(usage.get("prompt_tokens"))
                                    completion_tokens = self._optional_nonnegative_int(usage.get("completion_tokens"))
                                    cached_prompt_tokens = self._cached_prompt_tokens(usage)
                                    cost_amount = (
                                        self._optional_nonnegative_number(usage.get("cost"))
                                        if self._config.provider == "openrouter"
                                        else None
                                    )
                                    choices = event.get("choices")
                                    if choices == [] and (
                                        prompt_tokens is not None
                                        or completion_tokens is not None
                                        or cached_prompt_tokens is not None
                                        or cost_amount is not None
                                    ):
                                        content = ""
                                    else:
                                        content = choices[0]["delta"].get("content", "")
                                except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError) as exc:
                                    raise RemoteProviderError("Provider returned an invalid stream event") from exc
                                if (
                                    content
                                    or prompt_tokens is not None
                                    or completion_tokens is not None
                                    or cached_prompt_tokens is not None
                                    or cost_amount is not None
                                ):
                                    if not isinstance(content, str):
                                        raise RemoteProviderError("Provider returned non-text stream content")
                                    yield ProviderStreamChunk(
                                        text=content,
                                        prompt_tokens=prompt_tokens,
                                        completion_tokens=completion_tokens,
                                        cached_prompt_tokens=cached_prompt_tokens,
                                        cost_amount=cost_amount,
                                        cost_currency="USD" if cost_amount is not None else None,
                                    )
                    if retry_delay is not None:
                        await asyncio.sleep(retry_delay)
                        continue
                    return
                except self._PRE_CONNECT_ERRORS:
                    if attempt + 1 >= self._MAX_ATTEMPTS:
                        raise
                    await asyncio.sleep(self._RETRY_DELAY_SECONDS)
        finally:
            if owns_client:
                await client.aclose()

    async def call_with_tools(self, request: LocalModelRequest) -> ToolCallResult:
        if not request.tools:
            raise ValueError("tool call request must include at least one tool schema")
        payload = self._json_object(await self._post(request, stream=False))
        try:
            message = payload["choices"][0]["message"]
            text = message.get("content") or ""
            raw_calls = message.get("tool_calls") or []
            if not isinstance(text, str) or not isinstance(raw_calls, list):
                raise TypeError
            calls: list[ToolCall] = []
            for raw_call in raw_calls:
                function = raw_call["function"]
                name = function["name"]
                arguments = json.loads(function["arguments"])
                if not isinstance(name, str) or not name or not isinstance(arguments, dict):
                    raise TypeError
                calls.append(ToolCall(name=name, arguments=arguments))
            finish_reason = payload["choices"][0].get("finish_reason")
            provider, region = self._openrouter_route(payload)
            return ToolCallResult(
                text=text,
                tool_calls=tuple(calls),
                finish_reason=(finish_reason if isinstance(finish_reason, str) else None),
                model=(payload.get("model") if isinstance(payload.get("model"), str) else self._config.model),
                provider=provider,
                region=region,
            )
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RemoteProviderError("Provider returned invalid tool-call data") from exc

    async def _post(self, request: LocalModelRequest, *, stream: bool) -> httpx.Response:
        self._validate_request(request)
        secret = self._credential_for_request()
        client, owns_client = self._client_or_new()
        try:
            for attempt in range(self._MAX_ATTEMPTS):
                try:
                    response = await client.post(
                        self._config.endpoint,
                        headers=self._headers_for_request(secret),
                        json=self._payload(request, stream=stream),
                    )
                except self._PRE_CONNECT_ERRORS:
                    if attempt + 1 >= self._MAX_ATTEMPTS:
                        raise
                    await asyncio.sleep(self._RETRY_DELAY_SECONDS)
                    continue
                try:
                    self._raise_for_status(response)
                except RemoteProviderError as exc:
                    if exc.status_code != 429 or attempt + 1 >= self._MAX_ATTEMPTS:
                        raise
                    retry_delay = self._rate_limit_retry_delay(response)
                    if retry_delay is None:
                        raise
                    await asyncio.sleep(retry_delay)
                    continue
                return response
            raise RemoteProviderError("Provider request failed after bounded retries")
        finally:
            if owns_client:
                await client.aclose()

    def _validate_request(self, request: LocalModelRequest) -> None:
        if (
            request.provider != self._config.provider
            or request.model != self._config.model
            or request.region != self._config.region
        ):
            raise ValueError("request does not match the fixed Provider/model/region")

    @staticmethod
    def _headers(secret: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
        }

    def _credential_for_request(self) -> str:
        secret = self._credentials.get(self._config.account)
        if self._config.provider == "qwen" and not secret.startswith("sk-sp-"):
            raise RemoteProviderError(
                "Token Plan requires its dedicated API key; refusing to send request"
            )
        if self._config.provider == "qwen-app" and not secret.startswith("sk-ws-"):
            raise RemoteProviderError(
                "Qwen application API requires its separate pay-as-you-go key; refusing to send request"
            )
        return secret

    def _headers_for_request(self, secret: str) -> dict[str, str]:
        headers = self._headers(secret)
        if self._config.provider == "openrouter":
            headers["X-OpenRouter-Metadata"] = "enabled"
        return headers

    def _payload(self, request: LocalModelRequest, *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._config.model,
            "messages": list(request.messages),
            "stream": stream,
            "max_tokens": self._max_output_tokens,
        }
        if stream:
            payload["stream_options"] = {"include_usage": True}
        if request.tools:
            payload["tools"] = list(request.tools)
        if request.tool_choice is not None:
            payload["tool_choice"] = (
                dict(request.tool_choice)
                if isinstance(request.tool_choice, Mapping)
                else request.tool_choice
            )
        if request.thinking_enabled is not None and self._config.provider == "deepseek":
            payload["thinking"] = {
                "type": "enabled" if request.thinking_enabled else "disabled"
            }
        if request.response_format is not None:
            payload["response_format"] = dict(request.response_format)
        if self._config.provider == "openrouter":
            # OpenRouter otherwise enables cross-provider failover by default.
            payload["provider"] = {"allow_fallbacks": False}
            if request.tools:
                # Avoid endpoints that silently ignore tools/tool_choice.
                payload["provider"]["require_parameters"] = True
        return payload

    @staticmethod
    def _json_object(response: httpx.Response) -> Mapping[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RemoteProviderError("Provider returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteProviderError("Provider returned invalid JSON")
        return payload

    def _openrouter_route(self, payload: Mapping[str, Any]) -> tuple[str | None, str | None]:
        if self._config.provider != "openrouter":
            return None, None
        metadata = payload.get("openrouter_metadata")
        if not isinstance(metadata, dict):
            return None, None
        region = metadata.get("region") if isinstance(metadata.get("region"), str) else None
        endpoints = metadata.get("endpoints")
        available = endpoints.get("available") if isinstance(endpoints, dict) else None
        if isinstance(available, list):
            selected = next(
                (
                    endpoint
                    for endpoint in available
                    if isinstance(endpoint, dict) and endpoint.get("selected") is True
                ),
                None,
            )
            provider = (
                selected.get("provider")
                if selected is not None and isinstance(selected.get("provider"), str)
                else None
            )
            return provider, region
        return None, region

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_error:
            # Deliberately discard provider response bodies; they may echo request data.
            status_code = response.status_code
            if status_code == 401:
                message = "Provider rejected API credentials (HTTP 401)"
            elif status_code == 402:
                message = "Provider account requires payment or has insufficient balance (HTTP 402)"
            elif status_code == 403:
                message = "Provider denied access or permission (HTTP 403)"
            elif status_code == 429:
                message = "Provider rate limit reached (HTTP 429)"
            else:
                message = f"Provider request failed with HTTP {status_code}"
            raise RemoteProviderError(
                message,
                status_code=status_code,
            )

    @classmethod
    def _rate_limit_retry_delay(cls, response: httpx.Response) -> float | None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is None:
            return cls._RETRY_DELAY_SECONDS
        try:
            delay = float(retry_after)
        except ValueError:
            return None
        if not math.isfinite(delay) or delay < 0 or delay > 2.0:
            return None
        return delay

    def _client_or_new(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        return httpx.AsyncClient(timeout=45.0), True

    @staticmethod
    def _optional_nonnegative_int(value: object) -> int | None:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
        return None

    def _cached_prompt_tokens(self, usage: Mapping[str, Any]) -> int | None:
        prompt_tokens = self._optional_nonnegative_int(usage.get("prompt_tokens"))
        if self._config.provider == "deepseek":
            cached_tokens = self._optional_nonnegative_int(
                usage.get("prompt_cache_hit_tokens")
            )
        else:
            details = usage.get("prompt_tokens_details")
            if not isinstance(details, dict):
                return None
            cached_tokens = self._optional_nonnegative_int(details.get("cached_tokens"))
        if (
            prompt_tokens is None
            or cached_tokens is None
            or cached_tokens > prompt_tokens
        ):
            return None
        return cached_tokens

    @staticmethod
    def _optional_nonnegative_number(value: object) -> float | None:
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                number = float(value)
            except (OverflowError, ValueError):
                return None
            if math.isfinite(number) and number >= 0:
                return number
        return None
