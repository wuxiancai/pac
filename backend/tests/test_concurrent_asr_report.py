from pathlib import Path


REPORT = Path(__file__).parents[2] / "docs" / "poc" / "phase0-local-asr.md"


def test_asr_report_records_concurrent_local_model_sample_and_limits() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for required in (
        "qwen3.5:0.8b",
        "重叠 0.785 秒",
        "P95 52.17 ms",
        "最大 75.45 ms",
        "702,267,392 bytes",
        "10.95 秒",
        "GPU 未测",
        "不是产品性能验收",
        "工具未执行",
    ):
        assert required in report
