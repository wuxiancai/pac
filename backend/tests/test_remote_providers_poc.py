from __future__ import annotations

import asyncio
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest

from pac_poc.keychain_credentials import (
    CredentialUnavailable,
    MacOSKeychainCredentialProvider,
    PROVIDER_KEYCHAIN_SERVICE,
)
from pac_poc.model_gateway import (
    ConsentAwarePolicy,
    LocalModelRequest,
    ModelGateway,
    ProviderStreamChunk,
    PolicyDenied,
)
from pac_poc.remote_providers import (
    DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG,
    QWEN_APP_API_CONFIG,
    QWEN_TOKEN_PLAN_PROBE_CONFIG,
    OpenAICompatibleRemoteAdapter,
    RemoteProviderConfig,
    RemoteProviderError,
)
from pac_poc.security_poc import (
    ConsentGrant,
    ConsentManager,
    DataLevel,
    ModelAction,
    OutboundPolicy,
)

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
try:
    from probe_provider_capability_poc import _print_metadata, _print_probe_error
finally:
    sys.path.pop(0)


PROBE_SOURCE = "phase0-cli-probe"


class FakeCredentials:
    def __init__(self) -> None:
        self.reads: list[str] = []

    def get(self, account: str) -> str:
        self.reads.append(account)
        return f"test-secret-for-{account}"


def request_for(config=DEEPSEEK_PROBE_CONFIG, **overrides) -> LocalModelRequest:
    fields = {
        "provider": config.provider,
        "model": config.model,
        "messages": ({"role": "user", "content": "phase0 synthetic probe"},),
        "region": config.region,
        "purpose": "phase0-provider-probe",
        "data_level": DataLevel.L1,
        "source": PROBE_SOURCE,
    }
    fields.update(overrides)
    return LocalModelRequest(**fields)


def make_gateway(consent: ConsentManager, adapter, provider: str) -> ModelGateway:
    return ModelGateway(
        adapters={provider: adapter},
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )


def grant_for(
    consent: ConsentManager,
    config=DEEPSEEK_PROBE_CONFIG,
    *,
    actions: frozenset[ModelAction] = frozenset({ModelAction.GENERATE}),
) -> None:
    consent.grant(
        ConsentGrant(
            provider=config.provider,
            model=config.model,
            region=config.region,
            purpose="phase0-provider-probe",
            data_levels=frozenset({DataLevel.L1}),
            action_scopes=actions,
            source_scopes=frozenset({PROBE_SOURCE}),
            expires_at=1e20,
        )
    )


def test_remote_default_deny_prevents_keychain_read_and_network_request() -> None:
    credentials = FakeCredentials()
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": []})

    adapter = OpenAICompatibleRemoteAdapter(
        DEEPSEEK_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    gateway = make_gateway(ConsentManager(), adapter, "deepseek")

    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.generate(request_for()))

    assert credentials.reads == []
    assert requests == []


def test_provider_capability_deny_check_uses_tripwires_and_never_reads_keychain() -> None:
    backend = Path(__file__).parents[1]
    for provider in ("deepseek", "openrouter", "qwen"):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/probe_provider_capability_poc.py",
                provider,
                "deny-check",
            ],
            cwd=backend,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        assert "Keychain 读取次数=0，HTTP transport 调用次数=0: True" in result.stdout


def test_deepseek_text_request_requires_exact_consent_and_uses_keychain_secret() -> None:
    credentials = FakeCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "phase0-probe-accepted"}}]},
        )

    adapter = OpenAICompatibleRemoteAdapter(
        DEEPSEEK_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent)
    gateway = make_gateway(consent, adapter, "deepseek")

    answer = asyncio.run(gateway.generate(request_for()))

    assert answer == "phase0-probe-accepted"
    assert credentials.reads == ["deepseek"]
    assert str(seen[0].url) == DEEPSEEK_PROBE_CONFIG.endpoint
    assert seen[0].headers["authorization"] == "Bearer test-secret-for-deepseek"
    assert seen[0].read() == (
        b'{"model":"deepseek-flash","messages":[{"role":"user",'
        b'"content":"phase0 synthetic probe"}],"stream":false,"max_tokens":64}'
    )


def test_qwen_token_plan_uses_fixed_beijing_endpoint_and_keychain_credential() -> None:
    config = QWEN_TOKEN_PLAN_PROBE_CONFIG
    assert config.endpoint == (
        "https://token-plan.maas.qianwenaiapi.com/"
        "compatible-mode/v1/chat/completions"
    )

    class PlanCredentials(FakeCredentials):
        def get(self, account: str) -> str:
            self.reads.append(account)
            return "sk-sp-test-key"

    credentials = PlanCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "phase0-probe-ack"}}]},
        )

    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent, config)
    gateway = make_gateway(consent, adapter, config.provider)

    result = asyncio.run(gateway.generate(request_for(config)))

    assert result == "phase0-probe-ack"
    assert credentials.reads == ["qwen"]
    assert str(seen[0].url) == config.endpoint
    assert seen[0].headers["authorization"] == "Bearer sk-sp-test-key"
    assert b'"model":"qwen3.8-flash"' in seen[0].read()


def test_qwen_token_plan_refuses_non_plan_credential_before_http_request() -> None:
    config = QWEN_TOKEN_PLAN_PROBE_CONFIG

    class PayAsYouGoCredentials(FakeCredentials):
        def get(self, account: str) -> str:
            self.reads.append(account)
            return "sk-ws-test-key"

    credentials = PayAsYouGoCredentials()
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"choices": []})

    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent, config)
    gateway = make_gateway(consent, adapter, config.provider)

    with pytest.raises(RemoteProviderError, match="dedicated API key"):
        asyncio.run(gateway.generate(request_for(config)))

    assert credentials.reads == ["qwen"]
    assert requests == []


def test_qwen_application_api_uses_separate_endpoint_and_pay_as_you_go_key() -> None:
    config = QWEN_APP_API_CONFIG
    assert config.provider == "qwen-app"
    assert config.account == "qwen-app"
    assert config.model == "qwen3.8-flash"
    assert config.endpoint == (
        "https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions"
    )

    class ApplicationCredentials(FakeCredentials):
        def get(self, account: str) -> str:
            self.reads.append(account)
            return "sk-ws-fresh-application-key"

    credentials = ApplicationCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "qwen-app-ack"}}]},
        )

    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent, config)
    gateway = make_gateway(consent, adapter, config.provider)

    result = asyncio.run(gateway.generate(request_for(config)))

    assert result == "qwen-app-ack"
    assert credentials.reads == ["qwen-app"]
    assert str(seen[0].url) == config.endpoint
    assert seen[0].headers["authorization"] == "Bearer sk-ws-fresh-application-key"
    assert b'"model":"qwen3.8-flash"' in seen[0].read()


def test_qwen_application_api_rejects_token_plan_key_before_network() -> None:
    config = QWEN_APP_API_CONFIG

    class TokenPlanCredentials(FakeCredentials):
        def get(self, account: str) -> str:
            self.reads.append(account)
            return "sk-sp-token-plan-key"

    credentials = TokenPlanCredentials()
    requests: list[httpx.Request] = []
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200, json={"choices": []})
        )
    )
    adapter = OpenAICompatibleRemoteAdapter(config, credentials=credentials, client=client)
    consent = ConsentManager()
    grant_for(consent, config)
    gateway = make_gateway(consent, adapter, config.provider)

    with pytest.raises(RemoteProviderError, match="pay-as-you-go key"):
        asyncio.run(gateway.generate(request_for(config)))

    assert credentials.reads == ["qwen-app"]
    assert requests == []
    asyncio.run(client.aclose())


def test_openrouter_stream_uses_global_endpoint_and_parses_sse() -> None:
    credentials = FakeCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=(
                b'data: {"choices":[{"delta":{"content":"phase0"}}]}\n\n'
                b'data: {"choices":[{"delta":{"content":"-stream"}}]}\n\n'
                b'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":2,"total_tokens":9,"cost":0.0012}}\n\n'
                b"data: [DONE]\n\n"
            ),
        )

    adapter = OpenAICompatibleRemoteAdapter(
        OPENROUTER_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent, OPENROUTER_PROBE_CONFIG, actions=frozenset({ModelAction.STREAM}))
    gateway = make_gateway(consent, adapter, "openrouter")

    async def collect() -> list[ProviderStreamChunk]:
        return [chunk async for chunk in gateway.stream_with_usage(request_for(OPENROUTER_PROBE_CONFIG))]

    assert asyncio.run(collect()) == [
        ProviderStreamChunk(text="phase0"),
        ProviderStreamChunk(text="-stream"),
        ProviderStreamChunk(
            text="", prompt_tokens=7, completion_tokens=2,
            cost_amount=0.0012, cost_currency="USD"
        ),
    ]
    assert str(seen[0].url) == OPENROUTER_PROBE_CONFIG.endpoint
    assert credentials.reads == ["openrouter"]
    assert seen[0].headers["x-openrouter-metadata"] == "enabled"
    assert b'"provider":{"allow_fallbacks":false}' in seen[0].read()
    assert b'"stream_options":{"include_usage":true}' in seen[0].read()


def test_closing_remote_sse_after_first_chunk_closes_response_stream() -> None:
    class PendingSSE(httpx.AsyncByteStream):
        def __init__(self) -> None:
            self.closed = False

        async def __aiter__(self):
            yield b'data: {"choices":[{"delta":{"content":"first"}}]}\n\n'
            await asyncio.Event().wait()

        async def aclose(self) -> None:
            self.closed = True

    credentials = FakeCredentials()
    response_stream = PendingSSE()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                stream=response_stream,
            )
        )
    )
    adapter = OpenAICompatibleRemoteAdapter(
        OPENROUTER_PROBE_CONFIG,
        credentials=credentials,
        client=client,
    )
    consent = ConsentManager()
    grant_for(consent, OPENROUTER_PROBE_CONFIG, actions=frozenset({ModelAction.STREAM}))
    gateway = make_gateway(consent, adapter, "openrouter")

    async def cancel() -> str:
        stream = gateway.stream(request_for(OPENROUTER_PROBE_CONFIG))
        try:
            return await anext(stream)
        finally:
            await stream.aclose()
            await client.aclose()

    assert asyncio.run(cancel()) == "first"
    assert response_stream.closed
    assert credentials.reads == ["openrouter"]


def test_openrouter_metadata_reports_selected_provider_region_usage_and_cost() -> None:
    credentials = FakeCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": OPENROUTER_PROBE_CONFIG.model,
                "choices": [{"message": {"content": "phase0-probe-ack"}}],
                "openrouter_metadata": {
                    "region": "iad",
                    "endpoints": {
                        "available": [
                            {"provider": "DeepSeek", "selected": True},
                            {"provider": "Other", "selected": False},
                        ]
                    },
                },
                "usage": {
                    "prompt_tokens": 12,
                    "completion_tokens": 5,
                    "total_tokens": 17,
                    "cost": 0.000123,
                },
            },
        )

    adapter = OpenAICompatibleRemoteAdapter(
        OPENROUTER_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent, OPENROUTER_PROBE_CONFIG)
    gateway = make_gateway(consent, adapter, "openrouter")

    result = asyncio.run(
        gateway.generate_with_metadata(request_for(OPENROUTER_PROBE_CONFIG))
    )

    assert result.text == "phase0-probe-ack"
    assert result.model == OPENROUTER_PROBE_CONFIG.model
    assert result.provider == "DeepSeek"
    assert result.region == "iad"
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (12, 5, 17)
    assert result.cost_usd == 0.000123
    assert seen[0].headers["x-openrouter-metadata"] == "enabled"
    assert b'"provider":{"allow_fallbacks":false}' in seen[0].read()


def test_one_gateway_routes_sequentially_to_both_providers_with_exact_consents() -> None:
    credentials = FakeCredentials()
    routed: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        routed.append(str(request.url))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "phase0-probe-ack"}}]},
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapters = {
        config.provider: OpenAICompatibleRemoteAdapter(
            config, credentials=credentials, client=client
        )
        for config in (DEEPSEEK_PROBE_CONFIG, OPENROUTER_PROBE_CONFIG)
    }
    consent = ConsentManager()
    gateway = ModelGateway(
        adapters=adapters,
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )

    async def switch() -> list[str]:
        answers = []
        for config in (DEEPSEEK_PROBE_CONFIG, OPENROUTER_PROBE_CONFIG):
            grant_for(consent, config)
            request = request_for(
                config,
                messages=(
                    {
                        "role": "user",
                        "content": "Reply with exactly this text: phase0-probe-ack",
                    },
                ),
            )
            answers.append(
                (await gateway.generate_with_metadata(request)).text
            )
            consent.revoke(
                config.provider, config.model, config.region, "phase0-provider-probe"
            )
        await client.aclose()
        return answers

    answers = asyncio.run(switch())

    assert answers == ["phase0-probe-ack", "phase0-probe-ack"]
    assert routed == [DEEPSEEK_PROBE_CONFIG.endpoint, OPENROUTER_PROBE_CONFIG.endpoint]
    assert credentials.reads == ["deepseek", "openrouter"]


def test_remote_tools_are_returned_as_data_and_never_executed() -> None:
    credentials = FakeCredentials()
    calls = 0
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "synthetic_lookup",
                                        "arguments": '{"key":"phase0"}',
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
        )

    adapter = OpenAICompatibleRemoteAdapter(
        DEEPSEEK_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent, actions=frozenset({ModelAction.TOOL_PROPOSAL}))
    gateway = make_gateway(consent, adapter, "deepseek")
    request = request_for(
        tools=({"type": "function", "function": {"name": "synthetic_lookup"}},),
        tool_choice={"type": "function", "function": {"name": "synthetic_lookup"}},
        thinking_enabled=False,
    )

    result = asyncio.run(gateway.call_with_tools(request))

    assert result.text == ""
    assert [(call.name, call.arguments) for call in result.tool_calls] == [
        ("synthetic_lookup", {"key": "phase0"})
    ]
    assert calls == 1
    assert b'"tool_choice":{"type":"function","function":{"name":"synthetic_lookup"}}' in seen[0].read()
    assert b'"thinking":{"type":"disabled"}' in seen[0].read()


def test_openrouter_tool_probe_requires_parameter_capable_provider_without_fallback() -> None:
    credentials = FakeCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "model": OPENROUTER_PROBE_CONFIG.model,
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "phase0_echo_synthetic",
                                        "arguments": '{"marker":"phase0-probe-ack"}',
                                    }
                                }
                            ],
                        }
                    }
                ],
                "openrouter_metadata": {
                    "region": "hkg",
                    "endpoints": {
                        "available": [{"provider": "Relace", "selected": True}]
                    },
                },
            },
        )

    adapter = OpenAICompatibleRemoteAdapter(
        OPENROUTER_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(
        consent,
        OPENROUTER_PROBE_CONFIG,
        actions=frozenset({ModelAction.TOOL_PROPOSAL}),
    )
    gateway = make_gateway(consent, adapter, "openrouter")
    request = request_for(
        OPENROUTER_PROBE_CONFIG,
        tools=(
            {
                "type": "function",
                "function": {"name": "phase0_echo_synthetic", "parameters": {"type": "object"}},
            },
        ),
        tool_choice={"type": "function", "function": {"name": "phase0_echo_synthetic"}},
    )

    result = asyncio.run(gateway.call_with_tools(request))

    assert result.tool_calls[0].name == "phase0_echo_synthetic"
    assert (result.finish_reason, result.model, result.provider, result.region) == (
        "tool_calls",
        OPENROUTER_PROBE_CONFIG.model,
        "Relace",
        "hkg",
    )
    assert b'"provider":{"allow_fallbacks":false,"require_parameters":true}' in seen[0].read()


def test_structured_response_format_is_forwarded_without_secret_logging() -> None:
    credentials = FakeCredentials()
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": '{"ok":true}'},
                    }
                ],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            },
        )

    adapter = OpenAICompatibleRemoteAdapter(
        DEEPSEEK_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handle)),
    )
    consent = ConsentManager()
    grant_for(consent)
    gateway = make_gateway(consent, adapter, "deepseek")
    request = request_for(response_format={"type": "json_object"})

    result = asyncio.run(gateway.generate_with_metadata(request))

    assert result.text == '{"ok":true}'
    assert result.finish_reason == "stop"
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (12, 3, 15)
    assert b'"response_format":{"type":"json_object"}' in seen[0].read()
    assert credentials.reads == ["deepseek"]


def test_remote_error_is_sanitized_and_does_not_expose_body_or_key() -> None:
    credentials = FakeCredentials()
    adapter = OpenAICompatibleRemoteAdapter(
        DEEPSEEK_PROBE_CONFIG,
        credentials=credentials,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(401, text="invalid test-secret-for-deepseek")
            )
        ),
    )
    consent = ConsentManager()
    grant_for(consent)
    gateway = make_gateway(consent, adapter, "deepseek")

    with pytest.raises(RemoteProviderError, match="HTTP 401") as error:
        asyncio.run(gateway.generate(request_for()))

    assert "test-secret" not in str(error.value)
    assert error.value.status_code == 401
    assert error.value.is_client_error
    assert error.value.is_authentication_error
    assert not error.value.is_request_validation_error
    assert credentials.reads == ["deepseek"]


def test_remote_provider_422_is_classified_as_expected_client_error() -> None:
    error = RemoteProviderError(
        "Provider request failed with HTTP 422",
        status_code=422,
    )

    assert error.is_client_error
    assert error.is_request_validation_error
    assert not error.is_authentication_error
    assert not RemoteProviderError("Provider request failed with HTTP 503", status_code=503).is_client_error
    assert not RemoteProviderError("Provider rejected API credentials", status_code=401).is_request_validation_error
    assert not RemoteProviderError("Provider account requires payment", status_code=402).is_request_validation_error
    assert not RemoteProviderError("Provider rate limit reached", status_code=429).is_request_validation_error
    assert not RemoteProviderError("Provider returned invalid JSON").is_client_error


def test_probe_error_explains_401_as_api_key_authentication_failure(capsys) -> None:
    _print_probe_error(
        RemoteProviderError("Provider rejected API credentials (HTTP 401)", status_code=401)
    )

    output = capsys.readouterr().out
    assert "API Key 认证失败" in output
    assert "Keychain" in output
    assert "密钥内容未读取或显示" in output


def test_probe_error_does_not_label_non_401_status_as_bad_api_key(capsys) -> None:
    _print_probe_error(
        RemoteProviderError("Provider denied access or permission (HTTP 403)", status_code=403)
    )

    output = capsys.readouterr().out
    assert "HTTP 403" in output
    assert "API Key 认证失败" not in output


def test_metadata_probe_prints_json_encoded_text_when_response_mismatches(capsys) -> None:
    _print_metadata(
        SimpleNamespace(
            text="different\nresponse",
            model="deepseek-flash",
            provider=None,
            region=None,
            prompt_tokens=42,
            completion_tokens=3,
            total_tokens=45,
            cost_usd=None,
        ),
        1,
    )

    output = capsys.readouterr().out
    assert "请求 1 响应精确匹配: False" in output
    assert '响应正文: "different\\nresponse"' in output


def test_remote_adapter_rejects_changed_model_region_and_endpoint() -> None:
    with pytest.raises(ValueError, match="not allowlisted"):
        OpenAICompatibleRemoteAdapter(
            RemoteProviderConfig(
                **{**DEEPSEEK_PROBE_CONFIG.__dict__, "endpoint": "https://example.com/chat"}
            ),
            credentials=FakeCredentials(),
        )

    adapter = OpenAICompatibleRemoteAdapter(
        DEEPSEEK_PROBE_CONFIG,
        credentials=FakeCredentials(),
    )
    with pytest.raises(ValueError, match="fixed Provider/model/region"):
        asyncio.run(adapter.generate(request_for(model="other-model")))


def test_keychain_reader_uses_fixed_identity_and_captures_secret_only_in_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pac_poc.keychain_credentials.sys.platform", "darwin")
    seen: list[list[str]] = []

    def runner(args, **kwargs):
        seen.append(args)
        assert kwargs["capture_output"] is True
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 10
        return subprocess.CompletedProcess(args, 0, stdout="test-key\n", stderr="")

    credentials = MacOSKeychainCredentialProvider(runner=runner)

    assert credentials.get("deepseek") == "test-key"
    assert seen == [
        [
            "/usr/bin/security",
            "find-generic-password",
            "-s",
            PROVIDER_KEYCHAIN_SERVICE,
            "-a",
            "deepseek",
            "-w",
        ]
    ]


def test_keychain_reader_never_requests_unknown_account_or_surfaces_cli_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("pac_poc.keychain_credentials.sys.platform", "darwin")
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise subprocess.CalledProcessError(44, "security", stderr="secret must stay private")

    credentials = MacOSKeychainCredentialProvider(runner=runner)

    with pytest.raises(CredentialUnavailable, match="identity is not allowed"):
        credentials.get("unknown")
    assert calls == 0

    with pytest.raises(CredentialUnavailable, match="missing or unavailable") as error:
        credentials.get("deepseek")
    assert "secret" not in str(error.value)
    assert calls == 1
