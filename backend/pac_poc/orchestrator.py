"""Single-assistant request orchestration seams for the local-first beta."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from .model_gateway import LocalModelRequest, ModelGateway
from .security_poc import DataLevel


MAIN_ASSISTANT = "main_assistant"


@dataclass(frozen=True)
class ConversationTurn:
    """One in-memory chat request; this object is never persisted by the orchestrator."""

    messages: Sequence[Mapping[str, str]]
    provider: str
    model: str
    region: str = ""
    purpose: str = ""
    data_level: DataLevel = DataLevel.L0
    source: str = ""
    assistant_key: str = MAIN_ASSISTANT


class ContextBuilder(Protocol):
    def build(self, turn: ConversationTurn) -> Sequence[Mapping[str, str]]: ...


class PassThroughContextBuilder:
    """Use only the explicitly supplied turn messages; no memory or disk access."""

    def build(self, turn: ConversationTurn) -> Sequence[Mapping[str, str]]:
        return [{"role": item["role"], "content": item["content"]} for item in turn.messages]


class AssistantNotFound(LookupError):
    """The requested assistant is not enabled in this product build."""


class MainAssistantOrchestrator:
    """Route one assistant turn through a replaceable context builder and gateway."""

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self._gateway = gateway
        self._context_builder = context_builder or PassThroughContextBuilder()

    def stream(self, turn: ConversationTurn) -> AsyncIterator[str]:
        if turn.assistant_key != MAIN_ASSISTANT:
            raise AssistantNotFound(f"assistant is not enabled: {turn.assistant_key}")
        request = LocalModelRequest(
            provider=turn.provider,
            model=turn.model,
            messages=self._context_builder.build(turn),
            region=turn.region,
            purpose=turn.purpose,
            data_level=turn.data_level,
            source=turn.source,
        )
        return self._gateway.stream(request)
