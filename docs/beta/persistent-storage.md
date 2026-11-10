# Beta 本地持久化基础

最后核对：2026-11-10（Asia/Shanghai）

## 范围

此工作包建立产品数据库的加密运行时入口与第一版 schema，为后续接入聊天、任务和已确认记忆提供基础。它**不代表 Beta 已启用持久化**：当前 Beta API/UI 没有创建或使用此 store，也没有读取或写入 Keychain。

用户已选择本地保存聊天、任务和经确认的记忆；聊天/记忆由用户手动删除，完成任务保留 30 天后清理。用户还选择 SQLCipher 与随机数据库密钥存 macOS Keychain。密钥生成、Keychain ACL/访问组、轮换与丢失恢复尚未实现，因此当前数据库入口要求调用方显式提供 32-byte 密钥，不能单独作为产品启动路径。

## 实现

- `backend/pac_poc/persistence.py` 提供 `EncryptedApplicationStore`，限定绝对路径、私有目录/文件权限、拒绝符号链接和错误密钥，并打开 SQLCipher WAL 数据库。
- `backend/pac_poc/migrations/` 提供随 wheel 打包的 Alembic 初始 migration。
- schema 包含 conversations、turns、messages 与 FTS；任务状态表为后续 V2 使用；memory_items 仅接受用户确认的 claim，并有版本记录和 ACTIVE 条件 FTS。FTS 由触发器同步；会话删除通过外键级联。
- SQLAlchemy、Alembic、SQLCipher 已从可选 POC 依赖移入默认后端依赖。发行材料仍需包含 SQLCipher Community attribution/NOTICE。

## 验证

- `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_persistence.py`：9 passed。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`：291 passed，1 条既有 Starlette/httpx 弃用警告。
- `uv run --locked ruff check pac_poc/persistence.py pac_poc/migrations tests/test_persistence.py`：通过。
- `uv run --locked mypy pac_poc/persistence.py`：通过。
- `uv lock --check`：通过；wheel 构建后确认 migrations 被打包。
- SBOM 与锁文件 63/63 非根包匹配；默认依赖闭包 28 个包。见 `../poc/phase0-python-sbom.md` 与 `../poc/phase0-model-license-review.md`。

## 尚未完成

1. macOS Keychain 随机密钥的创建、ACL、注入与登录后自动打开。
2. Beta API/SwiftUI 接入及聊天、任务、确认记忆的读写、分页、删除和并发行为。
3. 任务完成后 30 天清理，以及确认记忆撤销/派生 FTS 清理。
4. 手动加密备份/恢复：独立口令的 KDF/参数版本、恢复认证、当前数据预备份、失败回滚、损坏文件拒绝、跨机器策略、RTO 与副本保留仍待实现或实测。
5. GUI 中的导出/删除控制，和真实 macOS Keychain、冻结/休眠/重启路径验收。

在上述接入完成并通过对应回归前，产品仍沿用当前进程内临时数据行为。此阶段没有访问真实用户数据、Keychain、Provider、麦克风或 GUI。
