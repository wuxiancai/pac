from __future__ import annotations

import asyncio
import time

import pytest

from pac_poc.model_gateway import (
    ConsentAwarePolicy,
    LocalModelRequest,
    ModelGateway,
    PolicyDenied,
    ProviderNotFound,
)
from pac_poc.security_poc import ConsentGrant, ConsentManager, DataLevel, OutboundPolicy


class RemoteProbeAdapter:
    is_local = False

    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LocalModelRequest) -> str:
        self.calls += 1
        return "stubbed response"

    async def stream(self, request: LocalModelRequest):
        self.calls += 1
        yield "stubbed response"


def remote_request(**overrides: object) -> LocalModelRequest:
    fields: dict[str, object] = {
        "provider": "provider-test",
        "model": "model-test",
        "messages": ({"role": "user", "content": "synthetic"},),
        "region": "region-test",
        "purpose": "assistant-response",
        "data_level": DataLevel.L1,
    }
    fields.update(overrides)
    return LocalModelRequest(**fields)  # type: ignore[arg-type]


def make_gateway(consent: ConsentManager, adapter: RemoteProbeAdapter) -> ModelGateway:
    return ModelGateway(
        adapters={"provider-test": adapter},
        policy=ConsentAwarePolicy(OutboundPolicy(consent)),
    )


def test_remote_gateway_denies_by_default_before_adapter_call() -> None:
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(ConsentManager(), adapter)

    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.generate(remote_request()))

    assert adapter.calls == 0


def test_remote_stream_is_denied_before_opening_adapter() -> None:
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(ConsentManager(), adapter)

    async def read_first() -> str:
        return await anext(gateway.stream(remote_request()))

    with pytest.raises(PolicyDenied):
        asyncio.run(read_first())

    assert adapter.calls == 0


def test_remote_request_without_region_or_purpose_is_denied() -> None:
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(ConsentManager(), adapter)
    request = remote_request(region="", purpose="")

    with pytest.raises(PolicyDenied, match="explicit region and purpose"):
        asyncio.run(gateway.generate(request))

    assert adapter.calls == 0


def test_remote_gateway_allows_only_exact_live_consent() -> None:
    consent = ConsentManager()
    consent.grant(
        ConsentGrant(
            provider="provider-test",
            model="model-test",
            region="region-test",
            purpose="assistant-response",
            data_levels=frozenset({DataLevel.L1}),
            expires_at=time.time() + 60,
        )
    )
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    result = asyncio.run(gateway.generate(remote_request()))

    assert result == "stubbed response"
    assert adapter.calls == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "other-provider"},
        {"model": "other-model"},
        {"region": "other-region"},
        {"purpose": "other-purpose"},
        {"data_level": DataLevel.L2},
        {"data_level": DataLevel.L3},
    ],
)
def test_remote_gateway_denies_consent_mismatch(overrides: dict[str, object]) -> None:
    consent = ConsentManager()
    consent.grant(
        ConsentGrant(
            provider="provider-test",
            model="model-test",
            region="region-test",
            purpose="assistant-response",
            data_levels=frozenset({DataLevel.L1}),
            expires_at=time.time() + 60,
        )
    )
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    with pytest.raises((PolicyDenied, ProviderNotFound)):
        asyncio.run(gateway.generate(remote_request(**overrides)))

    assert adapter.calls == 0


def test_revocation_blocks_next_remote_gateway_request() -> None:
    consent = ConsentManager()
    consent.grant(
        ConsentGrant(
            provider="provider-test",
            model="model-test",
            region="region-test",
            purpose="assistant-response",
            data_levels=frozenset({DataLevel.L1}),
            expires_at=time.time() + 60,
        )
    )
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)
    assert asyncio.run(gateway.generate(remote_request())) == "stubbed response"

    assert consent.revoke("provider-test", "model-test", "region-test", "assistant-response")
    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.generate(remote_request()))

    assert adapter.calls == 1
