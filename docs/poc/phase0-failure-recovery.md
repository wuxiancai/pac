# 阶段 0 POC：本机异常恢复与磁盘耗尽（工作包 0H）

状态：`IN_PROGRESS`。故障注入仅作用于 `.poc-data/sqlcipher-tests` 下的临时 SQLCipher 文件。

## 故障注入结果

- **进程异常退出**：子进程从 stdin 读取临时 key，打开加密数据库，在显式事务内写入 memory 与 FTS 行后用 `os._exit(73)` 突然退出。重新打开数据库后，已提交 baseline 仍可搜索，未提交 marker 不存在，`PRAGMA integrity_check` 返回 `ok`。
- **磁盘页数耗尽模拟**：将 SQLCipher POC DB 的 `max_page_count` 限制到当前页数 + 1，插入大记录触发 DBAPI 数据库错误。事务回滚后旧记忆和 FTS 仍可检索，失败记录不存在，完整性检查为 `ok`。
- **Alembic 回滚**：工作包 0F 已验证 POC migration `upgrade`/`downgrade`；这不是进程崩溃注入。
- 子进程凭据只通过 stdin 传递，不在 argv、环境变量、stdout/stderr。临时 DB、rollback journal 与备份只写在仓库 `.poc-data` 并由测试清理。

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_sqlcipher_compat_poc.py
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security --extra phase0-embedding pytest -q
```

当前全量本机 Python 测试 44 项通过；compileall 和 `uv lock --check` 通过；Swift 全量测试 12 项通过。

## 限制与未验收

- `max_page_count` 是受控 SQLite 页数上限模拟，不是 macOS 文件系统真实 ENOSPC、配额耗尽或磁盘设备故障。
- `os._exit` 验证事务未提交时的恢复；尚未做真实进程 SIGKILL/断电、损坏 rollback journal、WAL checkpoint、后端自动拉起和 GUI 会话恢复。
- 未覆盖真实备份介质读写错误、恢复中断回滚、备份校验失败及文件系统权限错误。
- 此 POC 不能证明产品可安全恢复用户数据库；没有产品 schema、正式 Keychain 密钥生命周期或发布 ADR。
