from pathlib import Path


REPORT = Path(__file__).parents[2] / "docs" / "poc" / "phase0-local-asr.md"


def test_asr_report_records_reproducible_synthetic_set_and_scope() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for required in (
        "8 条本机合成中文句",
        "8/8 final",
        "weighted CER 0.0",
        "59 个 partial",
        "3,000 ms",
        "不是真人麦克风准确率",
        "不输出转写正文",
        "由用户后续补下载多语言模型",
    ):
        assert required in report
