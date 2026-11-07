from __future__ import annotations

import pytest

from pac_poc.model_capabilities import (
    Capability,
    CapabilityNotVerified,
    CapabilityState,
    ModelCapabilityEntry,
    ModelCapabilityRegistry,
    ModelCapabilityReport,
)


def test_unknown_model_and_capabilities_stay_unknown_without_evidence() -> None:
    registry = ModelCapabilityRegistry()

    assert registry.state("ollama-local", "qwen3.5:0.8b", Capability.TOOLS) is (
        CapabilityState.UNKNOWN
    )
    with pytest.raises(CapabilityNotVerified, match="unknown"):
        registry.require("ollama-local", "qwen3.5:0.8b", Capability.TOOLS)


def test_verified_capability_requires_exact_model_and_keeps_other_capabilities_unknown() -> None:
    registry = ModelCapabilityRegistry()
    registry.register(
        ModelCapabilityReport(
            provider_id="ollama-local",
            model_id="qwen3.5:0.8b",
            entries=(
                ModelCapabilityEntry(Capability.TEXT_GENERATION, CapabilityState.SUPPORTED),
                ModelCapabilityEntry(Capability.STREAMING, CapabilityState.SUPPORTED),
            ),
            verified_at="2026-11-07T00:00:00Z",
            evidence_refs=("docs/poc/phase0-model-gateway-local.md",),
        )
    )

    assert registry.require("ollama-local", "qwen3.5:0.8b", Capability.STREAMING)
    assert registry.state("ollama-local", "qwen3.5:0.8b", Capability.TOOLS) is (
        CapabilityState.UNKNOWN
    )
    assert registry.state("ollama-local", "qwen3.5:8b", Capability.STREAMING) is (
        CapabilityState.UNKNOWN
    )


def test_explicitly_unsupported_is_distinct_from_unknown() -> None:
    registry = ModelCapabilityRegistry()
    registry.register(
        ModelCapabilityReport(
            provider_id="local-fixture",
            model_id="fixture-v1",
            entries=(
                ModelCapabilityEntry(Capability.VISION, CapabilityState.UNSUPPORTED),
            ),
            verified_at="2026-11-07T00:00:00Z",
            evidence_refs=("fixture:vision-negative-case",),
        )
    )

    assert registry.state("local-fixture", "fixture-v1", Capability.VISION) is (
        CapabilityState.UNSUPPORTED
    )
    assert registry.state("local-fixture", "fixture-v1", Capability.EMBEDDINGS) is (
        CapabilityState.UNKNOWN
    )
    with pytest.raises(CapabilityNotVerified, match="unsupported"):
        registry.require("local-fixture", "fixture-v1", Capability.VISION)


def test_verified_report_requires_timestamp_and_evidence_and_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="evidence"):
        ModelCapabilityReport(
            provider_id="provider",
            model_id="model",
            entries=(ModelCapabilityEntry(Capability.STREAMING, CapabilityState.SUPPORTED),),
        )
    duplicate = ModelCapabilityReport(
        provider_id="provider",
        model_id="model",
        entries=(
            ModelCapabilityEntry(Capability.STREAMING, CapabilityState.SUPPORTED),
            ModelCapabilityEntry(Capability.STREAMING, CapabilityState.UNSUPPORTED),
        ),
        verified_at="2026-11-07T00:00:00Z",
        evidence_refs=("fixture:evidence",),
    )
    with pytest.raises(ValueError, match="duplicate capability"):
        ModelCapabilityRegistry().register(duplicate)
