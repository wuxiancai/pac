# 项目上下文

最后核对：2026-11-10（Asia/Shanghai）

## 项目目标

依据 [个人 AI 助理开发规格 v1.2](../个人AI助理可执行开发规格书%20v1.2.md)，建设本机优先的个人 AI 助理。当前按 C-007 建设单用户 macOS 测试版；2026-11-10 用户将目标扩展至 V1.1、V2、V3，仍按阶段门禁推进。阶段 0 未完成验证按功能启用或正式发布时逐项补齐。

## 当前状态

- 2026-11-10 B3 恢复抗崩溃与并发协调：子进程在恢复切换前/后硬退出后，启动恢复完整旧会话并清理 rollback、marker 和 3 类加密 staging；POSIX shared/exclusive 生命周期锁允许多个 store 正常共存，恢复需独占，其他实例仍打开时 fail closed。自动回归覆盖私有锁文件、同进程多 store 与独立子进程持锁时拒绝恢复；后端全量最新 346 passed。完整应用 GUI/Keychain 认证、断电实机和 RTO 仍待验证。
- 2026-11-10 B1 本机错误 UI：新建本机会话中临时选择不存在的 Ollama 模型并发送合成短句，GUI 正确显示本机检查提示、本轮失败且无云 fallback；随后恢复 `qwen3.5:0.8b` 并确认服务状态恢复。测试对话保留在 SQLCipher 历史。仍需验证 Ollama 停止/恢复路径和云 API 错误 UI；详见 `docs/beta/macOS-beta-chat.md`。
- 2026-11-10 阶段 6 本机门禁复核：后端全量 341 passed（1 条既有弃用警告），Ruff 全目录、CI mypy、compileall、`uv lock --check`、tracked-file detect-secrets、Swift 60 项和 Beta target 构建均通过；测试口令扫描误报已逐行标注并复扫通过。之后已实机验证 B6 当前授权下日历/提醒事项只读查询；首次授权/拒绝以及 B1/B3/B5 其他 GUI 验收仍未完成。未运行远端 Actions、Provider 或麦克风。阶段 6 保持开放，详见 `docs/HANDOFF.md`。
- 2026-11-10 范围扩展：用户要求完成 V1.1、V2、V3 开发。用户已决定本地持久化聊天、任务和已确认记忆；聊天/已确认记忆手动删除，完成任务 30 天后清理。SQLCipher + Keychain 随机密钥、登录后自动打开已选为加密方向，正式密钥生命周期/产品验证仍未完成；已选手动加密备份到用户位置、每份独立口令、恢复前认证与预备份，RTO/副本保留和恢复故障验证待完成；备份采用 scrypt（N=32768,r=8,p=1）、不保存口令且仅当前 Mac 恢复；Embedding 按 D-014 先做离线候选评测、再决定产品启用。当前三次合成离线结果一致：24 条改写候选 23/24 top-1、24/24 top-3，FTS5 0/24；12 条词面控制均 12/12，12 条无相关项中候选均返回、FTS5 均拒答。观察到的正例最低相似度 0.3251、负例最高 0.2334 仅属合成集，不是产品阈值，仍不足以决定启用。D-015 通用数据导出暂缓，继续只提供加密备份/恢复。D-006 预恢复加密副本确认只保留最近一份，新份创建时替换旧份，已实现并通过连续恢复自动回归；D-005 已使用版本化公开价与 SAFE 汇率快照估算、明确标记；SQLCipher 月累计、用量页 80 元提示、跨实例原子预算预留/结算和估算触及 100 元前置拦截已接入；面板分开呈现已结算额与在途预留。云聊天最小审计也已存入 SQLCipher，metadata-only、保留 30 天并在用量页展示。当前月份启用前的 Provider 账单无法回填，真实 usage/cost 对账仍待验证。本机优先边界继续有效；持久化按已确认的 SQLCipher/Keychain 方案逐步接入，未完成备份与验收前不声称具备完整数据保护闭环。路线与门禁见 `docs/TASKS.md` 和 `docs/DECISIONS.md`。
- 2026-11-10 D-006 实现更新：认证 API/macOS UI 已支持手动口令加密导出和当前 Mac 恢复；恢复先验证口令、安装指纹与 SQLCipher 内容，再建立 `Application Support/PersonalAI/pre-restore/` 内仅本机密钥可读的预备份，使用当前 Keychain 密钥重新加密并切换数据库，失败时从 rollback 文件恢复。自动化覆盖正确/错误口令、预备份内容与换库失败回滚；完整回归和断电/强制退出实机验证仍待完成。
- 2026-11-10 会话历史优化：`GET /chat/history` 默认仅载入最新 100 条，用户可按 `(created_at,id)` 稳定游标继续加载更早记录；SQLCipher 添加复合索引，SwiftUI 保留加载前的首条消息滚动锚点。模型输入仍限制最近 20 条；超长单消息和长会话 GUI 压力验收未完成。
- 2026-11-10 V1.1 记忆来源：记忆表单现可选择任一本机会话作为来源，默认载入最新 100 条，可按需加载更早消息；只读本机聊天历史，不发给 Model Gateway。Swift 全量回归 60 项、Beta target 构建通过；来源选择与定位 GUI 实机验收仍待完成。
- 2026-11-10 V2 决策与实机复核：用户接受 EventKit 完整日历与提醒事项权限；Beta 仅用户点击读取未来 30 天摘要，不修改、保存或发送内容。日历面板实机返回 2 项；提醒事项面板成功读取且显示未来 30 天没有未完成项目。当前系统授权路径已确认，但本轮未出现首次授权弹窗，因此拒绝/首次授权仍未验证。用户选定首批固定助理为项目、会议、任务规划。
- 2026-11-10 V2 固定角色：聊天 API/UI 已接入主助理、项目助理、会议助理和任务规划四个封闭键；用户选择保存在本机，专业角色只增加静态指导文本，没有工具、后台执行、自动日历访问或外部写操作。
- 2026-11-10 V1.1 来源跳转：记忆来源查看新增“在对话中查看”，按分页读取来源会话直到定位原消息，再切换会话并滚动到该消息；只读取本机 SQLCipher 历史。
- 2026-11-10 V2/V3 决策：D-018 确认现有任务状态迁移图并禁止自动执行/后台重试；D-019 将首版 Skills 限定为本机固定提示模板，需逐次由用户选择，不含工具和外部写。
- 2026-11-10 V3 Skills 实现：加密数据库 migration 安装风险审查、决策简报、行动项整理三个固定 prompt-only Skills；发送前最多选择三个，提示仅加到当前请求并在发送后清空。Skills API 不回传正文，无工具注册/代码加载/外部写接口。
- 2026-11-10 V2/V3 决策：D-020 接受 EventKit 提醒事项完整系统权限、应用只读且按需读取；D-021 将多 Agent 限定为用户点击、本机 Ollama 顺序调用所选固定角色并汇总，不使用云端、后台执行、记忆或外部写。
- 2026-11-10 V3 多 Agent 实现及实机复核：聊天输入栏可为单轮选择至少两个专业角色（最多三个），后端只接受 Ollama，按所选顺序流式运行并展示各角色观点，再由总助理综合；单角色输出上限 4,000 字，汇总上下文超限则安全失败。角色中间结果不单独持久化，只随最终答复按现有聊天策略写入本机 SQLCipher。GUI 实机已确认双角色观点与综合答复闭环；针对本机 Qwen 默认长思考，协作子请求/汇总请求改为显式 `think:false`，不改变普通聊天；综合 prompt 先提供参考意见、最后重申原问题。真实单样本约十几秒完成且直接回答，但未稳定遵守严格字数限制，继续跟踪模型质量。测试会话留在本机加密历史，详见 `docs/HANDOFF.md`。
- 2026-11-10 D-005 官方计费来源补证：DeepSeek `deepseek-flash` 价目区分缓存/时段，API usage 提供 token 明细但没有请求级 cost；价目会变动。不得将 token 反推结果称为实扣费用；彼时预算门仍未实现；2026-11-10 已新增版本化 CNY 估算与 SQLCipher 月累计/请求前门禁，但首月回填、跨进程并发和实际 Provider E2E 仍未完成。计费来源研究见 `docs/beta/orchestrator-framework.md`。
- 阶段状态（2026-11-09，后续实现见下方更新）：阶段 0 的 Beta 范围已结束，附带明确的未实现/延期清单；原始 §13 全量 POC 仍有 `PARTIAL/OPEN`，不宣称全量验收。阶段 1 当前决策允许的工程底座已接入 CI lint/type/test/secret-scan 门禁。Loopback API 已有 trace、统一错误、依赖注入、最小 health、可注入启动设置和集中校验配置；云凭据写入/删除需通过 Touch ID 或设备密码。产品数据库/API 已接入 SQLCipher store 与 migration，Beta 启动已通过 Keychain 随机密钥和私有管道初始化加密数据库，聊天已支持多会话列表、新建、切换、重命名、指定历史恢复/写入/分别删除；模型上下文限末尾 20 条，历史分页/虚拟化未接入；V2 本机任务 CRUD、D-018 状态迁移图、完成后 30 天清理及默认关闭的本机通知已接入；通知须用户显式授权、启动时重建有效提醒、终态/删除时撤销，真实系统授权与投递仍待 GUI 验收；任务状态迁移规则已按 D-018 确认。用户手动确认记忆已持久化，支持搜索、永久删除和显式确认编辑并保留版本快照；记忆可关联当前会话中已有稳定 ID 的来源消息；版本历史只读查看、来源消息查看已接入；Embedding 与备份恢复验收仍待完成。D-005 预算请求门已实现，跨实例原子预留/结算已有回归，真实 Provider 端到端费用核对仍未完成；PDF 产品导入仍未实现；30 天 metadata-only 审计现覆盖云 Provider 聊天请求，其他安全操作按启用范围补齐；TXT/Markdown 导入由 B5 增量实现，完整文件导入未完成。触发条件见 `docs/poc/phase0-traceability.md` 和 `docs/TASKS.md`。
- 阶段路线：规格书共 7 阶段（0–6）；当前继续推进阶段 2 的对话/Gateway/Usage 主线。阶段 3 实时语音及阶段 4 文件导入均已有部分能力提前进入 Beta，但各自阶段验收仍未完成。各阶段范围见 `docs/TASKS.md` 与规格书 §13。
- 最新开发检查点（2026-11-10）：继续 B5 后，当前仓库 Beta target 由 `./poc/macos-audio/scripts/run_beta_app.sh` 成功构建并启动；本机 Ollama 及 `qwen3.5:0.8b` 可用。Apple 平台资料核对未发现适用于当前 Python helper 且已验证的硬内存上限替代方案；PDF 继续禁用，证据见 `docs/beta/file-import.md`。阶段 4 B5 的隔离 PDF 安全 POC 仍默认关闭；macOS `RLIMIT_AS/DATA/RSS` 有限内存限制尝试失败；worker 启动前通过 `/bin/sh ulimit -v` 试设 768 MiB、1 GiB、1.5 GiB 也均获 `Invalid argument`，缺少恶意样本和真实压力证据。CI 已显式安装 `phase4-pdf-poc` extra，使该 POC 的 7 项测试不再因依赖缺失而跳过；此变更不代表 PDF 可启用。TXT/Markdown Swift 导入客户端 URLProtocol 契约覆盖认证 loopback basename/content 请求、无路径传输及 PDF/超限网络前拒绝；GUI 文件选择、暂存、引用和移除已通过本机合成 TXT 验收：本机模型按请求返回文件内唯一测试标记，移除后 chip 消失。单样本结果不外推至其他模型或 PDF。旧实例未呈现的入口已在仓库当前构建确认可见。B1 有 HTTP 503 正文脱敏、SSE error 解码及 fake cloud/local 错误映射回归。阶段 2 ASGI 断连回归确认上游流关闭、run `CANCELLED` 及 UsageLedger 终态记录；Gateway 保留 DeepSeek/Qwen usage 明确报告的缓存命中输入 token 并显示于 Swift 用量面板，不据此估价。UsageLedger 现拒绝非有限时间戳、无效延迟和非有限/负音频时长。此前阶段 6 CI 等价门禁记录和测试结果均对应其报告中的提交；完整验证见最新 `docs/HANDOFF.md`。一次 APFS-128 临时映像测试曾间歇失败，复跑通过，原因未判定，已登记非阻塞观察。阶段 0 汇总已拆分记忆/Embedding 与 TXT/Markdown 导入状态；PDF 仍禁用。
- 2026-11-10 当前复核更新：`swift test --package-path poc/macos-audio` 43 项通过；后端全量 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`（工作目录 `backend/`）→ 281 passed、1 条既有 Starlette/httpx 弃用警告。之前该日一轮全量在 APFS-128 `backup-copy` 临时映像用例失败；单独复跑该用例 1 passed，随后当前全量亦通过，偶发原因未判定，保留非阻塞观察。Beta build 已在当前开发检查点成功。
- 2026-11-10 UsageLedger 一致性校验更新：UNKNOWN 不得含 token 数，ACTUAL/ESTIMATED 必须至少含一项 token 数；定向 `tests/test_usage.py tests/test_beta_api.py` 46 passed，后端全量 267 passed（1 条既有弃用警告），相关 Ruff 与 mypy 通过。后续 D-005 已接入估算归一和预算门；此校验改动本身不改变单次实际用量/费用语义。
- 2026-11-10 本机 TTS 点播行为更新：开始朗读另一条回复时先停止当前播放；如果系统不能立即停止，就不排入新文本并显示明确状态。Swift 全量 43 项通过，Beta target 构建通过；仅用 fake SpeechEngine 自动验证，真实设备可听性仍待用户手动验收。
- 2026-11-10 Provider 重试契约更新：远端 Adapter 最多两次尝试，仅对 HTTP 429 与建连前失败重试；读/写超时不重试，避免结果未知时重复发送。Consent 撤销会取消退避任务。最新后端全量 281 passed（1 条既有弃用警告）；无真实云请求。

- 2026-11-10 本机 Provider 传输错误映射：修正 `httpx.RequestError` 在 Ollama 请求时错误套用云端失败/计费提示的问题；连接错误提示检查 Ollama，响应超时提示本机生成可能仍在继续。窄回归 8 passed，Ruff/mypy 通过；后端全量 276 passed（1 条既有弃用警告）。
- 2026-11-10 阶段 6 本机 CI 等价门禁复核（代码基线 `0418d25`）：Ruff、mypy、`uv lock --check`、后端 all-extras/all-groups pytest（276 passed，1 条既有 Starlette/httpx 弃用警告）、compileall、tracked-file detect-secrets-hook、Swift 43 项及 Beta target build 均通过。未触发远端 GitHub Actions。
- 2026-11-10 Gateway Consent lease 清理：`stream_with_usage()` 现即使上游 async iterator 的 `aclose()` 抛错，也在嵌套 `finally` 中注销在途授权操作；避免保留已结束 task 引用。定向 2 passed，Ruff/mypy 通过；后端全量 281 passed（1 条既有弃用警告）。
- 2026-11-10 Gateway 流清理取消语义：流迭代或取消异常发生时，关闭上游 iterator 的异常不再覆盖原始异常；正常结束时关闭异常仍上抛。lease 仍在外层 finally 中释放。定向 2 passed，后端全量 281 passed（1 条既有弃用警告）。
- 2026-11-10 `ModelGateway.stream()` 同步采用与 `stream_with_usage()` 相同的关闭语义：取消或迭代错误优先保留，正常结束时关闭错误仍传播；Consent lease 总会释放。定向 3 passed，后端全量 281 passed（1 条既有弃用警告）。
- 2026-11-10 RunRegistry 将 `created_at` 读取移入注册锁，确保并发请求的时间戳与入表/淘汰顺序一致。定向 3 passed，Ruff/mypy 通过；后端全量 281 passed（1 条既有弃用警告）。
- 2026-11-10 RunRegistry 状态时间单调性：状态转换时 `updated_at=max(previous_updated_at, wall_clock)`；UsageLedger 完成时间复用 RunRegistry 终态时间，防止系统时钟回拨造成 `completed_at < started_at` 并破坏记录写入。定向 5 passed，后端全量 281 passed（1 条既有弃用警告）。
- 2026-11-10 B5 Swift 客户端聊天请求契约：URLProtocol 回归捕获 `/chat/stream` 请求并验证 Bearer 认证与 `import_ids` 序列化。Swift 全量 44 项通过，Beta target build 通过；GUI 对话实际引用资料仍待手动验收。
- 2026-11-10 B5 附件上下文预检：API 在 Orchestrator 序列化附件 JSON 前，以消息和附件字符数下限拒绝明显超限资料，仍保留序列化后的精确上限门。定向 2 passed，Ruff/mypy 通过，后端全量 282 passed（1 条既有弃用警告）。
- 2026-11-10 阶段 6 当前本机 CI 等价门禁通过：`uv lock --check`、Ruff、mypy、tracked-file detect-secrets、compileall、后端 282 项、Swift 44 项和 Beta target build 均通过。Swift 首次复核发现导入 URLProtocol 测试共享捕获器的并行竞态；已隔离拒绝网络探针并复跑通过。远端 GitHub Actions 未运行。
- 2026-11-10 B1 Ollama 取消延迟复测：默认 thinking 下请求耗时波动大，无法把高延迟归因于取消；显式 `think:false` 下短句基线 1.80 秒，取消 2.01 秒长流后的短句 1.31 秒，未复现排队延迟。未改模型策略；详见 `docs/beta/macOS-beta-chat.md`。
- 2026-11-10 阶段 0/6 模型许可证据复核：官方 Qwen 源模型页标注 Apache-2.0，官方 sherpa 文档指向第三方 ONNX 导出仓库；但转换仓库当前未见 LICENSE、镜像模型卡无单独许可字段，训练数据和随包 WAV 许可仍未确认。模型仍仅作本机 POC，不随 Beta 分发；详见 `docs/poc/phase0-model-license-review.md`。
- 2026-11-08 模型设置更新：SwiftUI 聊天页增加本地/云端选择，默认本机 Ollama；云端默认千问按量计费应用 API（`qwen3.8-flash`、`sk-ws-`、Keychain account `qwen-app`），另有 DeepSeek/OpenRouter 路由。选择云 Provider 即持续授权后续聊天发送到该服务商，不再逐条弹窗；设置文案披露此行为，Key 存 login Keychain，L3 凭据在后端出站前拒绝。千问 Token Plan 个人版 `sk-sp-` 官方条款明确排除自建应用后端，未接入直连 Provider；本会话一次千问合成请求返回通用错误且未重试，用户随后反馈已可正常聊天；未在本地记录该次成功响应/usage。详见 `docs/beta/macOS-beta-chat.md` 和 `docs/beta/qwen-token-plan-integration.md`。
- 当前目标：单用户 macOS 本机优先测试版；POC 证据仍标为 POC，阶段 0 完整 V1/正式发布验收未完成。SwiftUI Beta、受认证的本机 `/chat/stream`、Ollama 增量对话和 Provider/模型切换已实现；GUI 发消息/显示回复、模型切换与语音冒烟已由用户实机复核，详情见 `docs/beta/macOS-beta-chat.md`、`docs/beta/macOS-beta-voice.md`。生成请求使用 request ID 隔离回调；对话不持久化。B2 现为显式点击采集、本机实时 ASR、partial/final 草稿和手动 AVSpeechSynthesizer 朗读；用户实机验证 final、取消、点击打断和录音中 Cmd-Q 退出清理。延期能力保持清晰扩展边界，不宣称已通过验证。
- 对话主干已增加独立 `MainAssistantOrchestrator` / `ContextBuilder`、有界进程内 `RunRegistry`、精确型号能力门和随包静态 capability manifest、认证 Usage API 和有界进程内 UsageLedger，以及用户主动 TXT/Markdown 文件导入。认证 `/model-capabilities` 返回型号报告和证据；未登记型号及缺省能力为 UNKNOWN，证据有限的工具状态为 LIMITED。macOS Beta 已提供认证只读用量面板；Gateway 可透传 Ollama 与云 Provider 流最终帧中的实际 token 数，未收到时明确为 UNKNOWN。OpenRouter 若报告 `usage.cost` 则原样记为实际 USD；其他供应商缺失费用仍为 UNKNOWN。另有本地版本化公开价预算估算、SQLCipher 月聚合和 80/100 元门禁；精确云型号真实 usage/cost 尚未实测。导入内容只留本机进程内存，可移除，只用于本机模型并按不可信资料加入上下文；PDF 保持禁用直至解析资源限制验证完成。当前只路由 `main_assistant`，run 状态可经认证 API 查询，macOS UI 显示短 ID 和状态，记录不含对话正文且不跨进程保存；后续主线优先推进，不影响闭环的小问题先登记回修，具体规则见根目录 `AGENTS.md` 与 `docs/TASKS.md`。
- B0 已完成（2026-11-09）：主界面采用 SwiftUI 单实例 `Window`，关闭窗口即退出应用；启动失败分类提示/GUI 重试、真实本机服务启动和关窗后 app/backend 无残留均已复核。supervisor 的 start/stop/isRunning 由生命周期锁串行化，启动期间停止的回归通过。
- B1 本机依赖（2026-11-09）：PAC 本地聊天通过 Ollama 提供模型服务，Ollama 需在本机运行且选择的模型已安装；用户及本轮 GUI 均确认短句可正常返回。Ollama 0.40.15 本机直连接受控取消长流后，下一短请求延迟 46.72 秒；与 Ollama 上游断连占用 runner 槽报告相符，因果尚未完全确认。PAC 停止提示已说明 Ollama 可能仍在结束旧生成；新设置帮助会明确 PAC 后端与 Ollama 分开运行。详见 `docs/beta/macOS-beta-chat.md`。
- 实现形态：macOS SwiftUI 客户端 + 本机 Python/FastAPI 服务；仓库内各工作包的当前状态和证据见 [阶段 0 追踪矩阵](poc/phase0-traceability.md)。
- 本机语音：中文 Streaming ASR、麦克风捕获 CLI、TTS 打断已有 POC 和部分实测；用户提供的 Qwen3-ASR 0.6B INT8 ONNX 已完成随包中/英离线评估。官方中英双语 Streaming Zipformer 的 10 条合成音频均产生 final；用户三次实机运行 CLI 均观察到 partial/final；5 条中英/混说 manifest 合成 WAV 的本机 ASR-final→AVSpeechSynthesizer 链路共 7/7 完成。Beta 已接入 200 ms loopback WebSocket 实时本机 ASR、临时 partial/final 草稿和文字生成中的点击打断；用户验证停止后 final 入草稿、取消清空 partial、点击打断生成及录音中 Cmd-Q 清理。最新 GUI 故障的根因已通过本机 ASR 离线复现：`LocalVoiceTranscriber.end_stream()` 与 `abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，清理再次抛 `AttributeError` 并导致 WebSocket finally 跳过锁释放。现调用底层 recognizer reset，且 finally 保证释放锁。真实 Uvicorn + 本机 ASR 模型和 Apple URLSessionWebSocketTask + sherpa-onnx + PCM WAV 连续 3 轮均完成 partial/final/ended；Python 全量 183 项通过；用户现已确认 GUI 故障修复。D-013 启动面板单位错误已定位并修复：秒值遗漏乘以 1,000，显示仍标为毫秒。用户提供 20 个启动值，范围 500–700 ms、nearest-rank P95=700 ms，低于 5 秒门槛且启动样本计划已完成；partial 216 次、22 个窗口 n=7/9/10，各窗口 P95 最高 41.5 ms；停止→final 21 次 pooled P95=97.9 ms、最大 99.9 ms，均低于各自门槛。云 Realtime、AEC/自动声学插话和锁屏/休眠仍未实现，ADR-021 已 Accepted。用户指定当前真人语音目标为功能冒烟，模型识别质量后续再优化；本机双语 Zipformer 与 Qwen ONNX 权重 SHA-256 已分别匹配公开固定模型 revision，但训练数据、Qwen 转换工件和随包音频许可仍待核；详见 `docs/poc/phase0-local-asr.md` 与 `docs/beta/macOS-beta-voice.md`。
- 阶段 1 最终复核（2026-11-09，`5f6fe24`）：Python 全量 192 passed（1 条既有 Starlette/httpx 弃用警告），Swift 33 passed；Beta build、Ruff、mypy、`compileall`、`uv lock --check`、tracked-file secret scan 通过。该提交尚未运行远端 CI。
- SwiftUI 安全客户端：显式系统认证测试按钮已在真实 demo 窗口两次成功验证、一次用户取消验证，均确认未访问钥匙串；UI 按 LocalAuthentication 错误码区分用户取消和系统中断；GUI 后端启停另经两轮复测且无重复子进程。
- Gateway、安全、记忆、Embedding、SQLCipher 与后端生命周期有 POC；2026-11-10 新增产品存储 schema/migration 基础，尚未接入运行时 API；MemoryStore 显式注入固定 Embedding 权重的严格离线合成检索最新为 4/4 top-1。它们不等同于产品功能验收。详情按需查阅 [`docs/poc/`](poc/)。
- 0G 许可审查现覆盖当前 macOS Python arm64 wheel：Pillow 自带 SBOM 包含 GPL/LGPL 组件，SQLCipher/PortAudio/sherpa 内嵌 ONNX Runtime 有独立许可或 notices。实际产品安装依赖未定，模型工件及完整发行通知闭包仍开放，详见 `docs/poc/phase0-model-license-review.md`。
- 根目录现有 `README.md`、`AGENTS.md` 和 `.github/workflows/ci.yml`；2026-11-09 本轮 Python 全量 183 项通过（1 条既有 Starlette/httpx 弃用警告）；Swift 33 项在本轮收尾复核通过，`compileall` 与 `uv lock --check` 本轮通过。GitHub Actions 历史 `Phase 0 checks` run `42489738004` 在 `main` commit `51b9ab9` 成功（当时 Python 162、Swift 31）；当前分支提交尚未运行远端 PR CI；本地全量 Python/Swift 回归已在收尾复核通过。Python CycloneDX SBOM 已按最新锁文件重生成并验证 63/63 个非根依赖匹配；许可线索清单已包含 `websockets==17.4`，最终发行物审计仍未完成。D-001–D-015 的当前状态见 `DECISIONS.md`：用户现已扩展目标到 V1.1/V2/V3，并决定本地持久化聊天/任务/确认记忆及 SQLCipher + Keychain 密钥方案；手动加密备份也已确定方向。聊天和任务数据已接入 Beta API/UI；确认记忆、备份恢复、Embedding/导出细节待定。ADR-019 方案已选、实现验收进行中，ADR-020 已 Accepted 为项目自有轻量 Gateway，ADR-021 已 Accepted 为本机点击触发实时 ASR/点击打断、不做 AEC/自动声学插话/云 Realtime，ADR-022 已 Accepted。阶段 0 的 Beta 范围收尾评审于 2026-11-09 通过；原始 §13 全量 POC 仍保留 PARTIAL/OPEN。D-013 Beta GUI 采样三项均低于门槛；ASR+本机 Ollama 并发 probe 已扩至 20 轮（新增 13 轮），但不是完整 Agent 或产品负载验收；远端 CI、macOS 14 实机、硬件音频与许可/发布等证据仍按追踪矩阵未关闭项处理。
- 每次工作的 Git 基线以 `git log -1` 为准；工作开始前先检查 `git status`，保护已有改动。

## 架构和安全边界

- UI 通过本机 Loopback API 与后端通信；服务由 Swift supervisor 固定启动，不经任意 shell 命令。
- Model Gateway 使用 Adapter 和精确 Provider/Model capability registry；未知能力默认不支持。
- 本地优先。远端模型调用必须在发送前通过 Consent Manager 与 Policy Engine；凭据来自 Keychain。Beta 中用户选择云端模型是持续授权，后端仍为每一条请求生成精确 Provider/model/region/Data Level 的短时 grant；用户可切回本地停止云出站。L3 拦截和无自动 fallback 保留。阶段 0 的 DeepSeek/OpenRouter POC 脚本仍采用每次请求单独交互确认；两家各有用户确认后的合成文本真实请求成功记录，同一 Gateway 顺序跨 Provider 路由已真实通过一次。远端 HTTP 401 会提示凭据认证失败，Keychain 缺失与认证拒绝分开提示，错误响应正文不保留。无 Consent 的真实 HTTPX 检查在两家均于 Adapter 前拒绝、credential reads=0，PID 级 `lsof` 观察无活动网络 socket；全系统包捕获的 TCP/443 流量因未按进程过滤不作归因。
- 用户已指定交互式云模型 POC 默认优先千问 Token Plan。新增固定北京 `qwen3.8-flash` 文本 adapter 与 mock/deny-check 覆盖；用户已逐次确认并完成一次真实合成文本请求，响应精确匹配，usage 为 73/50/123 tokens。服务未返回下游 Provider、实际区域或费用。用户在聊天中暴露的临时 key 未被读取或保存。官方资料确认 Token Plan 支持文本 OpenAI-compatible HTTP 和 `qwen-audio-3.0-realtime-plus` Realtime WebSocket；非实时 ASR/TTS 使用独立 HTTP 接口。但 Token Plan 个人版仅供编程/智能体工具中交互使用，排除自定义应用后端，故不得把个人版 Key 接入本项目自建 SwiftUI/FastAPI Beta。未来如需应用内云语音，须另用适用于自定义应用的 API 凭据。当前 Beta 尚未接入 Qwen 实时语音，也未对新文本域名重新实测；适用范围和协议详见 `docs/beta/qwen-token-plan-integration.md`。
- Agent Registry 当前为模拟 POC；权限不得超出父权限，不实现 Agent 团队或任意执行器。
- 记忆 POC 使用 disposable 内存 SQLite/FTS5；Embedding 显式 opt-in。不得把 POC schema 当作产品 schema。
- ASR、TTS、LLM 分开配置；原始音频默认不持久化；本地 ASR 失败不得静默切到云端。
- 规格限制的 V1 范围不包括后台任务、外部写操作、跨设备或多用户能力。

## 记录规则

- 稳定事实和架构边界写在本文件；产品或架构取舍写在 [DECISIONS.md](DECISIONS.md)；当前状态、负责人和验收条件写在 [TASKS.md](TASKS.md)；每次交接摘要写在 [HANDOFF.md](HANDOFF.md)。
- POC 的详细证据以 `docs/poc/phase0-traceability.md` 及其链接报告为准；测试版可用范围和发布门禁以 `docs/TASKS.md`、`docs/DECISIONS.md` 为准。避免在多个文档复制长篇测试结果。
- 每项工作记录状态和可复核证据。没有实际验证的能力不得标记为已验证；产品待决事项不得由实现者自行假定。
- 每次变更后更新相关进度文档并提交 Git；交接或中断前更新 `HANDOFF.md`。

## 项目文档索引

| 文档 | 用途 |
|---|---|
| [`../AGENTS.md`](../AGENTS.md) | 每轮开发必须遵循的仓库工作流、范围和安全边界 |
| [`../README.md`](../README.md) | 仓库入口、结构和本机验证命令 |
| [`TASKS.md`](TASKS.md) | 阶段工作包、优先级、阻塞、下一步和完成条件 |
| [`DECISIONS.md`](DECISIONS.md) | 已确认的项目决策、待决产品事项和 ADR 状态入口 |
| [`HANDOFF.md`](HANDOFF.md) | 最新工作摘要和下一位执行者的起点 |
| [`poc/phase0-traceability.md`](poc/phase0-traceability.md) | 阶段 0 要求、证据、缺口及门禁的权威追踪矩阵 |
