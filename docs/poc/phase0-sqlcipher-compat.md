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

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security pytest -q tests/test_sqlcipher_compat_poc.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security pytest -q
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security python -m compileall -q pac_poc poc_migrations scripts tests
uv lock --check
```

- SQLCipher 独立测试：3 项通过。
- 当时全量本机测试：35 项通过。
- 没有测量或推断性能数据。

## 未解决/未验收

- 没有评估 key 生命周期、Keychain/Touch ID 解锁、密钥轮换、丢失恢复、备份密钥独立保存的用户流程；测试 passphrase 不是用户凭据。
- WAL/checkpoint、并发连接池、崩溃中断、磁盘不足、恢复失败回滚、macOS 发布打包签名/notarization、x86_64/universal2 及最低系统版本尚未验证。
- SQLCipher 与普通 SQLite 的性能、升级迁移以及外接盘/NAS行为未测；SQLAlchemy 官方说明其 SQLCipher dialect 需特殊连接设置且加密连接可能更慢，未据此做产品取舍。
- 尚未完成其他成熟加密候选比较、最终 ADR 和恢复演练，因此不得宣告静态加密验收完成。

## 版本与安全边界

此 extra 是阶段 0 的可选工具，不等于 V1 已集成 SQLCipher。产品 API Key 仍只能经 Keychain 管理；SQLCipher 测试 key 与 Provider API Key 是不同数据，不写数据库日志或普通配置。V1 的所有产品 schema 仍必须通过 Alembic migration，并带备份/回滚说明。
