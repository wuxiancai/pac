from pathlib import Path


REPORT = (
    Path(__file__).parents[2]
    / "docs"
    / "poc"
    / "phase0-traceability.md"
)
HANDOFF = Path(__file__).parents[2] / "docs" / "HANDOFF.md"
MEMORY_EMBEDDING = Path(__file__).parents[2] / "docs" / "poc" / "phase0-memory-embedding.md"
FAILURE_RECOVERY = Path(__file__).parents[2] / "docs" / "poc" / "phase0-failure-recovery.md"


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
    assert "POC SwiftUI demo 启停/退出清理已实机验证" in report


def test_handoff_does_not_leave_superseded_embedding_or_backend_status() -> None:
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "真实权重下载停滞并中断；未计算真实向量" not in handoff
    assert "这不是正式 App 后端子进程管理，真实 App 生命周期仍未验收" not in handoff
    assert "候选权重已下载并离线评测" in handoff
    assert "SwiftUI demo 已接入本机后端 supervisor" in handoff
    assert "SwiftUI demo 已实测启动/握手/停止/退出清理" in handoff
    assert "POC-05 真实 Touch ID、完整 App 生命周期/握手未验证" not in handoff


def test_memory_embedding_report_preserves_opt_in_and_non_product_scope() -> None:
    report = MEMORY_EMBEDDING.read_text(encoding="utf-8")
    traceability = REPORT.read_text(encoding="utf-8")
    handoff = HANDOFF.read_text(encoding="utf-8")

    assert "`PARTIAL`" in report
    assert "默认不配置 embedding provider" in report
    assert "没有修改产品 schema" in report
    assert "top1_matches=3" in report
    assert "产品模型、持久化 schema 与真实检索质量仍 OPEN" in traceability
    assert "固定候选权重离线合成检索 3/3 top-1" in handoff


def test_failure_recovery_report_distinguishes_reader_contention_from_crash_mid_checkpoint() -> None:
    report = FAILURE_RECOVERY.read_text(encoding="utf-8")
    traceability = REPORT.read_text(encoding="utf-8")

    assert "活动 WAL reader" in report
    assert "busy=1" in report
    assert "释放并关闭 reader 后" in report
    assert "checkpoint 执行中 SIGKILL" in report
    assert "活动 WAL reader 下 `busy=1` 可见" in traceability


def test_failure_recovery_report_records_atomic_backup_failure_protection() -> None:
    report = FAILURE_RECOVERY.read_text(encoding="utf-8")
    traceability = REPORT.read_text(encoding="utf-8")

    assert "原子替换" in report
    assert "旧备份仍可用原密钥解密" in report
    assert "保留旧备份" in traceability
    assert "备份复制期间子进程 SIGKILL" in report
    assert "WAL 数据库备份/恢复" in report
    assert "复制/校验失败" in report
    assert "崩溃 staging" in traceability
