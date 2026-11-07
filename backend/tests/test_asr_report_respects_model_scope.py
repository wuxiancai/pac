from pathlib import Path


REPORT = Path(__file__).parents[2] / "docs" / "poc" / "phase0-local-asr.md"


def test_asr_report_describes_english_coverage_as_a_later_model_choice() -> None:
    report = REPORT.read_text(encoding="utf-8")

    assert "英语覆盖取决于后续多语言模型" in report
    assert "不属于当前代码缺陷" in report
    assert "不作为当前阶段的实现阻塞" in report
    assert "英文识别仍未解决" not in report
