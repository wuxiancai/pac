from __future__ import annotations

import argparse
import asyncio
import json
import time

import httpx

from pac_poc.keychain_credentials import (
    CredentialUnavailable,
    MacOSKeychainCredentialProvider,
)
from pac_poc.model_gateway import (
    ConsentAwarePolicy,
    LocalModelRequest,
    ModelGateway,
    PolicyDenied,
    ToolCallResult,
)
from pac_poc.remote_providers import (
    DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG,
    OpenAICompatibleRemoteAdapter,
    RemoteProviderConfig,
    RemoteProviderError,
)
from pac_poc.security_poc import ConsentGrant, ConsentManager, DataLevel, OutboundPolicy
from probe_remote_provider_poc import PROBE_ACK, PROBE_PROMPT, PROBE_PURPOSE


CONFIGS = {
    DEEPSEEK_PROBE_CONFIG.provider: DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG.provider: OPENROUTER_PROBE_CONFIG,
}
CAPABILITIES = ("stream", "cancel", "tools", "json", "error", "metadata", "deny-check")
TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "phase0_echo_synthetic",
        "description": "Return the supplied synthetic phase0 marker as a proposal only.",
        "parameters": {
            "type": "object",
            "properties": {"marker": {"type": "string"}},
            "required": ["marker"],
            "additionalProperties": False,
        },
    },
}


class _CredentialTripwire:
    def __init__(self) -> None:
        self.reads = 0

    def get(self, _account: str) -> str:
        self.reads += 1
        raise AssertionError("denied request must not read credentials")


def _request(config: RemoteProviderConfig, capability: str) -> LocalModelRequest:
    prompt = PROBE_PROMPT
    tools = ()
    response_format = None
    if capability in {"stream", "cancel"}:
        prompt = PROBE_PROMPT
    elif capability == "tools":
        prompt = (
            "Call phase0_echo_synthetic exactly once with marker "
            f"{PROBE_ACK}. Do not execute anything."
        )
        tools = (TOOL_SCHEMA,)
    elif capability == "json":
        prompt = 'Return exactly one JSON object with key "phase0" and value "ack".'
        response_format = {"type": "json_object"}
    elif capability == "error":
        prompt = "This request intentionally carries an invalid response_format for error handling."
        response_format = {"type": "phase0_intentionally_invalid"}
    return LocalModelRequest(
        provider=config.provider,
        model=config.model,
        messages=({"role": "user", "content": prompt},),
        region=config.region,
        purpose=PROBE_PURPOSE,
        data_level=DataLevel.L1,
        tools=tools,
        response_format=response_format,
        tool_choice=(
            {"type": "function", "function": {"name": "phase0_echo_synthetic"}}
            if capability == "tools"
            else None
        ),
        thinking_enabled=(
            False if capability == "tools" and config.provider == "deepseek" else None
        ),
    )


def run_denial_check(config: RemoteProviderConfig) -> bool:
    credentials = _CredentialTripwire()
    network_calls = 0

    def transport_tripwire(_request: httpx.Request) -> httpx.Response:
        nonlocal network_calls
        network_calls += 1
        raise AssertionError("denied request reached HTTP transport")

    client = httpx.AsyncClient(transport=httpx.MockTransport(transport_tripwire))
    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=credentials,
        client=client,
    )
    gateway = ModelGateway(
        adapters={config.provider: adapter},
        policy=ConsentAwarePolicy(OutboundPolicy(ConsentManager())),
    )
    async def attempt_without_consent() -> None:
        try:
            await gateway.generate(_request(config, "metadata"))
        except PolicyDenied:
            return
        raise AssertionError("request without Consent was not denied")

    async def check() -> None:
        try:
            await attempt_without_consent()
        finally:
            await client.aclose()

    asyncio.run(check())
    return credentials.reads == 0 and network_calls == 0


def _grant(consent: ConsentManager, config: RemoteProviderConfig) -> None:
    consent.grant(
        ConsentGrant(
            provider=config.provider,
            model=config.model,
            region=config.region,
            purpose=PROBE_PURPOSE,
            data_levels=frozenset({DataLevel.L1}),
            expires_at=time.time() + 60,
        )
    )


def _print_metadata(result, index: int) -> None:
    matches = result.text.strip() == PROBE_ACK
    print(f"请求 {index} 响应精确匹配: {matches}")
    if not matches:
        print(f"响应正文: {json.dumps(result.text, ensure_ascii=False)}")
    print(f"实际模型: {result.model}")
    print(f"实际下游 Provider: {result.provider or '服务未返回'}")
    print(f"服务区域信息: {result.region or '服务未返回'}")
    print(
        "Token 用量: "
        f"prompt={result.prompt_tokens}, completion={result.completion_tokens}, "
        f"total={result.total_tokens}"
    )
    print(f"服务报告费用（USD）: {result.cost_usd if result.cost_usd is not None else '未提供'}")


def _print_response_diagnostics(result) -> None:
    print(f"Finish reason: {result.finish_reason or '服务未返回'}")
    print(f"实际模型: {result.model}")
    print(f"实际下游 Provider: {result.provider or '服务未返回'}")
    print(f"服务区域信息: {result.region or '服务未返回'}")
    print(
        "Token 用量: "
        f"prompt={result.prompt_tokens}, completion={result.completion_tokens}, "
        f"total={result.total_tokens}"
    )
    print(f"服务报告费用（USD）: {result.cost_usd if result.cost_usd is not None else '未提供'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One capability probe per exact Provider consent"
    )
    parser.add_argument("provider", choices=tuple(CONFIGS))
    parser.add_argument("capability", choices=CAPABILITIES)
    parser.add_argument(
        "--repeat",
        type=int,
        default=None,
        help="metadata mode only: independently confirm and send this many requests (default 2)",
    )
    args = parser.parse_args()
    config = CONFIGS[args.provider]

    if args.capability == "deny-check":
        print("本地 Consent 拒绝检查；使用网络 tripwire，不读取 Keychain，也不连接 Provider。")
        passed = run_denial_check(config)
        print(f"无 Consent 时 Keychain 读取次数=0，HTTP transport 调用次数=0: {passed}")
        return 0 if passed else 1
    if args.repeat is not None and args.capability != "metadata":
        parser.error("--repeat 仅用于 metadata")
    request_count = (args.repeat or 2) if args.capability == "metadata" else 1
    if request_count < 1:
        parser.error("--repeat 至少为 1")
    consent = ConsentManager()
    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=MacOSKeychainCredentialProvider(),
    )
    gateway = ModelGateway(
        adapters={config.provider: adapter},
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )
    request = _request(config, args.capability)
    all_passed = True

    for index in range(1, request_count + 1):
        confirmation = f"ALLOW {config.provider.upper()} {args.capability.upper()} {index}"
        print(f"Provider: {config.provider}")
        print(f"Model: {config.model}")
        print(f"Region: {config.region}")
        print(f"Purpose: {PROBE_PURPOSE}")
        print("Data level: L1 (synthetic text only)")
        print(f"Capability: {args.capability}")
        print(f"Payload: {request.messages[0]['content']}")
        if args.capability == "tools":
            print("工具调用只作为模型提案显示；本脚本不会执行该工具。")
            if request.thinking_enabled is False:
                print("DeepSeek 本次显式关闭 thinking，以支持指定 tool_choice。")
            if config.provider == "openrouter":
                print("OpenRouter 仅选择支持本次 tools/tool_choice 参数的端点，且不启用 Provider fallback。")
            print(f"Tool schema: {json.dumps(list(request.tools), ensure_ascii=False)}")
            print(f"tool_choice: {json.dumps(request.tool_choice, ensure_ascii=False)}")
        elif args.capability == "error":
            print("此项故意发送无效 response_format，以观察 Provider HTTP 错误；服务仍可能计费，不会重试。")
        elif args.capability == "cancel":
            print("本次会启动一条真实 SSE 请求，收到首个文本片段后立即关闭客户端流；可能产生费用，不会重试。")
            print("客户端可证明关闭本地流；Provider 是否及时停止生成/计费，需看服务端是否提供记录。")
        elif args.capability == "metadata":
            print("用于费用/区域重复观察；每次都是独立请求，可能产生费用。")
        print(f"若同意本次请求，请输入 `{confirmation}`：")
        if input().strip() != confirmation:
            print("未获本次确认；未读取 Keychain，也未发送请求。")
            all_passed = False
            continue

        _grant(consent, config)
        try:
            if args.capability == "stream":
                async def collect() -> str:
                    parts = [part async for part in gateway.stream(request)]
                    return "".join(parts)

                text = asyncio.run(collect())
                passed = text.strip() == PROBE_ACK
                print(f"流式响应: {text}")
                print(f"精确匹配: {passed}")
            elif args.capability == "cancel":
                async def cancel_after_first_chunk() -> str:
                    stream = gateway.stream(request)
                    try:
                        return await anext(stream)
                    finally:
                        await stream.aclose()

                first_chunk = asyncio.run(cancel_after_first_chunk())
                print(f"首个文本片段: {json.dumps(first_chunk, ensure_ascii=False)}")
                print("客户端流已主动关闭。")
                passed = bool(first_chunk)
            elif args.capability == "tools":
                result: ToolCallResult = asyncio.run(gateway.call_with_tools(request))
                calls = [
                    {"name": call.name, "arguments": dict(call.arguments)}
                    for call in result.tool_calls
                ]
                print(f"工具调用提案（未执行）: {json.dumps(calls, ensure_ascii=False)}")
                print(f"Finish reason: {result.finish_reason or '服务未返回'}")
                print(f"实际模型: {result.model or config.model}")
                print(f"实际下游 Provider: {result.provider or '服务未返回'}")
                print(f"服务区域信息: {result.region or '服务未返回'}")
                if not calls:
                    print(f"模型文本响应: {result.text or '（空）'}")
                passed = any(call["name"] == "phase0_echo_synthetic" for call in calls)
            elif args.capability == "error":
                try:
                    asyncio.run(gateway.generate_with_metadata(request))
                except RemoteProviderError as exc:
                    print(f"Provider 返回已脱敏错误: {exc}")
                    passed = exc.is_client_error
                    if passed:
                        print("错误路径验证通过：Provider 返回 4xx 客户端错误。")
                else:
                    print("Provider 接受了预期无效格式；未观察到 4xx 错误。")
                    passed = False
            else:
                result = asyncio.run(gateway.generate_with_metadata(request))
                if args.capability == "json":
                    try:
                        parsed = json.loads(result.text)
                    except json.JSONDecodeError:
                        parsed = None
                    passed = isinstance(parsed, dict) and parsed.get("phase0") == "ack"
                    print(f"JSON 响应: {result.text}")
                    print(f"符合探测结构: {passed}")
                    _print_response_diagnostics(result)
                else:
                    _print_metadata(result, index)
                    passed = result.text.strip() == PROBE_ACK
            all_passed = all_passed and passed
        except (CredentialUnavailable, RemoteProviderError, ValueError) as exc:
            print(f"探测失败: {exc}")
            all_passed = False
        except Exception as exc:  # noqa: BLE001 - avoid printing transport/body details
            print(f"探测未完成: {type(exc).__name__}；未输出密钥或响应正文。")
            all_passed = False
        finally:
            consent.revoke(config.provider, config.model, config.region, PROBE_PURPOSE)

    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
