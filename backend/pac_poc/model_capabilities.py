from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


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


class CapabilityReportFormatError(ValueError):
    """A capability report manifest is malformed or contains unsupported fields."""


class ModelCapabilityRegistry:
    """Exact provider/model evidence registry; names and formats imply nothing."""

    def __init__(self) -> None:
        self._reports: dict[tuple[str, str], ModelCapabilityReport] = {}

    @classmethod
    def from_json(cls, raw: str) -> ModelCapabilityRegistry:
        """Build a registry from a strict, versioned JSON evidence manifest.

        This only assembles explicitly supplied evidence; it never infers a
        capability from provider/model names or fills in omitted capabilities.
        """
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CapabilityReportFormatError("manifest must be valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {"schema_version", "reports"}:
            raise CapabilityReportFormatError("manifest must contain schema_version and reports")
        if type(payload["schema_version"]) is not int or payload["schema_version"] != 1:
            raise CapabilityReportFormatError("unsupported manifest schema_version")
        if not isinstance(payload["reports"], list):
            raise CapabilityReportFormatError("reports must be a list")

        registry = cls()
        try:
            for item in payload["reports"]:
                registry.register(_report_from_mapping(item))
        except (TypeError, ValueError, KeyError) as exc:
            if isinstance(exc, CapabilityReportFormatError):
                raise
            raise CapabilityReportFormatError(str(exc)) from exc
        return registry

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


def _report_from_mapping(value: Any) -> ModelCapabilityReport:
    if not isinstance(value, dict):
        raise CapabilityReportFormatError("each report must be an object")
    required = {"provider_id", "model_id", "entries", "verified_at", "evidence_refs"}
    optional = {"context_limit", "region", "data_policy_ref"}
    if not required.issubset(value) or not set(value).issubset(required | optional):
        raise CapabilityReportFormatError("report fields do not match schema version 1")

    entries_value = value["entries"]
    evidence_value = value["evidence_refs"]
    if not isinstance(entries_value, list) or not isinstance(evidence_value, list):
        raise CapabilityReportFormatError("entries and evidence_refs must be lists")
    entries: list[ModelCapabilityEntry] = []
    for item in entries_value:
        if not isinstance(item, dict) or set(item) != {"capability", "state"}:
            raise CapabilityReportFormatError("each entry requires capability and state")
        try:
            capability = Capability(item["capability"])
            state = CapabilityState(item["state"])
            entries.append(ModelCapabilityEntry(capability, state))
        except (TypeError, ValueError) as exc:
            raise CapabilityReportFormatError("entry contains an unknown capability or state") from exc
    if any(not isinstance(ref, str) or not ref.strip() for ref in evidence_value):
        raise CapabilityReportFormatError("evidence_refs must contain non-empty strings")
    for field in ("provider_id", "model_id", "verified_at"):
        if not isinstance(value[field], str):
            raise CapabilityReportFormatError(f"{field} must be a string")
    for field in ("region", "data_policy_ref"):
        if field in value and value[field] is not None and not isinstance(value[field], str):
            raise CapabilityReportFormatError(f"{field} must be a string or null")
    context_limit = value.get("context_limit")
    if context_limit is not None and (type(context_limit) is not int or context_limit <= 0):
        raise CapabilityReportFormatError("context_limit must be a positive integer or null")
    return ModelCapabilityReport(
        provider_id=value["provider_id"],
        model_id=value["model_id"],
        entries=tuple(entries),
        verified_at=value["verified_at"],
        evidence_refs=tuple(evidence_value),
        context_limit=context_limit,
        region=value.get("region"),
        data_policy_ref=value.get("data_policy_ref"),
    )
