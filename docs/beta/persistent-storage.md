# Beta 本地持久化基础

最后核对：2026-11-10（Asia/Shanghai）

## 范围

此工作包已建立产品数据库的 SQLCipher 运行时、Keychain 密钥注入和初始 schema。Beta 启动经私有子进程标准输入向固定后端交付密钥并创建/迁移数据库。聊天已接入本机多会话列表、新建、切换、重命名、分别删除，以及指定会话历史恢复/写入；初始历史最多 100 条，用户可加载更早记录；模型上下文限最近 20 条。V2 任务已接入本机 CRUD、状态迁移、完成后 30 天清理与可选本机提醒；重复状态变更幂等且不重置完成时间。过期完成任务与安全审计元数据在数据库密钥启动时立即清理，运行期间每 6 小时定时清理，退出时先取消维护任务。提醒默认关闭，只有用户显式启用时才请求 macOS 通知授权。应用启动会重建仍有效的待发提醒，任务完成、取消或删除时撤销提醒。通知授权、重启后系统实际投递和提醒时间边界尚未通过真实 GUI 验收。确认记忆中心支持手动确认创建、列表、FTS 搜索、显式确认编辑、版本历史只读查看和永久删除；每次编辑会追加版本快照，FTS 同步更新；创建时可从任一本机会话中选择来源消息，并按需加载更早历史页；删除会话后来源外键自动清空；来源消息可在记忆中心只读查看，并可跳转到原会话及对应历史消息，跨会话来源选择与跳转仍待 GUI 实机验收；不做自动抽取，Embedding 保持关闭；按 D-014 先做离线候选评测，评测后再决定产品启用。手动加密备份导出与当前 Mac 恢复已接通；D-006 已确认恢复前本机加密预备份只保留最近一份，新份创建时替换旧份，轮替已实现为固定路径原子替换，只在恢复切换成功后发布新副本；连续恢复回归确认目录只保留一份且内容为最新恢复前数据。断电/强制退出实机流程仍待验收。D-015 通用数据导出暂缓，仅提供加密备份/恢复。V2 本机日历/提醒事项读视图均已接入：用户点击后分别请求 EventKit 完整权限；日历仅展示未来 30 天事件，提醒事项展示未完成项目及到期信息；均不写、不持久化、不发给 Provider。

用户已选择本地保存聊天、任务和经确认的记忆；聊天/记忆由用户手动删除，完成任务保留 30 天后清理。用户还选择 SQLCipher 与随机数据库密钥存 macOS Keychain。密钥通过 `DatabaseKeychainStore` 使用系统随机源首次生成并存入 `WhenUnlockedThisDeviceOnly` 项。启动协议不在参数/环境/握手中放密钥，仅从专用子进程标准输入读取精确 32-byte hex 行；Keychain ACL 的实机验证、轮换与丢失恢复尚未完成。

## 实现

- `backend/pac_poc/persistence.py` 提供 `EncryptedApplicationStore`，限定绝对路径、私有目录/文件权限、拒绝符号链接和错误密钥，并打开 SQLCipher WAL 数据库。
- `backend/pac_poc/migrations/` 提供随 wheel 打包的 Alembic 初始 migration。
- migration `0003_local_skills` 在 SQLCipher store 内安装三个固定、只含提示文本的本机 Skills；读取接口不返回提示定义，不开放用户编辑或执行工具。聊天请求必须逐次提交登记的 skill keys。
- 会话支持显式重命名，标题与更新时刻写入加密数据库。
- schema 包含 conversations、turns、messages 与 FTS；`0004_monthly_cloud_budget` 在 SQLCipher 内只存逐月估算总额/请求数/价目版本，不保存对话内容；任务状态表为后续 V2 使用；memory_items 仅接受用户确认的 claim，并有版本记录和 ACTIVE 条件 FTS。FTS 由触发器同步；会话删除通过外键级联。
- SQLAlchemy、Alembic、SQLCipher 已从可选 POC 依赖移入默认后端依赖。发行材料仍需包含 SQLCipher Community attribution/NOTICE。
- `GET /memories/{id}/versions` 提供有界只读快照历史，UI 展示版本号、变更原因、时间、类别、主题和内容。
- 任务可保存可选 `schedule_at`；`TaskReminderManager` 仅安排本机通知。系统授权需由用户点击开启，拒绝授权不会自动改走远端通知。

## 验证

- `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_persistence.py`：9 passed。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`：基础持久化阶段 291 passed；2026-11-10 记忆纠错/来源/版本历史后的最新后端全量 300 passed，1 条既有 Starlette/httpx 弃用警告；Swift 全量 51 项通过。
- `uv run --locked ruff check pac_poc/persistence.py pac_poc/migrations tests/test_persistence.py`：通过。
- `uv run --locked mypy pac_poc/persistence.py`：通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_persistence.py -k 'long_conversation_history_pages or stable_bounded_keyset_pages'`（`backend/`）：2 passed；120 条消息跨 100 条默认页边界，无重复/遗漏。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_backup.py`（`backend/`）：10 passed，含连续恢复后只保留一份且替换为最新快照。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`（`backend/`）：326 passed，1 条既有 Starlette/httpx 弃用警告。
- `swift test --package-path poc/macos-audio`：2026-11-10 全量 50 项通过；Beta `personal-assistant-beta` 构建成功。
- `uv run --locked ruff check pac_poc tests && uv run --locked mypy && uv lock --check`：通过；wheel 构建后确认 migrations 被打包。
- SBOM 与锁文件 63/63 非根包匹配；默认依赖闭包 28 个包。见 `../poc/phase0-python-sbom.md` 与 `../poc/phase0-model-license-review.md`。

## 尚未完成

1. 删除记忆会同步删除其版本快照，FTS 由数据库触发器同步。新建记忆的来源选择目前支持本机全部会话及按需加载历史页；来源读取、跨会话定位的 GUI 实机验收仍待完成。
2. 会话历史已实现：初始最多 100 条，可通过有序 `(created_at,id)` keyset cursor 加载更早记录，SQLCipher schema 增加复合索引，SwiftUI 只在用户点击时拉取历史页并保留当前滚动锚点；已加载数据库行使用稳定消息 ID，临时流式消息使用稳定的本轮索引 ID，自动滚动与分页锚点共用同一行 ID。模型上下文仍限制最近 20 条。LazyVStack 当前对已加载消息做惰性视图创建，但尚无 SwiftUI 长会话压力与极大消息单体渲染验收。SQLCipher repository 新增 120 条消息跨 100 条分页边界的完整遍历回归（无重复/遗漏），不代表 GUI 渲染压力已通过。
3. D-018 已确认当前任务状态迁移图：`PENDING→READY/CANCELLED`；`READY→RUNNING/PAUSED/CANCELLED`；`RUNNING→WAITING/PARTIAL/COMPLETED/FAILED/CANCELLED`；`WAITING→READY/RUNNING/PAUSED/CANCELLED`；`PAUSED→READY/CANCELLED`；`PARTIAL→READY/COMPLETED/FAILED/CANCELLED`；`FAILED→READY/CANCELLED`；`COMPLETED` 与 `CANCELLED` 为终态。API 返回当前状态的 `allowed_transitions`，任务 UI 提供这些动作。状态只表示用户维护的计划，不代表后台执行；重复状态幂等，不重置 `completed_at`。到期清理在服务启动和任务列表读取时执行，服务运行期间另有每 6 小时周期清理。
4. 手动加密备份已接入认证 API 与 macOS UI：用户通过系统保存面板选择 `.pacbackup` 路径，输入每份独立口令后显式导出；口令不持久化，覆盖已有文件需保存面板确认。恢复前需确认并通过 macOS 设备认证；服务端验证容器口令、安装密钥指纹、SQLCipher 完整性/schema，创建当前数据库的私有本机 SQLCipher 预备份，再将内容在线复制到使用当前 Keychain 密钥加密的 staging DB 后切换；失败时从 rollback 文件还原。预备份放在 Application Support/PersonalAI/pre-restore，固定文件仅保留最近一份；校验并完成恢复切换后通过原子替换更新。失败时不会覆盖旧预备份。当前备份相关窄回归 12 passed，Swift 全量 53 项通过，后端全量 312 passed、1 条既有 Starlette/httpx 弃用警告；Ruff/mypy/锁文件检查通过，Beta build 成功。启动时若唯一未提交 rollback 文件存在，会先还原旧库；多个候选则 fail-closed。GUI、Keychain 实机认证、强制终止/断电期间恢复与 RTO 验收未做。
5. 记忆来源跨会话选择/跳转的 GUI 实机验收；真实 macOS Keychain 与冻结/休眠/重启路径验收。
6. 本机任务通知的真实系统授权、投递/过期行为及重启恢复验收；当前测试仅覆盖 stable identifier 与客户端/后端契约，不声称已验证系统投递。

聊天及任务数据现写入本机加密数据库；用量记录仍为进程内临时数据；用户确认记忆已进入本机加密数据库。任务提醒实现期间未实际启动 Beta、未请求 macOS 通知授权，也未访问真实用户数据、Keychain、Provider、麦克风或 GUI。
