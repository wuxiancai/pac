"""Single-assistant request orchestration seams for the local-first beta."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from time import time
from typing import Protocol
from uuid import uuid4

from .model_gateway import LocalModelRequest, ModelGateway
from .model_capabilities import (
    Capability,
    CapabilityNotVerified,
    CapabilityState,
    ModelCapabilityRegistry,
)
from .security_poc import DataLevel


MAIN_ASSISTANT = "main_assistant"


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunSnapshot:
    run_id: str
    assistant_key: str
    status: RunStatus
    created_at: float
    updated_at: float


class RunRegistry:
    """Bounded process-local lifecycle metadata; prompts and outputs are never kept."""

    _TERMINAL = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})
    _TRANSITIONS = {
        RunStatus.CREATED: frozenset({RunStatus.RUNNING, RunStatus.CANCELLED, RunStatus.FAILED}),
        RunStatus.RUNNING: _TERMINAL,
    }

    def __init__(self, *, capacity: int = 256) -> None:
        if capacity < 1:
            raise ValueError("run registry capacity must be positive")
        self._capacity = capacity
        self._runs: dict[str, RunSnapshot] = {}
        self._lock = Lock()

    def create(self, assistant_key: str = MAIN_ASSISTANT) -> RunSnapshot:
        if assistant_key != MAIN_ASSISTANT:
            raise AssistantNotFound(f"assistant is not enabled: {assistant_key}")
        now = time()
        snapshot = RunSnapshot(str(uuid4()), assistant_key, RunStatus.CREATED, now, now)
        with self._lock:
            if len(self._runs) >= self._capacity:
                oldest_terminal = next(
                    (key for key, run in self._runs.items() if run.status in self._TERMINAL),
                    None,
                )
                if oldest_terminal is None:
                    raise RuntimeError("run registry is full with active runs")
                del self._runs[oldest_terminal]
            self._runs[snapshot.run_id] = snapshot
        return snapshot

    def transition(self, run_id: str, status: RunStatus) -> RunSnapshot:
        with self._lock:
            current = self._runs.get(run_id)
            if current is None:
                raise LookupError("unknown run")
            if status not in self._TRANSITIONS.get(current.status, frozenset()):
                raise ValueError(f"invalid run transition: {current.status} -> {status}")
            updated = RunSnapshot(
                current.run_id, current.assistant_key, status, current.created_at, time()
            )
            self._runs[run_id] = updated
            return updated

    def get(self, run_id: str) -> RunSnapshot | None:
        with self._lock:
            return self._runs.get(run_id)


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
    required_capabilities: tuple[Capability, ...] = ()


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
        capability_registry: ModelCapabilityRegistry | None = None,
    ) -> None:
        self._gateway = gateway
        self._context_builder = context_builder or PassThroughContextBuilder()
        self._capability_registry = capability_registry

    def stream(self, turn: ConversationTurn) -> AsyncIterator[str]:
        if turn.assistant_key != MAIN_ASSISTANT:
            raise AssistantNotFound(f"assistant is not enabled: {turn.assistant_key}")
        for capability in turn.required_capabilities:
            if self._capability_registry is None:
                raise CapabilityNotVerified(capability, state=CapabilityState.UNKNOWN)
            self._capability_registry.require(turn.provider, turn.model, capability)
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
