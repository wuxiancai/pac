from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


@dataclass(frozen=True)
class AgentDefinition:
    key: str
    model_id: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    simulated: bool = False

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise ValueError("agent key must not be empty")
        if not self.model_id.strip():
            raise ValueError("agent model_id must not be empty")


class AgentResultStatus(StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    NEEDS_CLARIFICATION = "needs_clarification"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass(frozen=True)
class AgentResult:
    status: AgentResultStatus
    summary: str
    evidence: tuple[str, ...] = ()
    artifacts: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentResultStatus):
            raise ValueError("status must be a known AgentResultStatus")
        if not self.summary.strip():
            raise ValueError("summary must not be empty")


class SimulatedAgentRegistry:
    """POC-only definitions; simulated entries are never product agent runs."""

    def __init__(self, definitions: tuple[AgentDefinition, ...] | list[AgentDefinition]) -> None:
        self._definitions: dict[str, AgentDefinition] = {}
        self.product_agent_run_count = 0
        for definition in definitions:
            self.register(definition)
        if "main_assistant" not in self._definitions:
            raise ValueError("registry requires the single main_assistant definition")

    @property
    def keys(self) -> tuple[str, ...]:
        return tuple(self._definitions)

    def get(self, key: str) -> AgentDefinition:
        try:
            return self._definitions[key]
        except KeyError as exc:
            raise LookupError(f"unknown POC agent: {key}") from exc

    def register(self, definition: AgentDefinition) -> None:
        if definition.key != "main_assistant" and not definition.simulated:
            raise ValueError("additional agents are allowed only as explicit POC simulations")
        if definition.key == "main_assistant" and definition.simulated:
            raise ValueError("main_assistant is the single non-simulated product definition")
        if definition.key in self._definitions:
            raise ValueError(f"duplicate agent key: {definition.key}")
        self._definitions[definition.key] = definition


def derive_child_permissions(
    *, parent: frozenset[str], requested: frozenset[str]
) -> frozenset[str]:
    """A simulated child can receive only the intersection of parent permissions."""
    return parent.intersection(requested)
