from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from time import perf_counter
from typing import Generic, TypeVar


T = TypeVar("T")
U = TypeVar("U")
V = TypeVar("V")


@dataclass(frozen=True)
class WorkSample(Generic[T]):
    value: T
    started_at: float
    finished_at: float

    @property
    def wall_seconds(self) -> float:
        return self.finished_at - self.started_at


@dataclass(frozen=True)
class ConcurrentProbeResult(Generic[T, U]):
    asr: WorkSample[T]
    model: WorkSample[U]
    overlap_seconds: float


def run_concurrently(
    *, asr_work: Callable[[], T], model_work: Callable[[], U]
) -> ConcurrentProbeResult[T, U]:
    """Start two independent POC workloads together and measure their actual overlap."""
    start_barrier = Barrier(2)

    def measure(work: Callable[[], V]) -> WorkSample[V]:
        start_barrier.wait()
        started_at = perf_counter()
        value = work()
        finished_at = perf_counter()
        return WorkSample(value, started_at, finished_at)

    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="phase0-concurrency") as pool:
        asr_future = pool.submit(measure, asr_work)
        model_future = pool.submit(measure, model_work)
        asr_sample = asr_future.result()
        model_sample = model_future.result()

    overlap = max(
        0.0,
        min(asr_sample.finished_at, model_sample.finished_at)
        - max(asr_sample.started_at, model_sample.started_at),
    )
    return ConcurrentProbeResult(asr_sample, model_sample, overlap)
