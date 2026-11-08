from __future__ import annotations

import argparse
import asyncio
import os

import httpx

from pac_poc.keychain_credentials import CredentialUnavailable
from pac_poc.model_gateway import ConsentAwarePolicy, LocalModelRequest, ModelGateway, PolicyDenied
from pac_poc.remote_providers import (
    DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG,
    QWEN_TOKEN_PLAN_PROBE_CONFIG,
    OpenAICompatibleRemoteAdapter,
)
from pac_poc.security_poc import ConsentManager, DataLevel, OutboundPolicy

CONFIGS = {
    DEEPSEEK_PROBE_CONFIG.provider: DEEPSEEK_PROBE_CONFIG,
    OPENROUTER_PROBE_CONFIG.provider: OPENROUTER_PROBE_CONFIG,
    QWEN_TOKEN_PLAN_PROBE_CONFIG.provider: QWEN_TOKEN_PLAN_PROBE_CONFIG,
}


class CredentialReadTripwire:
    def __init__(self) -> None:
        self.reads = 0

    def get(self, _account: str) -> str:
        self.reads += 1
        raise CredentialUnavailable("system denial check forbids credential reads")


async def _attempt(provider: str, observe_seconds: int) -> bool:
    config = CONFIGS[provider]
    credentials = CredentialReadTripwire()
    consent = ConsentManager()
    client = httpx.AsyncClient(timeout=5.0)
    adapter = OpenAICompatibleRemoteAdapter(
        config,
        credentials=credentials,
        client=client,
    )
    gateway = ModelGateway(
        adapters={provider: adapter},
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )
    request = LocalModelRequest(
        provider=provider,
        model=config.model,
        region=config.region,
        purpose="phase0-provider-probe",
        data_level=DataLevel.L1,
        source="phase0-cli-probe",
        messages=({"role": "user", "content": "synthetic denial check"},),
    )
    denied = False
    try:
        print(f"PID: {os.getpid()}", flush=True)
        print(f"Provider: {provider}; no Consent; real HTTPX client; credential tripwire", flush=True)
        print("READY: consent-denied request starts in 3 seconds", flush=True)
        await asyncio.sleep(3)
        try:
            await gateway.generate(request)
        except PolicyDenied:
            denied = True
            print("Policy result: denied before adapter access", flush=True)
        except CredentialUnavailable:
            print("FAIL: credential tripwire was reached", flush=True)
        else:
            print("FAIL: request was not denied", flush=True)
        print(f"Credential reads: {credentials.reads}", flush=True)
        print(f"Observe PID for {observe_seconds} more seconds", flush=True)
        await asyncio.sleep(observe_seconds)
    finally:
        await client.aclose()
    return denied and credentials.reads == 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Observe OS TCP sockets while Consent rejects a synthetic request"
    )
    parser.add_argument("provider", choices=tuple(CONFIGS))
    parser.add_argument("--observe-seconds", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.observe_seconds <= 30:
        parser.error("--observe-seconds must be between 1 and 30")
    passed = asyncio.run(_attempt(args.provider, args.observe_seconds))
    print(f"Policy and credential ordering check passed: {passed}")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
