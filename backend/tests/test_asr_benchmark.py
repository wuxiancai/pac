from __future__ import annotations

import pytest

from pac_poc.asr_benchmark import summarize_measurements


def test_summary_reports_median_p95_and_realtime_factor() -> None:
    summary = summarize_measurements(
        frame_latencies_seconds=[0.01, 0.02, 0.03, 0.04],
        audio_seconds=0.8,
        inference_seconds=0.2,
        model_load_seconds=1.5,
        process_cpu_seconds=0.18,
        peak_rss_bytes=1024,
        partial_count=3,
        final_count=1,
    )

    assert summary["frame_latency_seconds"]["p50"] == pytest.approx(0.025)
    assert summary["frame_latency_seconds"]["p95"] == pytest.approx(0.0385)
    assert summary["real_time_factor"] == pytest.approx(0.25)
    assert summary["partial_count"] == 3
    assert summary["final_count"] == 1
    assert summary["peak_rss_bytes"] == 1024


@pytest.mark.parametrize(
    "overrides",
    [
        {"frame_latencies_seconds": []},
        {"audio_seconds": 0},
        {"inference_seconds": -1},
        {"partial_count": -1},
    ],
)
def test_summary_rejects_invalid_measurements(overrides: dict[str, object]) -> None:
    values: dict[str, object] = {
        "frame_latencies_seconds": [0.01],
        "audio_seconds": 1.0,
        "inference_seconds": 0.1,
        "model_load_seconds": 0.1,
        "process_cpu_seconds": 0.1,
        "peak_rss_bytes": 100,
        "partial_count": 0,
        "final_count": 1,
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        summarize_measurements(**values)  # type: ignore[arg-type]
