from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from pac_poc.model_capabilities import (
    Capability,
    CapabilityNotVerified,
    CapabilityState,
    ModelCapabilityEntry,
    ModelCapabilityRegistry,
    ModelCapabilityReport,
)
from pac_poc.model_gateway import LocalModelRequest
from pac_poc.orchestrator import (
    AssistantNotFound,
    ConversationTurn,
    MainAssistantOrchestrator,
    RunRegistry,
    RunStatus,
)


class RecordingGateway:
    def __init__(self) -> None:
        self.request: LocalModelRequest | None = None
        self.stream_calls = 0

    async def _stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        self.request = request
        yield "hello"

    def stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        self.stream_calls += 1
        return self._stream(request)


async def _consume_stream(stream: AsyncIterator[str]) -> list[str]:
    return [part async for part in stream]


def test_main_assistant_orchestrator_builds_ephemeral_gateway_request() -> None:
    gateway = RecordingGateway()
    orchestrator = MainAssistantOrchestrator(gateway)  # type: ignore[arg-type]
    turn = ConversationTurn(
        messages=({"role": "user", "content": "hello"},),
        provider="ollama",
        model="local-model",
    )

    assert asyncio.run(_consume_stream(orchestrator.stream(turn))) == ["hello"]
    assert gateway.request is not None
    assert gateway.request.provider == "ollama"
    assert gateway.request.messages == [{"role": "user", "content": "hello"}]


def test_orchestrator_does_not_enable_additional_assistants() -> None:
    gateway = RecordingGateway()
    orchestrator = MainAssistantOrchestrator(gateway)  # type: ignore[arg-type]
    turn = ConversationTurn(
        messages=({"role": "user", "content": "hello"},),
        provider="ollama",
        model="local-model",
        assistant_key="specialist",
    )

    try:
        orchestrator.stream(turn)
    except AssistantNotFound:
        pass
    else:
        raise AssertionError("only main_assistant should be enabled")
    assert gateway.request is None


def test_run_registry_enforces_lifecycle_and_keeps_only_bounded_metadata() -> None:
    runs = RunRegistry(capacity=1)
    first = runs.create()
    assert runs.transition(first.run_id, RunStatus.RUNNING).status is RunStatus.RUNNING
    assert runs.transition(first.run_id, RunStatus.COMPLETED).status is RunStatus.COMPLETED

    second = runs.create()
    assert runs.get(first.run_id) is None
    assert runs.get(second.run_id) is not None
    try:
        runs.transition(second.run_id, RunStatus.COMPLETED)
    except ValueError:
        pass
    else:
        raise AssertionError("runs must pass through running before a terminal state")


def test_run_registry_does_not_evict_active_runs_when_full() -> None:
    runs = RunRegistry(capacity=1)
    first = runs.create()
    runs.transition(first.run_id, RunStatus.RUNNING)
    try:
        runs.create()
    except RuntimeError:
        pass
    else:
        raise AssertionError("active run metadata must not be evicted")


def test_orchestrator_requires_exact_capability_evidence_before_gateway_call() -> None:
    gateway = RecordingGateway()
    registry = ModelCapabilityRegistry()
    registry.register(
        ModelCapabilityReport(
            provider_id="ollama",
            model_id="qwen3.5:0.8b",
            entries=(ModelCapabilityEntry(Capability.TOOLS, CapabilityState.SUPPORTED),),
            verified_at="2026-11-07T00:00:00Z",
            evidence_refs=("docs/poc/phase0-model-capability-registry.md",),
        )
    )
    orchestrator = MainAssistantOrchestrator(
        gateway, capability_registry=registry  # type: ignore[arg-type]
    )
    messages = ({"role": "user", "content": "hello"},)

    with pytest.raises(CapabilityNotVerified, match="unknown"):
        orchestrator.stream(
            ConversationTurn(
                messages=messages,
                provider="ollama",
                model="custom-model",
                required_capabilities=(Capability.TOOLS,),
            )
        )
    assert gateway.stream_calls == 0

    stream = orchestrator.stream(
        ConversationTurn(
            messages=messages,
            provider="ollama",
            model="qwen3.5:0.8b",
            required_capabilities=(Capability.TOOLS,),
        )
    )
    assert gateway.stream_calls == 1
    assert asyncio.run(_consume_stream(stream)) == ["hello"]
