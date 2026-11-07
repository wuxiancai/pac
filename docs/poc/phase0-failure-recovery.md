# 阶段 0 POC：本机异常恢复与磁盘耗尽（工作包 0H）

状态：`IN_PROGRESS`。故障注入仅作用于 `.poc-data/sqlcipher-tests` 下的临时 SQLCipher 文件。

## 故障注入结果

- **进程异常退出**：子进程从 stdin 读取临时 key，打开加密数据库，在显式事务内写入 memory 与 FTS 行后用 `os._exit(73)` 突然退出。重新打开数据库后，已提交 baseline 仍可搜索，未提交 marker 不存在，`PRAGMA integrity_check` 返回 `ok`。
- **OS SIGKILL**：测试启动隔离子进程，在未提交 memory/FTS 事务后通过 stdout `READY` 信号通知测试进程；测试对该 PID 发送 `SIGKILL`。进程退出码为 `-SIGKILL`，重新打开后提交数据存在、未提交 marker 不存在、完整性检查为 `ok`。DELETE rollback journal 与 WAL 两种配置分别通过。本项不代表断电、存储控制器缓存或真实硬件断电语义。
- **WAL TRUNCATE checkpoint**：在 SQLCipher 加密 POC 数据库上启用 WAL，写入已提交 memory/FTS 记录，执行受限模式的 `PRAGMA wal_checkpoint(TRUNCATE)`，检查 busy=0 且 checkpointed frames 与 log frames 相等；关闭并重开后检索结果和 `integrity_check` 均通过。checkpoint API 对 mode 使用枚举白名单，拒绝任意 SQL 文本。仅验证该临时数据库路径，不代表 App 退出时的正式 checkpoint 调度。
- **WAL 数据库备份/恢复**：在源 SQLCipher DB 启用 WAL 并提交两条 memory/FTS 记录，通过单独备份密钥生成加密备份；源库和恢复库均可检索提交数据且 `integrity_check=ok`。该测试未在并发写入、活动 reader 或 WAL checkpoint 受阻状态下执行备份，也不确定产品 WAL 生命周期策略。
- **活动 WAL reader 下 checkpoint 受阻与重试**：reader 连接开启事务并固定 snapshot 后，writer 提交新 memory/FTS 行并尝试 `TRUNCATE` checkpoint；SQLCipher 返回 `busy=1`，writer 仍能检索新提交数据。释放并关闭 reader 后重试返回 `busy=0` 且 checkpointed frames 与 log frames 相等；关闭并重开数据库，两条记录均可检索且 `integrity_check=ok`。该用例证明受阻状态可见并能在读锁释放后恢复，不证明 checkpoint 执行中断电或 SIGKILL 的原子性。
- **磁盘页数耗尽模拟**：将 SQLCipher POC DB 的 `max_page_count` 限制到当前页数 + 1，插入大记录触发 DBAPI 数据库错误。事务回滚后旧记忆和 FTS 仍可检索，失败记录不存在，完整性检查为 `ok`。
- **Alembic 回滚**：工作包 0F 已验证 POC migration `upgrade`/`downgrade`；这不是进程崩溃注入。
- **备份目标不可创建**：将 backup 的父路径预置为普通文件，模拟目标目录不可用；接口返回不含凭据的 `SQLCipherPOCError`，源 DB 查询与完整性检查仍通过。该故障注入验证错误目标路径，不等同真实备份介质 I/O 故障。
- **已有备份时复制/校验/替换失败**：分别在 backup 调用边界注入 SQLite 数据库错误、注入 staging 校验不通过、模拟 `os.replace` 抛出 `OSError`；三种情况下接口均显式失败，旧备份仍可用原密钥解密、查询和通过 `integrity_check`，源数据库也保持可查询/完整，临时 `.partial` 文件清理。正常成功路径先将数据写入同目录加密 staging 文件、重新打开并完整性校验，再通过 `os.replace` 原子替换目标。注入故障不是损坏介质测试，也不证明所有文件系统/介质上的断电原子性。
- **备份复制期间子进程 SIGKILL**：测试构造 80 条带较大索引内容的加密源记录及可解密旧目标备份。故障注入子进程经 stdin 接收源/备份 key，在 SQLCipher backup progress callback 确认 staging 已复制部分页面后发出 `BACKUP_COPY_PROGRESS`；测试向该子进程发送 SIGKILL。旧目标仍能用旧密钥检索并通过 `integrity_check`；源库全部记录仍在且完整。SIGKILL 绕过正常 finally 清理，测试观察到加密 `.partial` 遗留并在 teardown 清除。此项仅证明本机临时数据库在该注入点的进程终止恢复，不代表断电、设备缓存或其他文件系统语义。
- 子进程凭据只通过 stdin 传递，不在 argv、环境变量、stdout/stderr。临时 DB、rollback journal 与备份只写在仓库 `.poc-data` 并由测试清理。

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_sqlcipher_compat_poc.py
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security --extra phase0-embedding pytest -q
```

本报告最初提交时全量本机 Python 测试 44 项通过；当前完整回归数量以 `docs/HANDOFF.md` 的最新记录为准。

## 限制与未验收

- `max_page_count` 是受控 SQLite 页数上限模拟，不是 macOS 文件系统真实 ENOSPC、配额耗尽或磁盘设备故障。
- `os._exit` 与真实子进程 `SIGKILL` 均验证未提交事务恢复；WAL 下验证 SIGKILL 后恢复、正常 TRUNCATE checkpoint 及活动 reader 导致 busy 后的释放/重试。未覆盖断电、损坏 rollback journal、checkpoint 执行中 SIGKILL、后端自动拉起和 GUI 会话恢复。
- 未覆盖真实备份介质读写错误、恢复中断回滚、SIGKILL 恰好发生于原子替换系统调用、空间配额耗尽及文件系统权限错误。备份复制中 SIGKILL 会遗留 staging 文件；应用启动时的临时文件清理/保留策略尚未决定，当前 POC 不扫描目录。校验失败有完整性门禁，但尚未以损坏数据注入覆盖。
- 此 POC 不能证明产品可安全恢复用户数据库；没有产品 schema、正式 Keychain 密钥生命周期或发布 ADR。
