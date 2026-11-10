# Beta 本地持久化基础

最后核对：2026-11-10（Asia/Shanghai）

## 范围

此工作包已建立产品数据库的 SQLCipher 运行时、Keychain 密钥注入和初始 schema。Beta 启动经私有子进程标准输入向固定后端交付密钥并创建/迁移数据库。聊天已接入一个默认对话的读取、写入和手动删除；V2 任务已接入本机 CRUD、状态迁移和 30 天清理。确认记忆中心现可手动确认创建、列表、FTS 搜索和永久删除；不做自动抽取，Embedding 保持关闭。多对话管理、分页、备份恢复尚未接入。

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

1. 已实现用户手动确认记忆创建、列表、全文检索、永久删除与初始版本快照；来源追踪选择 UI、更新/纠错版本工作流、撤销时派生 FTS 清理尚未接入。
2. 聊天多对话管理、分页/搜索和大历史加载边界。
3. 任务状态迁移图目前是实现暂定规则；V2 完整验收前需要确认等待、部分完成、失败重试、暂停/取消的业务语义。30 天清理现于服务启动和任务列表读取时执行，长时间运行期间可能延至下一次触发。
4. 手动加密备份/恢复：独立口令的 KDF/参数版本、恢复认证、当前数据预备份、失败回滚、损坏文件拒绝、跨机器策略、RTO 与副本保留仍待实现或实测。
5. GUI 中的导出/删除控制，和真实 macOS Keychain、冻结/休眠/重启路径验收。

聊天及任务数据现写入本机加密数据库；用量记录仍为进程内临时数据；用户确认记忆已进入本机加密数据库。本轮没有实际启动 Beta，也未访问真实用户数据、Keychain、Provider、麦克风或 GUI。
