# Beta 本地持久化基础

最后核对：2026-11-10（Asia/Shanghai）

## 范围

此工作包已建立产品数据库的 SQLCipher 运行时、Keychain 密钥注入和初始 schema。Beta 启动经私有子进程标准输入向固定后端交付密钥并创建/迁移数据库。聊天已接入本机多会话列表、新建、切换、重命名、分别删除，以及指定会话历史恢复/写入；模型上下文限最近 20 条。V2 任务已接入本机 CRUD、状态迁移、完成后 30 天清理与可选本机提醒；提醒默认关闭，只有用户显式启用时才请求 macOS 通知授权。应用启动会重建仍有效的待发提醒，任务完成、取消或删除时撤销提醒。通知授权、重启后系统实际投递和提醒时间边界尚未通过真实 GUI 验收。确认记忆中心支持手动确认创建、列表、FTS 搜索、显式确认编辑、版本历史只读查看和永久删除；每次编辑会追加版本快照，FTS 同步更新；可在创建时将记忆关联至当前会话中的历史消息，删除会话后来源外键自动清空；来源消息可在记忆中心只读查看，不做自动抽取，Embedding 保持关闭。会话历史仍整段载入 UI、没有分页/虚拟化；备份恢复尚未接入。

用户已选择本地保存聊天、任务和经确认的记忆；聊天/记忆由用户手动删除，完成任务保留 30 天后清理。用户还选择 SQLCipher 与随机数据库密钥存 macOS Keychain。密钥通过 `DatabaseKeychainStore` 使用系统随机源首次生成并存入 `WhenUnlockedThisDeviceOnly` 项。启动协议不在参数/环境/握手中放密钥，仅从专用子进程标准输入读取精确 32-byte hex 行；Keychain ACL 的实机验证、轮换与丢失恢复尚未完成。

## 实现

- `backend/pac_poc/persistence.py` 提供 `EncryptedApplicationStore`，限定绝对路径、私有目录/文件权限、拒绝符号链接和错误密钥，并打开 SQLCipher WAL 数据库。
- `backend/pac_poc/migrations/` 提供随 wheel 打包的 Alembic 初始 migration。
- 会话支持显式重命名，标题与更新时刻写入加密数据库。
- schema 包含 conversations、turns、messages 与 FTS；任务状态表为后续 V2 使用；memory_items 仅接受用户确认的 claim，并有版本记录和 ACTIVE 条件 FTS。FTS 由触发器同步；会话删除通过外键级联。
- SQLAlchemy、Alembic、SQLCipher 已从可选 POC 依赖移入默认后端依赖。发行材料仍需包含 SQLCipher Community attribution/NOTICE。
- `GET /memories/{id}/versions` 提供有界只读快照历史，UI 展示版本号、变更原因、时间、类别、主题和内容。
- 任务可保存可选 `schedule_at`；`TaskReminderManager` 仅安排本机通知。系统授权需由用户点击开启，拒绝授权不会自动改走远端通知。

## 验证

- `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_persistence.py`：9 passed。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`：基础持久化阶段 291 passed；2026-11-10 记忆纠错/来源/版本历史后的最新后端全量 300 passed，1 条既有 Starlette/httpx 弃用警告；Swift 全量 51 项通过。
- `uv run --locked ruff check pac_poc/persistence.py pac_poc/migrations tests/test_persistence.py`：通过。
- `uv run --locked mypy pac_poc/persistence.py`：通过。
- `swift test --package-path poc/macos-audio`：2026-11-10 全量 50 项通过；Beta `personal-assistant-beta` 构建成功。
- `uv run --locked ruff check pac_poc tests && uv run --locked mypy && uv lock --check`：通过；wheel 构建后确认 migrations 被打包。
- SBOM 与锁文件 63/63 非根包匹配；默认依赖闭包 28 个包。见 `../poc/phase0-python-sbom.md` 与 `../poc/phase0-model-license-review.md`。

## 尚未完成

1. 删除记忆会同步删除其版本快照，FTS 由数据库触发器同步。来源目前可选当前会话中已有稳定 ID 的消息，不支持跨会话选择或跳转。
2. 会话历史分页/虚拟化与大历史加载边界。
3. 任务状态迁移图目前是实现暂定规则；V2 完整验收前需要确认等待、部分完成、失败重试、暂停/取消的业务语义。30 天清理现于服务启动和任务列表读取时执行，长时间运行期间可能延至下一次触发。
4. 手动加密备份已接入认证 API 与 macOS UI：用户通过系统保存面板选择 `.pacbackup` 路径，输入每份独立口令后显式导出；口令不持久化，覆盖已有文件需保存面板确认。已实现版本化 scrypt 容器及 SQLCipher 在线导出：每份随机 16-byte salt、N=32768/r=8/p=1、32-byte 派生密钥、头部 HMAC、当前数据库密钥指纹绑定、临时 SQLCipher 在线快照/完整性校验与 0600 原子目标写入。当前窄回归 47 passed，Swift 全量 52 项通过，Ruff/mypy/锁文件检查通过，Beta build 成功；恢复前预备份、恢复换库/回滚和系统认证流程待实现。
5. GUI 中的导出控制、记忆来源跨会话跳转；真实 macOS Keychain 与冻结/休眠/重启路径验收。
6. 本机任务通知的真实系统授权、投递/过期行为及重启恢复验收；当前测试仅覆盖 stable identifier 与客户端/后端契约，不声称已验证系统投递。

聊天及任务数据现写入本机加密数据库；用量记录仍为进程内临时数据；用户确认记忆已进入本机加密数据库。任务提醒实现期间未实际启动 Beta、未请求 macOS 通知授权，也未访问真实用户数据、Keychain、Provider、麦克风或 GUI。
