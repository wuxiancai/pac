# 阶段 0 POC：SQLCipher / FTS5 / SQLAlchemy / Alembic 兼容性（工作包 0F）

状态：`IN_PROGRESS`。这只是本机候选方案兼容性验证；没有选定产品加密方案，也没有更改产品数据库 schema。

## 本机结果

- 当前设备：ARM64；本机 Python 3.12 环境安装了可运行的 `sqlcipher3==0.6.3`。
- 运行时报告 SQLCipher `4.12.0 community`；编译选项含 `HAS_CODEC` 和 `ENABLE_FTS5`。
- 加密 POC 文件头不是标准 SQLite 明文头；正确密钥可检索 FTS5；错误密钥不能打开。
- SQLCipher Online Backup API 生成另一把 key 加密的备份；备份文件仍加密，数据库原 key 不能打开备份，备份 key 可以恢复并进行 FTS 检索。
- SQLAlchemy `2.1.8` 的 `sqlite+pysqlcipher` dialect 与 Alembic `1.20.1` 在 ARM64/Python 3.12 上完成临时 migration upgrade、FTS5 查询及 downgrade。SQLAlchemy URL 的字符串展示隐藏 passphrase，Engine echo 关闭；key 只在进程内测试对象中使用。
- 迁移仅位于 `backend/poc_migrations/sqlcipher_compat/`，只操作 `.poc-data/sqlcipher-tests` 下的临时 POC DB，测试结束清理。未建立产品数据表或运行时迁移。
- SQLCipher、SQLAlchemy、Alembic 放在可选 `phase0-security` extra，不会被默认环境强制安装或固化为产品依赖。

## 后续补充验证（截至 2026-11-07）

- **WAL 数据库备份/恢复**：SQLCipher WAL 下已验证 checkpoint、活动 reader 导致 checkpoint `busy=1` 后释放/重试，以及 WAL 源库以独立密钥备份、恢复 memory/FTS 并检查完整性。WAL 备份用例没有并发 writer/reader。
- 已验证事务在 `os._exit`、DELETE/WAL 模式 SIGKILL 后恢复；备份 staging 已复制部分页面时对隔离子进程 SIGKILL，旧目标备份仍可恢复、源库完整。进程被杀后会遗留加密 `.partial`；产品生命周期/清理策略仍未决，POC 不扫描目录。
- 备份复制失败、staging 校验失败、`os.replace` 返回错误三种注入路径均保留原目标备份并保持源库可用。成功路径先校验 staging，再原子替换目标。
- 页数上限模拟触发写入失败后，已有 memory/FTS 仍可检索；这不是文件系统真实 ENOSPC。

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security pytest -q tests/test_sqlcipher_compat_poc.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security pytest -q
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security python -m compileall -q pac_poc poc_migrations scripts tests
uv lock --check
```

- SQLCipher 专项测试：15 项通过（包含 WAL 备份/恢复及进程中断故障注入）。
- 当前全量本机 Python 测试：115 项通过，包含 `phase0-security` 与 `phase0-embedding` extras。
- `compileall`、`uv lock --check` 与 `git diff --check` 通过。
- 已有一项相同合成工作负载的 SQLite/SQLCipher + FTS5 三轮本机观察，详见 `phase0-sqlcipher-performance.md`；它不是完整 App 或产品负载性能验收。

## 未解决/未验收

- 没有评估 key 生命周期、Keychain/Touch ID 解锁、密钥轮换、丢失恢复、备份密钥独立保存的用户流程；测试 passphrase 不是用户凭据。
- 并发连接池、并发写/读期间备份、恢复失败回滚、真实 ENOSPC、macOS 发布打包签名/notarization、x86_64/universal2 及最低系统版本尚未验证。
- 真实用户规模、冷/热启动、长期运行、并发负载、CPU/RSS 及外接盘/NAS 性能未测；当前仅有三轮合成工作负载对照，未据此做产品取舍。
- 尚未完成其他成熟加密候选比较、最终 ADR 和恢复演练，因此不得宣告静态加密验收完成。

## 版本与安全边界

此 extra 是阶段 0 的可选工具，不等于 V1 已集成 SQLCipher。产品 API Key 仍只能经 Keychain 管理；SQLCipher 测试 key 与 Provider API Key 是不同数据，不写数据库日志或普通配置。V1 的所有产品 schema 仍必须通过 Alembic migration，并带备份/回滚说明。
