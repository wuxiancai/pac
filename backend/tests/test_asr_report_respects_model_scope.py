from pathlib import Path


REPORT = Path(__file__).parents[2] / "docs" / "poc" / "phase0-local-asr.md"


def test_asr_report_distinguishes_offline_multilingual_candidate_from_streaming_scope() -> None:
    report = REPORT.read_text(encoding="utf-8")

    assert "Qwen3-ASR 候选已在五条随包音频上完成离线中/英/混说检查" in report
    assert "不能把 RTF<1 写成实时流式验收" in report
    assert "不实现云端 fallback" in report
