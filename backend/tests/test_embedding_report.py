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
        "产品 Embedding 型号",
        "local_files_only",
        "HF_HUB_OFFLINE",
        "D-014",
        "23/24",
        "24/24",
        "人工标注",
        "Embedding 仍保持产品关闭",
    ):
        assert required in report

    assert "不能外推" in report
