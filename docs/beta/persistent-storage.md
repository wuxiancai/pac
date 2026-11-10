# Beta 本地持久化基础

最后核对：2026-11-10（Asia/Shanghai）

## 范围

此工作包已建立产品数据库的 SQLCipher 运行时、Keychain 密钥注入和初始 schema。Beta 启动经私有子进程标准输入向固定后端交付密钥并创建/迁移数据库。聊天已接入本机多会话列表、新建、切换、重命名、分别删除，以及指定会话历史恢复/写入；初始历史最多 100 条，用户可加载更早记录；模型上下文限最近 20 条。V2 任务已接入本机 CRUD、状态迁移、完成后 30 天清理与可选本机提醒；重复状态变更幂等且不重置完成时间。过期完成任务与安全审计元数据在数据库密钥启动时立即清理，运行期间每 6 小时定时清理，退出时先取消维护任务。提醒默认关闭，只有用户显式启用时才请求 macOS 通知授权。应用启动会重建仍有效的待发提醒，任务完成、取消或删除时撤销提醒。通知授权、重启后系统实际投递和提醒时间边界尚未通过真实 GUI 验收。确认记忆中心支持手动确认创建、列表、FTS 搜索、显式确认编辑、版本历史只读查看和永久删除；每次编辑会追加版本快照，FTS 同步更新；创建时可从任一本机会话中选择来源消息，并按需加载更早历史页；删除会话后来源外键自动清空；来源消息可在记忆中心只读查看，并可跳转到原会话及对应历史消息，跨会话来源选择与跳转仍待 GUI 实机验收；不做自动抽取，Embedding 保持关闭；按 D-014 先做离线候选评测，评测后再决定产品启用。手动加密备份导出与当前 Mac 恢复已接通；D-006 已确认恢复前本机加密预备份只保留最近一份，新份创建时替换旧份，轮替已实现为固定路径原子替换，只在恢复切换成功后发布新副本；连续恢复回归确认目录只保留一份且内容为最新恢复前数据。断电/强制退出实机流程仍待验收。D-015 通用数据导出暂缓，仅提供加密备份/恢复。V2 本机日历/提醒事项读视图均已接入：用户点击后分别请求 EventKit 完整权限；日历仅展示未来 30 天事件，提醒事项展示未完成项目及到期信息；均不写、不持久化、不发给 Provider。2026-11-10 GUI 实机确认：日历只读面板读取成功并显示未来 30 天 2 项；提醒事项只读面板读取成功且无未来 30 天未完成条目。当前系统授权下实际读取路径通过；本轮未出现新授权弹窗，首次授权与拒绝路径仍未验证。

## 2026-11-10：会话分页请求并发保护

- SwiftUI 历史读取使用递增代际标识。开始切换会话、打开记忆来源、创建/删除会话、恢复备份或发送新消息时，之前发起的分页/选择请求会失效；响应落地前同时核对代际与会话 ID，避免迟到页面污染当前会话，或较早选择覆盖较新的会话选择。分页忙碌状态绑定请求 ID，切换时可释放旧状态，迟到旧请求不会清除新分页请求的忙碌状态。
- 验证：`swift test --package-path poc/macos-audio` → 68 项通过，新增两条协调器自动回归；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功。Beta 窗口本轮 CUA 连接超时，未做 GUI 并发点验；旧版本 GUI 来源跳转按钮验收及临时合成记忆清理仍待完成。该修复针对客户端竞态，不改变 SQLCipher 分页/API 契约。

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
- 每次启动重建和单条安排只接受未完成/未取消、时间可解析且仍在未来的任务；已过期、无效时间或终态任务会从本机待发通知中移除。纯逻辑回归覆盖有效时间、过去/无效/缺失时间以及完成/取消状态，不代表真实系统授权或通知投递。
- 用户拒绝通知授权或系统授权后来失效时，提醒开关恢复为关闭并清理本应用待发提醒；不转发到远端。

## 验证

- `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_persistence.py`：9 passed。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`：基础持久化阶段 291 passed；2026-11-10 记忆纠错/来源/版本历史后的最新后端全量 300 passed，1 条既有 Starlette/httpx 弃用警告；Swift 全量 51 项通过。
- `uv run --locked ruff check pac_poc/persistence.py pac_poc/migrations tests/test_persistence.py`：通过。
- 2026-11-10 `swift test --package-path poc/macos-audio`：62 项通过（含 Beta target 编译）；任务提醒时间资格、权限拒绝与授权撤销 mock 回归通过。没有请求通知权限或触发系统通知。
- Mock 回归确认拒绝/撤销会清理 `pac.task.*`，同时保留其他应用的 pending 通知；真实系统设置撤销行为仍待 GUI 实测。
- `uv run --locked mypy pac_poc/persistence.py`：通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_persistence.py -k 'long_conversation_history_pages or stable_bounded_keyset_pages'`（`backend/`）：2 passed；120 条消息跨 100 条默认页边界，无重复/遗漏。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --group dev pytest -q tests/test_backup.py`（`backend/`）：10 passed，含连续恢复后只保留一份且替换为最新快照。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`（`backend/`）：326 passed，1 条既有 Starlette/httpx 弃用警告。
- `swift test --package-path poc/macos-audio`：2026-11-10 全量 50 项通过；Beta `personal-assistant-beta` 构建成功。
- `uv run --locked ruff check pac_poc tests && uv run --locked mypy && uv lock --check`：通过；wheel 构建后确认 migrations 被打包。
- SBOM 与锁文件 63/63 非根包匹配；默认依赖闭包 28 个包。见 `../poc/phase0-python-sbom.md` 与 `../poc/phase0-model-license-review.md`。

## 尚未完成

### 2026-11-10 恢复切换安全补充

恢复切换使用 POSIX 生命周期锁：普通打开的 store 持共享锁，恢复要求独占锁；其他 store 活跃时 fail closed。独占锁保护启动时 rollback 恢复及专用 staging/marker 回收。子进程在切换前后硬退出的故障注入均恢复原会话并清理 rollback、marker 和三类 staging；同进程与独立进程持锁时均拒绝切换，释放后再次打开可正常恢复；另覆盖锁文件私有权限。物理断电、介质故障、Keychain 设备认证、完整 GUI 流程和 RTO 仍未验收。

本轮验证（跨进程锁回归后）：备份专项 15 passed；后端全量 346 passed（1 条既有 Starlette/httpx 弃用警告）；`mypy pac_poc` 37 个模块、`ruff check pac_poc tests scripts` 通过。

1. 删除记忆会同步删除其版本快照，FTS 由数据库触发器同步。新建记忆的来源选择目前支持本机全部会话及按需加载历史页；切换会话会使旧异步读取失效，防止迟到结果覆盖当前选择。2026-11-10 GUI 实机验证当前与另一条合成会话的来源消息均可载入并选择；完成按钮可关闭空表单；未保存主题/正文会弹确认，分别验证继续编辑与放弃后关闭，记忆数量仍为 0。未保存任何记忆。依赖已保存来源的查看/跳回原会话定位 GUI 验收仍待完成。
2. 会话历史已实现：初始最多 100 条，可通过有序 `(created_at,id)` keyset cursor 加载更早记录，SQLCipher schema 增加复合索引，SwiftUI 只在用户点击时拉取历史页并保留当前滚动锚点；已加载数据库行使用稳定消息 ID，临时流式消息使用稳定的本轮索引 ID，自动滚动与分页锚点共用同一行 ID。模型上下文仍限制最近 20 条。LazyVStack 当前对已加载消息做惰性视图创建，但尚无 SwiftUI 长会话压力与极大消息单体渲染验收。SQLCipher repository 新增 120 条消息跨 100 条分页边界的完整遍历回归（无重复/遗漏），不代表 GUI 渲染压力已通过。
3. D-018 已确认当前任务状态迁移图：`PENDING→READY/CANCELLED`；`READY→RUNNING/PAUSED/CANCELLED`；`RUNNING→WAITING/PARTIAL/COMPLETED/FAILED/CANCELLED`；`WAITING→READY/RUNNING/PAUSED/CANCELLED`；`PAUSED→READY/CANCELLED`；`PARTIAL→READY/COMPLETED/FAILED/CANCELLED`；`FAILED→READY/CANCELLED`；`COMPLETED` 与 `CANCELLED` 为终态。API 返回当前状态的 `allowed_transitions`，任务 UI 提供这些动作。状态只表示用户维护的计划，不代表后台执行；重复状态幂等，不重置 `completed_at`。到期清理在服务启动和任务列表读取时执行，服务运行期间另有每 6 小时周期清理。
4. 手动加密备份已接入认证 API 与 macOS UI：用户通过系统保存面板选择 `.pacbackup` 路径，输入每份独立口令后显式导出；口令不持久化，覆盖已有文件需保存面板确认。恢复前需确认并通过 macOS 设备认证；服务端验证容器口令、安装密钥指纹、SQLCipher 完整性/schema，创建当前数据库的私有本机 SQLCipher 预备份，再将内容在线复制到使用当前 Keychain 密钥加密的 staging DB 后切换；失败时从 rollback 文件还原。预备份放在 Application Support/PersonalAI/pre-restore，固定文件仅保留最近一份；校验并完成恢复切换后通过原子替换更新。失败时不会覆盖旧预备份。2026-11-10 子进程在恢复切换前/后硬退出后均可恢复旧库；POSIX 生命周期锁让打开的 store 持共享锁，恢复要求独占，并在启动独占恢复时清理专用 staging。新增同进程和独立进程持锁回归：其他 store/process 活跃时恢复 fail closed，旧库完整且临时文件清理。该自动化不代表物理断电/介质故障验收。GUI 导出一轮 274,726-byte 加密副本成功，随后恢复认证尝试停在“处理中”，未创建预备份、数据库 mtime 未变化，未进入切换；临时副本已删除。新 Beta 实测系统文件面板正常，旧实例未弹出面板的原因仍未判定。默认保存名双后缀已修复；恢复 UI 已将认证恢复与导出状态区分，防止“正在备份”误报恢复进度。Beta 包现包含并在构建时校验 `NSFaceIDUsageDescription`（用途说明根据 [Apple LocalAuthentication 文档](https://developer.apple.com/documentation/localauthentication/lacontext) 添加），但最新 Beta GUI 重试依旧无认证提示；独立系统认证 POC 也进入等待态，约 30 秒没有返回。因此配置缺失仅是一个真实打包缺口，未证明是本机认证停滞的根因。应用退出后临时备份已清理；未检查 Library 数据库，不推断本轮切换状态。LocalAuthentication 提示/回调仍待诊断。用户自选本地目录路径已在 GUI 实测：保存面板导航到 `/Users/wuxiancai/Documents` 并成功导出 274,726 bytes，文件核实后删除；此项不覆盖外接卷。恢复界面现可显式取消进行中的 LocalAuthentication 请求（通过使 LAContext 失效），认证阶段禁止关闭表单；GUI 取消后返回 LAError，但当前系统文字为英文。新增错误映射单测已通过，因 CUA 重开新包超时，中文映射暂未实机复核。认证提示/成功回调与恢复本身仍未验收，错误口令、断电/强制退出完整 GUI、Keychain 实机验证和 RTO 仍未完成。

2026-11-10 本轮补充：Beta 备份表单临时口令已输入后，对 accessibility 导出按钮连续两次点击均未触发可见 NSSavePanel，口令已清空并关闭表单；无导出调用或新备份。此现象仍无法区分自动化点击未触发 action 与系统面板呈现问题，不推翻先前成功导出证据；下次先用可观察的键盘/人工点击确认 action。

2026-11-10 面板改造：保存和打开 `NSSavePanel`/`NSOpenPanel` 改用异步窗口 sheet，以避免同步模态调用阻塞 SwiftUI；取消保存选择时保留口令。Swift 86 项和 Beta 打包成功。新包 GUI 未能被 CUA 访问，故实际保存/打开面板仍待实机验收。

2026-11-10 面板根因与 GUI 验收：备份 sheet 中 `NSApp.keyWindow/mainWindow` 都为空，导致前次改造提示无法打开面板。改为通过 `NSViewRepresentable` 捕获 sheet 实际 `NSWindow` 并传给异步面板后，GUI 保存和打开均成功；文件名 `PAC-B3-AsyncPanel-20261110.pacbackup`，274,726 bytes。另验证取消保存保留口令。随后清空口令并删除临时文件；未执行恢复。新应用首启 Keychain 数据库密钥错误一次，点击重试后本机服务连接成功，原因未判定。

2026-11-10 数据库密钥错误诊断：`DatabaseKeychainError` 现提供中文错误类别和 OSStatus，覆盖无效身份、无效存储密钥、随机数生成和 Keychain 读写失败；对无效存储密钥明确不自动换钥。描述不含密钥内容。Swift 全量 87 passed，Beta build 成功。此前 GUI 首启错误经重试恢复，尚未重现以确定具体类别/状态。

2026-11-10 Keychain 生命周期自动回归：为 `DatabaseKeychainStore` 注入内部 Security 适配器 seam，并以 fake 覆盖现存 32-byte key 只读、缺失时安全随机创建及 `WhenUnlockedThisDeviceOnly` 属性、`errSecDuplicateItem` 后读取竞争胜出的已存键、malformed existing key 不尝试替换、Keychain read/random/write 失败时拒绝启动密钥交付。Swift 全量 92 passed，Beta build 成功。没有操作真实 Keychain；ACL、应用签名访问控制和休眠/重启路径仍待实机验收。
5. 记忆来源跨会话选择/跳转的 GUI 实机验收；真实 macOS Keychain 与冻结/休眠/重启路径验收。
6. 本机任务通知的真实系统授权、投递/过期行为及重启恢复验收；当前测试仅覆盖 stable identifier 与客户端/后端契约，不声称已验证系统投递。

聊天及任务数据现写入本机加密数据库；用量记录仍为进程内临时数据；用户确认记忆已进入本机加密数据库。2026-11-10 日历/提醒事项面板实机仅读取系统摘要，未编辑、保存或发送内容。任务提醒系统通知授权/投递与重启恢复仍未验收；Keychain、Provider、麦克风和备份恢复未在本次 GUI 操作中访问。

2026-11-10 已保存来源跳转 GUI 尝试：为验收创建临时合成确认记忆 `临时验收记忆 PAC-MEMORY-JUMP-20261110`，已成功读取关联用户消息详情。发现卡片行内操作拥挤且来源跳转位于未显示的 toolbar secondary action；已将操作独立成行、将“在对话中查看”改成详情显式按钮。Swift 全量 63 passed，Beta target build 通过。改版重启后 CUA 连续超时，跳转及删除临时记忆尚未完成；待恢复 GUI 后优先清理该记录。
