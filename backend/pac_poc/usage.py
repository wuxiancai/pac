"""Bounded process-local request usage metadata for the single-user beta."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from threading import Lock

from .orchestrator import RunStatus
from .security_poc import DataLevel


class UsageState(StrEnum):
    ACTUAL = "actual"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class UsageRecord:
    run_id: str
    provider: str
    model: str
    region: str
    purpose: str
    data_level: DataLevel
    status: RunStatus
    started_at: float
    completed_at: float
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    audio_seconds: float | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None
    usage_state: UsageState = UsageState.UNKNOWN
    cost_state: UsageState = UsageState.UNKNOWN


class UsageLedger:
    """Keep only bounded metadata; never retain prompts, outputs, keys, or audio."""

    def __init__(self, *, capacity: int = 512) -> None:
        if capacity < 1:
            raise ValueError("usage ledger capacity must be positive")
        self._records: deque[UsageRecord] = deque(maxlen=capacity)
        self._lock = Lock()

    def record(self, record: UsageRecord) -> None:
        if record.latency_ms < 0 or record.completed_at < record.started_at:
            raise ValueError("usage record timestamps are invalid")
        for value in (record.prompt_tokens, record.completion_tokens):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError("token counts must be non-negative integers or unknown")
        if record.cost_amount is not None and (
            isinstance(record.cost_amount, bool)
            or not isinstance(record.cost_amount, (int, float))
            or not isfinite(record.cost_amount)
            or record.cost_amount < 0
        ):
            raise ValueError("cost amount must be non-negative or unknown")
        if (record.cost_amount is None) != (record.cost_currency is None):
            raise ValueError("cost amount and currency must be provided together")
        if record.usage_state is UsageState.ACTUAL and (
            record.prompt_tokens is None and record.completion_tokens is None
        ):
            raise ValueError("actual usage requires at least one token count")
        if record.cost_state is not UsageState.UNKNOWN and record.cost_amount is None:
            raise ValueError("known cost state requires an amount and currency")
        if record.cost_amount is not None and record.cost_state is UsageState.UNKNOWN:
            raise ValueError("reported cost amount requires an actual or estimated state")
        with self._lock:
            self._records.append(record)

    def list_records(self, *, limit: int = 100) -> tuple[UsageRecord, ...]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("usage query limit must be between 1 and 100")
        with self._lock:
            return tuple(list(self._records)[-limit:][::-1])

    def summary(self) -> dict[str, int | float]:
        with self._lock:
            records = tuple(self._records)
        return {
            "record_count": len(records),
            "unknown_usage_count": sum(item.usage_state is UsageState.UNKNOWN for item in records),
            "unknown_cost_count": sum(item.cost_state is UsageState.UNKNOWN for item in records),
            "total_latency_ms": sum(item.latency_ms for item in records),
        }


def usage_record_to_dict(record: UsageRecord) -> dict[str, str | float | int | None]:
    """Return a JSON-safe record that intentionally excludes conversation content."""
    return {
        "run_id": record.run_id,
        "provider": record.provider,
        "model": record.model,
        "region": record.region,
        "purpose": record.purpose,
        "data_level": record.data_level.value,
        "status": record.status.value,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "latency_ms": record.latency_ms,
        "prompt_tokens": record.prompt_tokens,
        "completion_tokens": record.completion_tokens,
        "audio_seconds": record.audio_seconds,
        "cost_amount": record.cost_amount,
        "cost_currency": record.cost_currency,
        "usage_state": record.usage_state.value,
        "cost_state": record.cost_state.value,
    }
