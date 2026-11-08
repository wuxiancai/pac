from __future__ import annotations

import argparse
import asyncio
import time

from pac_poc.keychain_credentials import (
    CredentialUnavailable,
    MacOSKeychainCredentialProvider,
)
from pac_poc.model_gateway import ConsentAwarePolicy, LocalModelRequest, ModelGateway
from pac_poc.remote_providers import (
    DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG,
    OpenAICompatibleRemoteAdapter,
    RemoteProviderError,
)
from pac_poc.security_poc import ConsentGrant, ConsentManager, DataLevel, OutboundPolicy


PROBE_PURPOSE = "phase0-provider-probe"
PROBE_PROMPT = "Reply with exactly this text: phase0-probe-ack"
PROBE_ACK = "phase0-probe-ack"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One explicitly approved synthetic remote Provider probe"
    )
    parser.add_argument("provider", choices=("deepseek", "openrouter"))
    args = parser.parse_args()
    config = (
        DEEPSEEK_PROBE_CONFIG
        if args.provider == "deepseek"
        else OPENROUTER_PROBE_CONFIG
    )
    confirmation = f"ALLOW {config.provider.upper()}"

    print("单次远端合成探测；不重试、不启用跨 Provider failover、不调用工具。")
    print(f"Provider: {config.provider}")
    print(f"Model: {config.model}")
    print(f"Region: {config.region}")
    print(f"Purpose: {PROBE_PURPOSE}")
    print("Data level: L1 (synthetic text only)")
    print(f"Payload: {PROBE_PROMPT}")
    print("最大输出: 64 tokens；本次只发一个非流式 chat-completions 请求。")
    if config.provider == "openrouter":
        print("OpenRouter Global 会选择一个上游端点；已关闭上游故障切换，响应会报告选中的 Provider 和区域。")
    print(f"凭据只从 macOS Keychain 的 account `{config.account}` 读取；不会显示或记录密钥。")
    answer = input(f"若同意现在向该 Provider 发送以上合成内容，请输入 `{confirmation}`：")
    if answer.strip() != confirmation:
        print("未获本次请求确认；未读取 Keychain，也未发送请求。")
        return 2

    consent = ConsentManager()
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
    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=MacOSKeychainCredentialProvider(),
    )
    gateway = ModelGateway(
        adapters={config.provider: adapter},
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )
    request = LocalModelRequest(
        provider=config.provider,
        model=config.model,
        messages=({"role": "user", "content": PROBE_PROMPT},),
        region=config.region,
        purpose=PROBE_PURPOSE,
        data_level=DataLevel.L1,
    )
    try:
        result = asyncio.run(gateway.generate_with_metadata(request))
    except (CredentialUnavailable, RemoteProviderError, ValueError) as exc:
        print(f"探测失败：{exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - suppress transport details and response data
        print(f"探测未完成：{type(exc).__name__}；未输出密钥或响应正文。")
        return 1
    finally:
        consent.revoke(config.provider, config.model, config.region, PROBE_PURPOSE)

    print(f"响应: {result.text}")
    print(f"实际模型: {result.model}")
    print(f"实际下游 Provider: {result.provider or '服务未返回'}")
    print(f"服务区域信息: {result.region or '服务未返回'}")
    print(
        "Token 用量: "
        f"prompt={result.prompt_tokens}, completion={result.completion_tokens}, "
        f"total={result.total_tokens}"
    )
    print(f"服务报告费用（USD）: {result.cost_usd if result.cost_usd is not None else '未提供'}")
    print(f"精确匹配探测文本: {result.text.strip() == PROBE_ACK}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
