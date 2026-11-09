from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

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

    async def _stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        self.request = request
        yield "hello"

    def stream(self, request: LocalModelRequest) -> AsyncIterator[str]:
        return self._stream(request)


def test_main_assistant_orchestrator_builds_ephemeral_gateway_request() -> None:
    gateway = RecordingGateway()
    orchestrator = MainAssistantOrchestrator(gateway)  # type: ignore[arg-type]
    turn = ConversationTurn(
        messages=({"role": "user", "content": "hello"},),
        provider="ollama",
        model="local-model",
    )

    async def consume() -> list[str]:
        return [part async for part in orchestrator.stream(turn)]

    assert asyncio.run(consume()) == ["hello"]
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
