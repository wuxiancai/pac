from __future__ import annotations

from math import inf, nan

import pytest

from pac_poc.orchestrator import RunStatus
from pac_poc.security_poc import DataLevel
from pac_poc.usage import UsageLedger, UsageRecord, UsageState


def _record(run_id: str) -> UsageRecord:
    return UsageRecord(
        run_id=run_id,
        provider="ollama",
        model="qwen-local",
        region="local",
        purpose="beta-interactive-chat",
        data_level=DataLevel.L0,
        status=RunStatus.COMPLETED,
        started_at=100.0,
        completed_at=101.0,
        latency_ms=1000,
    )


def test_usage_ledger_is_bounded_and_returns_newest_first() -> None:
    ledger = UsageLedger(capacity=2)
    ledger.record(_record("first"))
    ledger.record(_record("second"))
    ledger.record(_record("third"))

    assert [item.run_id for item in ledger.list_records()] == ["third", "second"]
    assert ledger.summary() == {
        "record_count": 2,
        "unknown_usage_count": 2,
        "unknown_cost_count": 2,
        "total_latency_ms": 2000,
    }


def test_usage_ledger_rejects_invalid_limits_and_unpaired_cost_fields() -> None:
    with pytest.raises(ValueError, match="capacity"):
        UsageLedger(capacity=0)
    with pytest.raises(ValueError, match="limit"):
        UsageLedger().list_records(limit=101)
    with pytest.raises(ValueError, match="currency"):
        UsageLedger().record(_record("bad-cost").__class__(
            **{**_record("bad-cost").__dict__, "cost_amount": 1.0}
        ))


def test_usage_record_preserves_explicit_actual_usage_without_content_fields() -> None:
    record = UsageRecord(
        **{
            **_record("actual").__dict__,
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "cost_amount": 0.25,
            "cost_currency": "CNY",
            "usage_state": UsageState.ACTUAL,
            "cost_state": UsageState.ACTUAL,
        }
    )
    ledger = UsageLedger()
    ledger.record(record)

    assert ledger.list_records()[0].prompt_tokens == 12
    assert ledger.list_records()[0].cost_currency == "CNY"
    assert "prompt" not in UsageRecord.__dataclass_fields__
    assert "messages" not in UsageRecord.__dataclass_fields__
    assert "content" not in UsageRecord.__dataclass_fields__


def test_usage_ledger_rejects_token_counts_marked_unknown() -> None:
    record = UsageRecord(
        **{**_record("unknown-with-counts").__dict__, "prompt_tokens": 12}
    )

    with pytest.raises(ValueError, match="unknown usage"):
        UsageLedger().record(record)


def test_usage_ledger_rejects_estimated_state_without_token_counts() -> None:
    record = UsageRecord(
        **{**_record("estimated-without-counts").__dict__, "usage_state": UsageState.ESTIMATED}
    )

    with pytest.raises(ValueError, match="known usage"):
        UsageLedger().record(record)


def test_usage_ledger_rejects_cached_prompt_tokens_above_prompt_total() -> None:
    record = UsageRecord(
        **{
            **_record("invalid-cache").__dict__,
            "prompt_tokens": 10,
            "cached_prompt_tokens": 11,
        }
    )
    with pytest.raises(ValueError, match="cached prompt tokens"):
        UsageLedger().record(record)


@pytest.mark.parametrize(
    "field,value", [("started_at", nan), ("completed_at", inf), ("latency_ms", True)]
)
def test_usage_ledger_rejects_invalid_time_values(field: str, value: object) -> None:
    record = UsageRecord(**{**_record("bad-time").__dict__, field: value})

    with pytest.raises(ValueError, match="timestamps"):
        UsageLedger().record(record)


@pytest.mark.parametrize("value", [nan, inf, -1.0, True])
def test_usage_ledger_rejects_invalid_audio_duration(value: object) -> None:
    record = UsageRecord(**{**_record("bad-audio").__dict__, "audio_seconds": value})

    with pytest.raises(ValueError, match="audio duration"):
        UsageLedger().record(record)
