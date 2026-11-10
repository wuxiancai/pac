# Beta 本地持久化基础

最后核对：2026-11-10（Asia/Shanghai）

## 范围

此工作包建立产品数据库的加密运行时入口与第一版 schema，为后续接入聊天、任务和已确认记忆提供基础。它**不代表 Beta 已启用持久化**：当前 Beta API/UI 没有创建或使用此 store，Beta 启动现在会从 Keychain 取得该密钥，通过私有子进程标准输入交给固定后端，并在后端创建/迁移 SQLCipher 数据库；聊天当前已接入一个默认对话的读取、写入和手动删除；任务、记忆 CRUD、多个对话管理和分页尚未接入。

用户已选择本地保存聊天、任务和经确认的记忆；聊天/记忆由用户手动删除，完成任务保留 30 天后清理。用户还选择 SQLCipher 与随机数据库密钥存 macOS Keychain。密钥通过 `DatabaseKeychainStore` 使用系统随机源首次生成并存入 `WhenUnlockedThisDeviceOnly` 项。启动协议不在参数/环境/握手中放密钥，仅从专用子进程标准输入读取精确 32-byte hex 行；Keychain ACL 的实机验证、轮换与丢失恢复尚未完成。

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
2. 任务、确认记忆的读写；聊天多对话管理、分页/搜索及大历史加载边界。当前默认对话的聊天读取、写入、删除已接入 Beta API/SwiftUI。
3. 任务完成后 30 天清理，以及确认记忆撤销/派生 FTS 清理。
4. 手动加密备份/恢复：独立口令的 KDF/参数版本、恢复认证、当前数据预备份、失败回滚、损坏文件拒绝、跨机器策略、RTO 与副本保留仍待实现或实测。
5. GUI 中的导出/删除控制，和真实 macOS Keychain、冻结/休眠/重启路径验收。

聊天数据现已写入本机加密数据库；任务、已确认记忆和用量记录仍是进程内临时数据。本轮没有实际启动 Beta，也未访问真实用户数据、Keychain、Provider、麦克风或 GUI。
