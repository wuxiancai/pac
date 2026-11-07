from __future__ import annotations

import time
from threading import Lock

from pac_poc.concurrent_probe import run_concurrently


def test_probe_starts_asr_and_local_model_work_together_and_measures_overlap() -> None:
    started: dict[str, float] = {}
    lock = Lock()

    def work(name: str) -> str:
        with lock:
            started[name] = time.perf_counter()
        time.sleep(0.04)
        return name

    result = run_concurrently(
        asr_work=lambda: work("asr"),
        model_work=lambda: work("model"),
    )

    assert result.asr.value == "asr"
    assert result.model.value == "model"
    assert abs(started["asr"] - started["model"]) < 0.05
    assert result.overlap_seconds >= 0.03


def test_probe_propagates_worker_failures() -> None:
    def fail() -> None:
        raise RuntimeError("synthetic failure")

    try:
        run_concurrently(asr_work=fail, model_work=lambda: "ok")
    except RuntimeError as error:
        assert str(error) == "synthetic failure"
    else:
        raise AssertionError("worker failure must not be reported as a completed probe")
