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
        "该次历史测量之后新增 Qwen3-ASR 离线英语样本评估",
    ):
        assert required in report


def test_asr_report_records_three_repeat_local_measurements_and_limits() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for required in (
        "同一条 6.94 秒合成 WAV 连续运行 3 次",
        "帧 P50 16.01–16.51 ms",
        "帧 P95 17.22–31.78 ms",
        "RTF 0.0527–0.0665",
        "不能推断真人语音、麦克风实时性或产品性能验收",
    ):
        assert required in report
