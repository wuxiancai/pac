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
from probe_remote_provider_poc import PROBE_ACK, PROBE_PROMPT, PROBE_PURPOSE


CONFIGS = (DEEPSEEK_PROBE_CONFIG, OPENROUTER_PROBE_CONFIG)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sequential same-Gateway Provider switch proof with separate consent"
    )
    parser.parse_args()

    consent = ConsentManager()
    gateway = ModelGateway(
        adapters={
            config.provider: OpenAICompatibleRemoteAdapter(
                config,
                credentials=MacOSKeychainCredentialProvider(),
            )
            for config in CONFIGS
        },
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )
    print("同一个 ModelGateway 实例依次路由到两个 Provider；不是自动 failover。")
    print("每个 Provider 都须单独确认；拒绝或失败不会触发另一家代发。")
    outcomes: list[bool] = []

    for config in CONFIGS:
        confirmation = f"ALLOW {config.provider.upper()}"
        print(f"\nProvider: {config.provider}")
        print(f"Model: {config.model}")
        print(f"Region: {config.region}")
        print(f"Purpose: {PROBE_PURPOSE}")
        print("Data level: L1 (synthetic text only)")
        print(f"Payload: {PROBE_PROMPT}")
        print("最大输出 64 tokens；单次非流式请求；不带工具、不重试。")
        answer = input(f"若同意现在向该 Provider 发送以上内容，请输入 `{confirmation}`：")
        if answer.strip() != confirmation:
            print("本次未获确认；未读取该 Provider Keychain 凭据，也未发送请求。")
            outcomes.append(False)
            continue

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
            outcomes.append(False)
        except Exception as exc:  # noqa: BLE001 - suppress transport details
            print(f"探测未完成：{type(exc).__name__}；未输出密钥或响应正文。")
            outcomes.append(False)
        else:
            matched = result.text.strip() == PROBE_ACK
            print(f"响应精确匹配: {matched}")
            print(f"实际模型: {result.model}")
            print(f"实际下游 Provider: {result.provider or '服务未返回'}")
            print(f"服务区域信息: {result.region or '服务未返回'}")
            outcomes.append(matched)
        finally:
            consent.revoke(config.provider, config.model, config.region, PROBE_PURPOSE)

    if all(outcomes):
        print("\n同一 Gateway 的两条独立 Provider 路由均成功。")
        return 0
    print("\n切换验证未全部通过；请按各 Provider 输出判断，不会自动补发。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
