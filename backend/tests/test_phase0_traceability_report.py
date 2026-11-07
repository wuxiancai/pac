from pathlib import Path


REPORT = (
    Path(__file__).parents[2]
    / "docs"
    / "poc"
    / "phase0-traceability.md"
)
HANDOFF = Path(__file__).parents[2] / "docs" / "HANDOFF.md"


def test_phase0_traceability_matches_latest_local_poc_evidence_and_gate() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for required in (
        "POC-04 本地 Embedding",
        "真实模型已下载并离线加载",
        "设备密码",
        "Touch ID/设备密码",
        "真实 Provider/Gateway 实测尚缺",
        "WAL TRUNCATE checkpoint",
        "阶段 0：未验收。阶段 1：未开始。",
    ):
        assert required in report

    assert "模型权重下载未完成" not in report
    assert "Touch ID UI/完整 App lifecycle OPEN" not in report


def test_handoff_does_not_leave_superseded_embedding_or_backend_status() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "真实权重下载停滞并中断；未计算真实向量" not in handoff
    assert "这不是正式 App 后端子进程管理，真实 App 生命周期仍未验收" not in handoff
    assert "候选权重已下载并离线评测" in handoff
    assert "SwiftUI demo 已接入本机后端 supervisor" in handoff
