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
from pac_poc.security_poc import (
    ConsentGrant,
    ConsentManager,
    DataLevel,
    ModelAction,
    OutboundPolicy,
)


TEST_SOURCE = "test-surface"


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


class WaitingGenerateAdapter(RemoteProbeAdapter):
    def __init__(
        self,
        started: asyncio.Event,
        pending: asyncio.Event,
        expected_calls: int = 1,
    ) -> None:
        super().__init__()
        self.started = started
        self.pending = pending
        self.expected_calls = expected_calls
        self.cancelled = False
        self.cancelled_calls = 0

    async def generate(self, request: LocalModelRequest) -> str:
        self.calls += 1
        if self.calls >= self.expected_calls:
            self.started.set()
        try:
            await self.pending.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            self.cancelled_calls += 1
            raise
        return "late response"


class WaitingStreamAdapter(RemoteProbeAdapter):
    def __init__(
        self,
        started: asyncio.Event,
        pending: asyncio.Event,
        closed: asyncio.Event,
    ) -> None:
        super().__init__()
        self.started = started
        self.pending = pending
        self.closed = closed

    async def stream(self, request: LocalModelRequest):
        self.calls += 1
        try:
            self.started.set()
            yield "first chunk"
            await self.pending.wait()
        finally:
            self.closed.set()


class CloseFailingStream:
    def __init__(self) -> None:
        self.sent = False

    def __aiter__(self) -> CloseFailingStream:
        return self

    async def __anext__(self) -> str:
        if self.sent:
            raise StopAsyncIteration
        self.sent = True
        return "one chunk"

    async def aclose(self) -> None:
        raise RuntimeError("synthetic stream close failure")


class CancelCloseFailingStream(CloseFailingStream):
    def __init__(self, started: asyncio.Event, pending: asyncio.Event) -> None:
        super().__init__()
        self.started = started
        self.pending = pending

    async def __anext__(self) -> str:
        if not self.sent:
            self.sent = True
            return "one chunk"
        self.started.set()
        await self.pending.wait()
        raise StopAsyncIteration


class CloseFailingAdapter:
    is_local = False

    def __init__(self, stream: CloseFailingStream | None = None) -> None:
        self.stream_instance = stream

    async def generate(self, request: LocalModelRequest) -> str:
        raise AssertionError("test uses a stream")

    def stream(self, request: LocalModelRequest) -> CloseFailingStream:
        return self.stream_instance or CloseFailingStream()


def remote_request(**overrides: object) -> LocalModelRequest:
    fields: dict[str, object] = {
        "provider": "provider-test",
        "model": "model-test",
        "messages": ({"role": "user", "content": "synthetic"},),
        "region": "region-test",
        "purpose": "assistant-response",
        "data_level": DataLevel.L1,
        "source": TEST_SOURCE,
    }
    fields.update(overrides)
    return LocalModelRequest(**fields)  # type: ignore[arg-type]


def grant_consent(
    consent: ConsentManager,
    *,
    actions: frozenset[ModelAction] = frozenset({ModelAction.GENERATE}),
) -> None:
    consent.grant(
        ConsentGrant(
            provider="provider-test",
            model="model-test",
            region="region-test",
            purpose="assistant-response",
            data_levels=frozenset({DataLevel.L1}),
            action_scopes=actions,
            source_scopes=frozenset({TEST_SOURCE}),
            expires_at=time.time() + 60,
        )
    )


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


def test_remote_request_without_source_scope_is_denied() -> None:
    adapter = RemoteProbeAdapter()
    consent = ConsentManager()
    grant_consent(consent)
    gateway = make_gateway(consent, adapter)

    with pytest.raises(PolicyDenied, match="explicit source scope"):
        asyncio.run(gateway.generate(remote_request(source="")))

    assert adapter.calls == 0


def test_remote_gateway_allows_only_exact_live_consent() -> None:
    consent = ConsentManager()
    grant_consent(consent)
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
        {"source": "other-surface"},
        {"data_level": DataLevel.L2},
        {"data_level": DataLevel.L3},
    ],
)
def test_remote_gateway_denies_consent_mismatch(overrides: dict[str, object]) -> None:
    consent = ConsentManager()
    grant_consent(consent)
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    with pytest.raises((PolicyDenied, ProviderNotFound)):
        asyncio.run(gateway.generate(remote_request(**overrides)))

    assert adapter.calls == 0


def test_generate_consent_does_not_authorize_streaming() -> None:
    """A grant scoped to generate must not be usable to open a stream."""
    consent = ConsentManager()
    grant_consent(consent, actions=frozenset({ModelAction.GENERATE}))
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    async def read_first() -> str:
        return await anext(gateway.stream(remote_request()))

    with pytest.raises(PolicyDenied):
        asyncio.run(read_first())

    assert adapter.calls == 0


def test_stream_consent_does_not_authorize_generate() -> None:
    consent = ConsentManager()
    grant_consent(consent, actions=frozenset({ModelAction.STREAM}))
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.generate(remote_request()))

    assert adapter.calls == 0


def test_text_consent_does_not_authorize_tool_proposal() -> None:
    """Regression: tool proposals previously inherited a text-only grant."""
    consent = ConsentManager()
    grant_consent(consent, actions=frozenset({ModelAction.GENERATE}))
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.call_with_tools(remote_request()))

    assert adapter.calls == 0


def test_streaming_is_authorized_when_grant_lists_stream_action() -> None:
    consent = ConsentManager()
    grant_consent(consent, actions=frozenset({ModelAction.STREAM}))
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)

    async def collect() -> str:
        return "".join([part async for part in gateway.stream(remote_request())])

    assert asyncio.run(collect()) == "stubbed response"
    assert adapter.calls == 1


def test_revocation_blocks_next_remote_gateway_request() -> None:
    consent = ConsentManager()
    grant_consent(consent)
    adapter = RemoteProbeAdapter()
    gateway = make_gateway(consent, adapter)
    assert asyncio.run(gateway.generate(remote_request())) == "stubbed response"

    assert consent.revoke("provider-test", "model-test", "region-test", "assistant-response")
    with pytest.raises(PolicyDenied):
        asyncio.run(gateway.generate(remote_request()))

    assert adapter.calls == 1


def test_revocation_cancels_in_flight_generate() -> None:
    async def run() -> None:
        consent = ConsentManager()
        grant_consent(consent)
        started = asyncio.Event()
        pending = asyncio.Event()
        adapter = WaitingGenerateAdapter(started, pending)
        gateway = make_gateway(consent, adapter)
        task = asyncio.create_task(gateway.generate(remote_request()))

        await started.wait()
        assert consent.revoke(
            "provider-test", "model-test", "region-test", "assistant-response"
        )
        with pytest.raises(asyncio.CancelledError):
            await task

        assert adapter.calls == 1
        assert adapter.cancelled
        grant = consent.exact_grant(
            "provider-test", "model-test", "region-test", "assistant-response"
        )
        assert grant is not None
        assert grant.status.value == "revoked"

    asyncio.run(run())


def test_revocation_cancels_in_flight_stream_and_closes_adapter() -> None:
    async def run() -> None:
        consent = ConsentManager()
        grant_consent(consent, actions=frozenset({ModelAction.STREAM}))
        started = asyncio.Event()
        pending = asyncio.Event()
        closed = asyncio.Event()
        adapter = WaitingStreamAdapter(started, pending, closed)
        gateway = make_gateway(consent, adapter)

        async def consume() -> list[str]:
            return [chunk async for chunk in gateway.stream(remote_request())]

        task = asyncio.create_task(consume())
        await started.wait()
        assert consent.revoke(
            "provider-test", "model-test", "region-test", "assistant-response"
        )
        with pytest.raises(asyncio.CancelledError):
            await task

        assert adapter.calls == 1
        assert closed.is_set()

    asyncio.run(run())


def test_usage_stream_releases_consent_lease_when_upstream_close_fails() -> None:
    async def run() -> None:
        consent = ConsentManager()
        grant_consent(consent, actions=frozenset({ModelAction.STREAM}))
        gateway = make_gateway(consent, CloseFailingAdapter())  # type: ignore[arg-type]

        async def consume() -> None:
            async for _ in gateway.stream_with_usage(remote_request()):
                pass

        with pytest.raises(RuntimeError, match="synthetic stream close failure"):
            await consume()

        assert consent._in_flight == {}

    asyncio.run(run())


def test_usage_stream_preserves_cancellation_when_upstream_close_fails() -> None:
    async def run() -> None:
        consent = ConsentManager()
        grant_consent(consent, actions=frozenset({ModelAction.STREAM}))
        started = asyncio.Event()
        pending = asyncio.Event()
        adapter = CloseFailingAdapter(CancelCloseFailingStream(started, pending))
        gateway = make_gateway(consent, adapter)  # type: ignore[arg-type]

        async def consume() -> None:
            async for _ in gateway.stream_with_usage(remote_request()):
                pass

        task = asyncio.create_task(consume())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert consent._in_flight == {}

    asyncio.run(run())


def test_revocation_cancels_all_concurrent_requests_for_the_consent_scope() -> None:
    async def run() -> None:
        consent = ConsentManager()
        grant_consent(consent)
        started = asyncio.Event()
        pending = asyncio.Event()
        adapter = WaitingGenerateAdapter(started, pending, expected_calls=2)
        gateway = make_gateway(consent, adapter)
        tasks = [
            asyncio.create_task(gateway.generate(remote_request()))
            for _ in range(2)
        ]

        await started.wait()
        assert adapter.calls == 2
        assert consent.revoke(
            "provider-test", "model-test", "region-test", "assistant-response"
        )
        results = await asyncio.gather(*tasks, return_exceptions=True)

        assert all(isinstance(result, asyncio.CancelledError) for result in results)
        assert adapter.cancelled_calls == 2

    asyncio.run(run())
