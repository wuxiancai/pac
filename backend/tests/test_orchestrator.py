from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from pac_poc.model_gateway import LocalModelRequest
from pac_poc.orchestrator import (
    AssistantNotFound,
    ConversationTurn,
    MainAssistantOrchestrator,
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
