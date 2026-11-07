from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Capability(StrEnum):
    TEXT_GENERATION = "text_generation"
    STREAMING = "streaming"
    TOOLS = "tools"
    PARALLEL_TOOLS = "parallel_tools"
    JSON_SCHEMA = "json_schema"
    VISION = "vision"
    AUDIO_INPUT = "audio_input"
    AUDIO_OUTPUT = "audio_output"
    EMBEDDINGS = "embeddings"
    RERANK = "rerank"
    REALTIME_AUDIO = "realtime_audio"
    BATCH = "batch"
    CANCELLATION = "cancellation"


class CapabilityState(StrEnum):
    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    LIMITED = "limited"


@dataclass(frozen=True)
class ModelCapabilityEntry:
    capability: Capability
    state: CapabilityState

    def __post_init__(self) -> None:
        if self.state is CapabilityState.UNKNOWN:
            raise ValueError("unknown capability must be omitted rather than asserted")


@dataclass(frozen=True)
class ModelCapabilityReport:
    provider_id: str
    model_id: str
    entries: tuple[ModelCapabilityEntry, ...] = ()
    verified_at: str | None = None
    evidence_refs: tuple[str, ...] = ()
    context_limit: int | None = None
    region: str | None = None
    data_policy_ref: str | None = None

    def __post_init__(self) -> None:
        if not self.provider_id.strip() or not self.model_id.strip():
            raise ValueError("provider_id and model_id are required")
        if self.entries and (not self.verified_at or not self.evidence_refs):
            raise ValueError("verified capability entries require timestamp and evidence")
        if self.context_limit is not None and self.context_limit <= 0:
            raise ValueError("context_limit must be positive when known")


class CapabilityNotVerified(RuntimeError):
    def __init__(self, capability: Capability, state: CapabilityState) -> None:
        self.capability = capability
        self.state = state
        super().__init__(f"capability {capability.value} is {state.value}, not verified supported")


class ModelCapabilityRegistry:
    """Exact provider/model evidence registry; names and formats imply nothing."""

    def __init__(self) -> None:
        self._reports: dict[tuple[str, str], ModelCapabilityReport] = {}

    def register(self, report: ModelCapabilityReport) -> None:
        key = (report.provider_id, report.model_id)
        if key in self._reports:
            raise ValueError(f"duplicate model capability report: {key}")
        seen: set[Capability] = set()
        for entry in report.entries:
            if entry.capability in seen:
                raise ValueError(f"duplicate capability entry: {entry.capability.value}")
            seen.add(entry.capability)
        self._reports[key] = report

    def state(self, provider_id: str, model_id: str, capability: Capability) -> CapabilityState:
        report = self._reports.get((provider_id, model_id))
        if report is None:
            return CapabilityState.UNKNOWN
        for entry in report.entries:
            if entry.capability is capability:
                return entry.state
        return CapabilityState.UNKNOWN

    def require(self, provider_id: str, model_id: str, capability: Capability) -> bool:
        state = self.state(provider_id, model_id, capability)
        if state is not CapabilityState.SUPPORTED:
            raise CapabilityNotVerified(capability, state)
        return True

    @property
    def models(self) -> tuple[tuple[str, str], ...]:
        return tuple(self._reports)
