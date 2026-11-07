from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from typing import Any


def summarize_measurements(
    *,
    frame_latencies_seconds: Sequence[float],
    audio_seconds: float,
    inference_seconds: float,
    model_load_seconds: float,
    process_cpu_seconds: float,
    peak_rss_bytes: int,
    partial_count: int,
    final_count: int,
) -> dict[str, Any]:
    latencies = tuple(frame_latencies_seconds)
    durations = (audio_seconds, inference_seconds, model_load_seconds, process_cpu_seconds)
    if not latencies or any(not math.isfinite(value) or value < 0 for value in latencies):
        raise ValueError("frame latencies must contain finite non-negative measurements")
    if not math.isfinite(audio_seconds) or audio_seconds <= 0:
        raise ValueError("audio duration must be finite and positive")
    if any(not math.isfinite(value) or value < 0 for value in durations[1:]):
        raise ValueError("timings must be finite and non-negative")
    if peak_rss_bytes < 0 or partial_count < 0 or final_count < 0:
        raise ValueError("resource and event counts cannot be negative")

    percentiles = (
        statistics.quantiles(latencies, n=100, method="inclusive")
        if len(latencies) > 1
        else [latencies[0]] * 99
    )
    p50, p95 = percentiles[49], percentiles[94]
    return {
        "audio_seconds": audio_seconds,
        "inference_seconds": inference_seconds,
        "real_time_factor": inference_seconds / audio_seconds,
        "frame_count": len(latencies),
        "frame_latency_seconds": {
            "p50": p50,
            "p95": p95,
            "max": max(latencies),
        },
        "model_load_seconds": model_load_seconds,
        "process_cpu_seconds": process_cpu_seconds,
        "peak_rss_bytes": peak_rss_bytes,
        "partial_count": partial_count,
        "final_count": final_count,
    }
