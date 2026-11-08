from pathlib import Path


REPORT = Path(__file__).parents[2] / "docs" / "poc" / "phase0-local-asr.md"


def test_asr_report_records_concurrent_local_model_sample_and_limits() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for required in (
        "qwen3.5:0.8b",
        "做三轮本机重复",
        "重叠 0.420–0.553 秒",
        "P95 19.55–30.17 ms",
        "585,367,552–1,126,219,776 bytes",
        "GPU 未测",
        "不能作为产品性能验收",
        "工具未执行",
    ):
        assert required in report
