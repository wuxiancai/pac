from pathlib import Path


REPORT = (
    Path(__file__).parents[2]
    / "docs"
    / "poc"
    / "phase0-local-embedding.md"
)


def test_embedding_report_records_real_local_run_without_claiming_product_acceptance() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for required in (
        "top1_matches=4/4",
        "851,804,160 bytes",
        "1.95 秒",
        "合成",
        "未选定",
        "local_files_only",
        "HF_HUB_OFFLINE",
    ):
        assert required in report

    assert "不能外推" in report
