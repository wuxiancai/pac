# 阶段任务清单

最后核对：2026-11-10（Asia/Shanghai）

## 状态和流程

- `DONE`：工作包的明确完成条件已满足，证据可复核。
- `IN PROGRESS`：正在执行，尚有明确完成条件未满足。
- `OPEN`：可继续推进，尚未开始或证据不足。
- `BLOCKED`：依赖产品决定、用户操作、凭据或外部条件；记录解除阻塞所需输入。
- `DEFERRED`：按用户或基线范围暂缓，不作为当前缺陷。

执行顺序：开始前读取根目录 `AGENTS.md`（如存在）、`PROJECT_CONTEXT.md`、`TASKS.md`、`DECISIONS.md`、`HANDOFF.md`；检查 Git 状态；按下面的顺序选取未阻塞任务；实现后执行适用验证、更新 POC 报告与追踪矩阵、更新本清单和交接文档，最后提交 Git。用户已按 C-007 授权先建设单用户 macOS 测试版。阶段 0 仍保留为完整 V1/正式发布证据清单，但不再整体阻塞测试版；延期验证须在对应能力启用或正式分发前补齐。

### 主干优先与问题回修

整体框架和核心可用功能优先。对不影响主要闭环、安全、隐私或授权的小问题，记录复现证据、影响、是否已确认代码根因及回修触发条件，随后继续主线；偶发 Provider、模型、网络或设备问题不得未经证据直接归因为代码缺陷。主干成形后集中回看这些记录。若问题会阻断核心功能或触碰安全边界，则先处理。该规则见根目录 `AGENTS.md`，后续开发持续遵循。

阶段 0 的原始证据以 [追踪矩阵](poc/phase0-traceability.md) 为准；本清单另行定义当前测试版交付顺序。

### 扩展目标（2026-11-10 用户要求）

2026-11-10 用户指定 V3 首个经审批外部写入为“仅创建日历事件”；单个非重复事件的精确授权、预览、审计与范围边界见 D-022 和 B10。

在完成当前单用户 Beta/V1 可用闭环后，继续规格书 §13 的 V1.1、V2 和 V3 开发，不再把 V1.1/V2/V3 作为“以后再说”的范围。路线依赖仍按阶段门禁推进：V1.1 记忆中心/导出恢复优化；V2 完整任务状态机、只读日历/待办、受控通知；V3 固定专业 Agent、多 Agent 协作、经审批的外部写操作与 Skills。用户已决定本地持久化聊天、任务和已确认记忆；聊天/已确认记忆手动删除，完成任务 30 天后清理。数据库加密方向已选 SQLCipher + Keychain 随机密钥、登录后自动打开；Keychain 生命周期与产品验证仍待完成；手动加密备份已选定为用户位置 + 每份独立口令 + 恢复前认证/预备份，用户已选择 scrypt（N=32768,r=8,p=1）、不保存备份口令、仅当前 Mac 恢复；RTO/副本保留、损坏/中断恢复仍待验证。Embedding 先按 D-014 进行离线候选评测，产品启用另行决定；D-015 通用导出暂缓，继续只提供加密备份/恢复。D-005 估价规则、D-006 最近一份预备份规则已确认，按 DECISIONS 跟踪实现和验证。聊天、任务和用户确认记忆当前已通过 B3 写入本机 SQLCipher；本机任务提醒已实现，系统通知授权及实际投递仍待 GUI 验收。

项目开发规格共定义 7 个阶段：阶段 0 POC/工程基线、阶段 1 V1 工程底座、阶段 2 V1 对话与 Model Gateway、阶段 3 实时语音、阶段 4 长期记忆与资料导入、阶段 5 安全加固/备份/运维、阶段 6 V1 系统验收/发布候选。阶段 0 Beta 范围和阶段 1 当前决策允许范围已完成；当前按单用户 Beta 队列继续阶段 2，部分阶段 3/4 能力曾提前实现，不代表相应阶段整体完成。

**阶段 0 Beta 范围已结束（2026-11-09），附未实现/延期清单。** 用户确认剩余小功能按触发条件延期；它们不得标为完成或通过。原始 §13 全量 POC 的 `PARTIAL/OPEN` 外部证据在相关功能启用或正式分发前继续追踪。详细清单见[阶段 0 追踪矩阵](poc/phase0-traceability.md)。阶段 1 当前决策允许的无持久化工程底座已完成（2026-11-09，提交 `5f6fe24`）；其后按重开决议推进 B3，现有 SQLCipher store、Keychain 启动密钥注入、聊天历史与 V2 本机任务 API/UI 已接入。确认记忆、备份恢复、Keychain 实机与加密产品验收仍未完成。

## 单用户 macOS 测试版交付队列

| 顺序 | 工作包 | 状态 | 完成条件 / 说明 |
|---:|---|---|---|
| B0 | 应用可运行骨架 | DONE | SwiftUI `.app` 可由仓库脚本构建启动；本机服务启动失败时按错误类型显示中文提示并可重试；supervisor 对启动/停止/状态读取串行化并覆盖启动中停止。GUI 故意返回无效握手后，替换为本机 health fixture 并点击重试成功；真实本机服务启动连接成功；单窗口关闭后 app 与 backend 均退出且无残留。 |
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或千问应用 API、DeepSeek、OpenRouter 固定路由；本地模型 ID 可配置。选择云端即持续授权后续消息发往该服务商，设置有告知且无逐条弹窗；Keychain、固定目标、L3 拦截、错误脱敏和无自动 fallback 保留。每次发送快照当前 Provider/模型；切换时取消旧客户端流并屏蔽迟到回调，状态栏显示当前及本轮实际 Provider/模型。用户已实机确认模型间可自由切换、打开 Ollama 后 PAC 本地模型可聊天，本机短句也收到精确回复。Ollama 必须运行且模型已安装。设置页云端披露与只读 Key 状态已实机复核（OpenRouter 已保存，未读 Key），Ollama 配置帮助说明已在 GUI 实机复核，明确区分 PAC 服务与 Ollama 进程并提示模型安装要求。SSE 注释保活/上游取消自动回归通过（窄回归 22 项）。Ollama 0.40.15 本机直连取消长流后，紧接短请求耗时 46.72 秒（同机默认短请求基线约 2.42 秒）；与 Ollama issue #17131 描述的断流后 runner 槽占用现象相符，根因仍属推断；停止提示已区分客户端停止与上游状态。客户端 HTTP 503 正文脱敏及 SSE error 事件解码通过；后端 fake adapter 覆盖云端 HTTP 401/402/403/429/503 错误提示脱敏、FAILED run 及无 fallback，也覆盖本机异常脱敏、FAILED run 和 unknown usage/cost。本机 HTTPX 连接失败提示检查 Ollama；响应超时提示其可能仍在本机生成，不显示云端计费措辞。远端自动尝试最多 2 次，仅对明确 429 和连接建立前错误；读/写超时不重试，避免服务商可能已受理的请求被重复发送。429 遵从最多 2 秒的数值 Retry-After；Consent 撤销会取消退避中的任务。当前后端全量 282 passed、1 条既有 Starlette/httpx 弃用警告；APFS-128 备份耗尽用例曾间歇失败，隔离复跑和随后全量均通过，原因未判定。Swift 全量 44 项与 Beta build 通过。已在干净新会话实机确认不存在模型时的本机错误消息、失败 run 状态且无云 fallback；Ollama 本轮恢复路径已于 2026-11-10 GUI 实测：本机服务连接状态恢复后，以 `ollama / qwen3.5:0.8b` 完成一次合成短请求；云 API 错误 UI 验收仍待完成。APFS-128 临时映像偶发失败及复跑证据列于非阻塞问题清单。用户反馈千问现可正常聊天；D-005 已按版本化公开价估算并将月累计保存到 SQLCipher，用量页显示 80 元提示，估算累计加请求预估达到 100 元时阻止后续云请求，跨实例共享数据库原子预留已覆盖并发请求；当前月历史账单无法回填，真实 Provider 计费闭环仍待验证；D-010 Provider 范围为千问应用 API、DeepSeek（中国）、OpenRouter（Global）；Token Plan `sk-sp-` 个人版不直连自建应用。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | IN PROGRESS | 已扩展为受认证 loopback WebSocket 本机实时 ASR：200 ms PCM 帧、有界队列、临时 partial、停止后 final 入草稿；一次性语音入口也按请求流分块限长，无 Content-Length 时仍执行 30 秒字节上限；批量 ASR 原子获取单会话锁并在等待超时后拒绝并发请求；Uvicorn WebSocket 消息上限为最大协议帧 12,804 字节；用户曾验证 final、取消、文字生成时打断、录音中 Cmd-Q 清理。GUI 曾在停止时断开 socket、随后的第二次录音报 ASR 忙（partial n=2、停止→final n=0）。根因已查明：`LocalVoiceTranscriber.end_stream()`/`abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，清理再次异常使 WebSocket finally 跳过锁释放。现改为重置底层 recognizer，并在清理异常时仍释放会话锁。真实 Uvicorn + 项目本机 ASR 模型连续 3 轮 PCM 流式识别均收到 partial/final/ended；Python 全量 183 项通过（1 条既有 Starlette/httpx 弃用警告）；Apple URLSessionWebSocketTask + 真实 Uvicorn + 本机 sherpa-onnx 模型 + 固定 PCM WAV 连续 3 轮均收到 partial/final/ended。用户已确认 GUI 实时语音故障修复。启动面板单位错误已定位并修复：秒值遗漏乘以 1,000。用户提供的 20 个启动值换算为 500–700 ms，nearest-rank P95=700 ms，低于 5 秒门槛，启动采样计划已完成；partial 更新 216 次、22 个窗口 P95 摘要最高 41.5 ms；停止→final 21 次 pooled P95 97.9 ms、最大 99.9 ms。三项性能均已满足门槛；本机 TTS 现确保第二次点播先停止当前语音，停止失败则不排队，Swift 自动回归覆盖该逻辑；具体结果见 `docs/beta/macOS-beta-voice.md`。D-013 启动 20 个样本计划已完成。模型报告已通过本机 SHA-256 将双语 Zipformer 与 Qwen ONNX 权重精确对应到公开模型 revision；模型训练数据、Qwen 转换代码/工件和随包音频许可仍开放。详见 `beta/macOS-beta-voice.md` 与 `poc/phase0-model-license-review.md`。 |
| B3 | 会话保存与恢复 | IN PROGRESS | 用户已决定本地持久化聊天、任务与已确认记忆：聊天/记忆手动删除，完成任务 30 天清理；SQLCipher + Keychain 随机密钥、手动加密备份方向已选。Beta 已接入本机 SQLCipher、Keychain 启动密钥管道、多会话读写/新建/切换/重命名/分别删除、最多 100 条初始会话历史与用户触发 keyset 分页、V2 任务 CRUD/提醒与清理、手工确认记忆 CRUD/FTS/显式修正版本、版本历史只读查看、全部会话历史消息来源选择及来源查看/跳转。手动口令备份容器、SQLCipher 在线导出、认证 API/macOS 导出与恢复 UI、当前 Mac 换钥恢复、恢复前私有 SQLCipher 预备份、进程内回滚及启动中断回滚已实现；备份恢复、硬退出及同/跨进程独占测试最新窄回归 15 项通过，分页 repository/API 窄回归 2 项通过；D-006 预备份最近一份原子轮替已实现；D-005 版本化估算器、SQLCipher 月聚合、80 元提示、跨实例原子预留/结算与 100 元请求前门禁已接入；用量 API/UI 分开显示已结算估算与在途预留。新增 SQLCipher 恢复前/后切换硬退出注入，重启恢复旧库并清理所有 staging；基于 POSIX 生命周期锁保证正常 store 可并行打开、恢复切换独占；同进程或另一进程仍持锁时均安全拒绝恢复，并由独立子进程回归确认。手动备份导出 GUI 已在 `.poc-data` 临时路径成功保存并清理（274,726 bytes）；恢复确认 UI 已实机显示；本次恢复状态文案已区分认证恢复与导出并在操作中互斥禁用，但上轮恢复卡在认证阶段的原因仍未知。设备认证及终态/错误反馈未完成，错误口令、恢复中断和用户自选外部位置仍待验收。新增 UI 稳定消息 UUID（不进入 API 编码）并保留流式替换身份；聊天 SwiftUI `ForEach` 直接消费消息集合，移除每次更新都创建完整枚举行包装数组。Swift 全量 84 项、Beta target build 和 `poc/macos-audio/scripts/build_beta_app.sh` 打包均通过；超长单条消息、实机长会话渲染压力仍待验收。另待完整备份中断/强制退出实机验收、真实 Keychain/通知验收。2026-11-10 已在 GUI 实测已保存来源详情跳转至对应会话并显示来源消息；按测试说明删除临时合成记忆，记忆中心确认已永久删除。当前与跨会话的合成消息来源选择、空表单关闭及放弃未保存草稿确认已实机验证，含仅选择来源和编辑态；未创建持久记忆。新增 120 条消息跨 100 条分页边界的 SQLCipher 长历史回归通过；这不替代 UI 渲染压力验收。任务状态迁移图已按 D-018 确认，API 返回可选动作且 UI 显示完整允许迁移；2026-11-10 GUI 使用无提醒临时任务实测 PENDING→READY→RUNNING→COMPLETED，随后删除测试任务，未请求通知权限。Embedding 关闭。详见 `beta/persistent-storage.md` 与 `docs/HANDOFF.md`。 |
| B4 | 千问 Token Plan 扩展接入 | DEFERRED | 个人版条款仅允许经官方支持的编程/智能体工具扩展交互使用，排除本项目自建应用后端。只有取得允许自建应用的官方授权/套餐，或实现受支持工具扩展集成后，才能纳入应用选项。协议、地址和状态见 `beta/qwen-token-plan-integration.md`。 |
| B5 | V1 文件导入及正式发布扩展 | IN PROGRESS | 已实现用户主动选择 TXT/Markdown、本机临时导入、显式移除及仅本机模型上下文；10 MB/UTF-8/普通文件名验证，有界进程内内存，无路径持久化。Swift 客户端已自动验证 basename/内容/认证 loopback 请求、无路径传输和 PDF/超限网络前拒绝；Beta UI 对文件导入增加单飞状态，导入期间禁用重复选择、发送和语音入口，避免并发上传绕过客户端 4 文件上限；Swift 全量 40 项通过且 Beta target build 通过；后端导入接收也采用 API 单飞门禁，另一上传在首请求分块接收期间立即返回 409，且请求体未被消费，避免并发请求在注册表容量检查前各自暂存 10 MiB；GUI 文件选择、导入暂存、聊天引用和移除均已实机验证：85-byte 合成 TXT 导入后，向本机 qwen3.5:0.8b 询问文件内唯一 marker，回复包含精确匹配值，移除后 chip 消失；只证明单一合成 TXT/模型路径。自动化还验证合成提示注入文本与 JSON 样式文件名仍作为单条 user 消息中的 JSON 不可信资料，system/user 角色固定且无工具注册；此测试只验证上下文边界，不证明模型语义层面对任意注入免疫。较早旧实例控件树未呈现入口，当前仓库构建入口可见。新增可选隔离 pypdf 安全 POC，7 项自动测试覆盖输入/页数/文本/解析工作边界、合成 FlateDecode 解压上限、提取文本字符上限和超时转换；CI 显式安装 PDF POC extra，确保相关自动化用例不被依赖缺失而跳过。本机尝试以 `RLIMIT_AS/DATA/RSS` 设置 512 MiB 硬内存上限失败；`ulimit -v` 768 MiB、1 GiB、1.5 GiB 在 macOS 拒绝；另在隔离 C 子进程调用 `task_set_phys_footprint_limit(256 MiB)` 返回 SDK 状态 `KERN_NO_ACCESS`，均未建立硬内存边界。PDF 仍缺可验证的解析资源隔离、代表性恶意语料、真实 CPU/墙钟超时压力证据与 PDF 专项启用验收，故继续禁用；具体探针结果见 `docs/beta/file-import.md`。D-014 已允许持久化用户确认的记忆，离线 Embedding 候选评测进行中且产品仍关闭；D-015 通用数据导出暂缓；云语音、备份/恢复、自动恢复、完整许可通知和正式签名分发仍延后至对应功能开发/发布前。 |
| B6 | V2 本机日历/提醒事项只读 | IN PROGRESS | 用户接受 EventKit 完整日历与提醒事项权限；Beta UI 分别只在点击后请求权限。日历读未来 30 天事件，提醒事项读未来 30 天到期的未完成条目及无到期日条目。两者均无创建/修改/删除、无持久化或 Provider 发送。2026-11-10 实机点击读取成功：日历返回未来 30 天 2 项；提醒事项返回“没有未完成项目”。当前系统授权下读取路径确认；本轮未出现新的系统授权弹窗，首次授权/拒绝路径仍需验收。 |
| B7 | V2 固定专业助理 | DONE（实现与自动化） | 固定角色已经进入聊天 UI/API：项目助理、会议助理、任务规划；本机保存当前选择，每轮发送白名单角色键，后端插入静态角色指导。无任意工具、后台执行、Agent 团队或外部写。真实桌面操作验收仍按 V2 总体验收跟踪。 |
| B8 | V3 首版本机 Skills | DONE（实现与自动化） | 加密数据库 migration 安装三个只含固定提示、权限清单为空的本机 Skills：风险审查、决策简报、行动项整理。用户在发送前逐次显式选择，最多三个；选择只附加到本轮 system context，发送后清空。无用户代码、工具注册、外部写或跨设备同步。 |
| B9 | V3 本机顺序多 Agent 协作 | IN PROGRESS（实机闭环已走通） | D-021 已实现：用户每轮显式选择至少两个固定角色；服务端限 Ollama，按序运行并流式显示观点，最多每角色 4,000 字后交总助理汇总。上下文/输出越界失败关闭；断连会关闭当前上游并阻止后续角色调用。无云、后台、记忆、工具或外部写。多 Agent 专用请求关闭 Ollama thinking，普通聊天不变；综合请求约束相关性/数量/长度/格式。2026-11-10 GUI 新样本发现协作角色以 Set 排序导致实际顺序不跟随点选；现改为保留点击顺序。项目助理→会议助理复测完成并显示两个角色观点及综合；综合三项切题且简短，但角色个别条目仍超 15 字，质量/格式不稳定。B9 继续 IN PROGRESS；单题不作质量保证。详见 `beta/orchestrator-framework.md` 和最新 `HANDOFF.md`。 |

### B10：V3 逐次审批日历事件创建（IN PROGRESS）

- 范围按 D-022：用户手动填写单个事件，预览后逐次确认，写入 macOS 当前默认日历；EventKit write-only；无 Agent 自动调用、提醒事项写入、重复、邀请、修改/删除或后台执行。
- 先行段已新增认证 `/security-audit/calendar-event`，只接受受限决策/原因码，并在 SQLCipher 中记录 metadata-only 的 `ATTEMPTED/SUCCEEDED/FAILED`（敏感级别 L2），不接收标题/时间/备注。自动回归覆盖无认证拒绝、`audit_finalization_failed` 终态原因码和事件详情不入审计。
- 审计 API 窄回归通过；Ruff/mypy 通过，后端全量 347 passed（1 条既有弃用警告）。EventKit 创建服务/协调器现有 8 项自动回归，覆盖权限准备不写入、校验先于审计、审批审计失败关闭、写入失败记 FAILED、成功结果审计失败不重试，且同一表单服务已成功写入后拒绝再次创建。Swift 审计客户端另有 2 项窄回归覆盖 metadata-only 与 503 失败关闭。Beta 独立创建入口现有手填字段、默认日历同步披露、权限检查、确切预览和逐次二次确认；协调器统一执行 ATTEMPTED→EventKit→SUCCEEDED/FAILED。预览使用与保存一致的规范化值，时间显示精度对齐分钟。Swift 全量 83 passed，Beta target 与 `.app` 打包成功。2026-11-10 GUI 已显示创建入口/表单/必填校验；随后经用户明确授权的实机验收创建一条合成事件，UI 显示“事件已创建，成功状态已写入加密审计”：标题 `PAC 合成日历审批验收（可手动删除）`，时间 2026-11-10 20:56–21:56（Asia/Shanghai），地点 `PAC 本机 Beta 验收`，备注标明合成事件并请测试后手动删除。确认了本次系统授权下从精确预览确认到成功写入及成功审计的 GUI 闭环；未另行读取日历。首次授权/拒绝分支及审计/写入故障 GUI 路径仍待验收。该事件若需移除请在日历应用中手动删除。详见 `docs/HANDOFF.md`。

### 阶段 6 本机门禁复核（2026-11-10，仍开放）

- 在代码基线 `a21ec3d` 复核：后端 all-extras/all-groups pytest 347 passed（1 条既有弃用警告），Swift 83 passed；Ruff、CI mypy、`uv lock --check`、Python compileall、tracked-file detect-secrets 和 Beta target build 全部通过。
- 2026-11-10 完成一条合成 EventKit 事件创建及成功审计 GUI 验收。远端 GitHub Actions、真实 Provider、麦克风、备份恢复和其他 GUI/系统门禁仍未齐，不能关闭阶段 6。

## 阶段 0 证据状态（已结束；延期项保留原状态）

**Beta 范围阶段 0 收尾评审：PASS（2026-11-09）**。当前已启用本机优先 Beta 路径的证据和回归已核对；原始 §13 全量 POC 仍有 `PARTIAL/OPEN` 项，不宣称全量阶段 0 通过。按 C-007，这些项目在对应能力启用或正式分发前补齐，触发点见追踪矩阵。0A–0H 的历史证据和未闭环项仍见追踪矩阵。2026-11-10 当前代码复核：Python 全量 281 passed、1 条既有 Starlette/httpx 弃用警告；此前一轮全量中 APFS-128 `backup-copy` 临时映像子进程通用 `OSError`，目标用例单独复跑 1 passed，随后当前全量也通过，偶发原因未判定；Swift 全量 43 项通过，Beta target 构建成功。2026-11-10 于代码基线 `0418d25` 复核 CI 等价门禁：Ruff、mypy、`uv lock --check`、后端全量 276 passed、compileall、tracked-file detect-secrets、Swift 43 项与 Beta target build 全部通过；本次没有触发远端 GitHub Actions。历史 GitHub Actions run `42489738004` 仍只证明旧 commit `51b9ab9`（当时 Python 162、Swift 31）。当前本地提交尚未推送，PR 触发路径未实际运行；最新 Python SBOM 已按 `uv.lock` 重生成并校验 63/63 非根依赖。D-013 Beta GUI 样本已达到计划数量并低于门槛：启动 n=20/P95=700 ms，partial 216 次/各窗口 P95≤41.5 ms，停止→final n=21/P95=97.9 ms。POC-01 并发 probe 新增 13 轮，详见 `phase0-local-asr.md` 与逐轮 CSV；Consent/Policy 新增在途 generate/stream 撤销取消 fake-adapter 回归，窄回归 50 项通过（含同一 Consent 下并发撤销）；完整 Agent/产品负载和 Consent 持久审计仍未验收。其他缺口继续按追踪矩阵逐项关闭，不以延期冒充通过。

2026-11-10 0G 更新：核对 Qwen 官方 Apache-2.0 声明、sherpa 官方导出指引、第三方转换仓库文件列表和镜像模型卡后，仍未找到转换工件与随包音频的独立许可；训练数据权利链也无逐项证据。阶段 0 原始模型许可项继续 PARTIAL；Beta 不打包该候选。详见 `poc/phase0-model-license-review.md`。

2026-11-10 D-005 费用输入补证：DeepSeek 官方当前价目将 `deepseek-flash` 映射到 V4.1-Flash-1017，并按缓存命中/未命中、输出 token、UTC 峰谷时段定价；Chat Completions usage 提供 token 分类但没有请求级费用字段，价目可调整。故现有 token 只能支持明示为估算的计算，不能据此声称实扣成本；仍须确定估算口径/版本更新、OpenRouter USD 与实际充值支出的关系、缺失值 fail-closed、跨进程累加及并发/月界策略。2026-11-10 用户确认：缺少请求级实扣费用/usage 或汇率时，按版本化公开价估算并明确标注；估算达限后拦截。版本化估算器已覆盖当前固定 Beta 三组云模型价目与 SAFE 汇率快照；SQLCipher 月聚合、用量页 80 元提示、预算 100 元请求前门禁和跨实例原子预留/结算已接入。当前月份功能启用前的账单无法回填；真实 Provider usage/cost E2E 与快照更新仍待验证，细节见 `docs/beta/orchestrator-framework.md`。

## 当前执行顺序

2026-11-10 B3 备份恢复实机续验：旧 Beta 实例不弹系统文件面板，正常退出并按仓库脚本重建后，NSSavePanel/NSOpenPanel 均正常。导出一份加密临时快照（274,726 bytes）、重选并确认恢复后，界面停在“处理中”，未见认证/终态；应用退出后数据库修改时间未变且没有 pre-restore 文件，未进入换库，本轮不记恢复通过。临时副本已删除。发现并修复默认备份名双后缀，最新面板显示 `PersonalAssistant.pacbackup`；Swift 84 项通过、Beta build 成功。设备认证/恢复结果仍待验收，详见 `docs/HANDOFF.md`。

2026-11-10 B3 加密备份 GUI 重试：用一次性口令启用导出按钮后，accessibility 点击和坐标点击均未打开 NSSavePanel；临时口令已清空，`.poc-data` 未发现本轮备份文件。原因未判定，不能归因代码或自动化；再次验收先确认面板能打开，再继续备份/恢复。详见 `docs/HANDOFF.md`。

2026-11-10 阶段 6 主机/包基线：当前回归运行于 macOS 26.5.1，Beta Info.plist 最低版本为 14.0；当前 bundle 为 ad hoc 签名、无 Team ID。未验证 macOS 14 runtime、Developer ID/notarization 或正式安装器，不能关闭发布门禁。详情见 `docs/HANDOFF.md`。

2026-11-10 阶段 6 本机 CI 等价门禁复核（代码基线 `a21ec3d`）：后端 347 passed、1 条既有弃用警告；Swift 84 项通过；Ruff、CI mypy、锁文件、compileall、tracked-file secret scan 与 Beta target build 均通过。没有运行远端 Actions/Provider/麦克风/系统授权/备份恢复，因此阶段 6 仍开放。命令和边界见 `docs/HANDOFF.md`。

2026-11-10 B3 备份恢复表单复核：打开备份页时恢复按钮禁用且未选择文件；只确认空选择不会触发恢复。页面仍显示此前导出成功提示，本轮未创建/读取备份、未输入口令或修改数据。用户自选位置、错误口令、系统认证和恢复故障 GUI 验收仍待完成，详见 `docs/HANDOFF.md`。

2026-11-10 阶段 6 用量面板 GUI 复核：刷新后显示 1 条 Ollama L0 完成请求，输入/输出 token、未知费用与缓存命中状态清楚；月估算 ¥0/¥100、¥80 提示线和估算说明可见。两条 EventKit 审计仅呈现 L2 元数据，没有事件内容。空记录与加载失败状态仍待独立验收；无云请求或系统权限操作。详见 `docs/HANDOFF.md`。

2026-11-10 阶段 6 代码提交 `35d6644` 本机 CI 等价门禁：`uv lock --check`、Ruff、CI mypy、tracked-file `detect-secrets-hook`、compileall、后端全量 346 passed、Swift 全量 68 passed 和 `personal-assistant-beta` 构建均通过（后端仅 1 条既有 Starlette/httpx 弃用警告）。远端 Actions 未运行，阶段 6 仍开放。

2026-11-10 V1.1 快捷指令：聊天页“新对话”按钮增加 macOS `⌘N`；`⌘L` 聚焦消息输入框，不发送、不启动语音。快捷键复用既有会话创建逻辑和 SwiftUI FocusState；Swift 全量回归与 Beta target build 通过。GUI 实测 `⌘L` 将焦点移至消息输入框；`⌘N` 显示“已创建新会话”并打开空会话，未发送消息或启动语音。

2026-11-10 V1.1 本机朗读语速预设：模型设置提供较慢/标准/较快三档，保存在本机，只用于本机语音合成。SpeechEngine 传递速率有自动回归；GUI 已实测依次切换较慢、较快并恢复标准。真实声学体验仍待设备验收，详见 `docs/HANDOFF.md`。

2026-11-10 V1.1 模型预设：设置页支持保存/应用/删除命名配置，数据只含来源、型号和白名单 Provider ID，不含凭据；应用云端预设仍显示目标并复用原授权/预算/审计链路。存储层回归覆盖序列化/验证、旧字段迁移和未知 Provider 拒绝；最新 Swift 全量与 Beta build 结果见 `docs/HANDOFF.md`。2026-11-10 GUI 实测保存本机 Ollama / qwen3.5:0.8b 预设；改临时型号后点击“使用”恢复为已保存型号；随后删除临时预设，主界面确认仍为原本机型号。未切换云端或发起新模型请求。

2026-11-10 B3 客户端历史读取并发保护：SwiftUI 为分页、会话选择、记忆来源跳转和聊天历史刷新增加代际校验、会话 ID 核对和分页请求 ID，阻止失效的迟到响应覆盖当前会话、追加到错误会话或清除新分页请求状态。Swift 全量 68 项（含分页代际及加载态竞争回归）、Beta target build 通过；并发 GUI 复测尚未完成。已保存来源跳转 GUI 点验和临时合成记忆清理已于 2026-11-10 完成，详见本清单 B3 状态与 HANDOFF。

2026-11-10 阶段 6 本地门禁复核：后端全量 346 passed（1 条既有 Starlette/httpx 弃用警告），Swift 62 passed，Ruff、37 模块 mypy、CI mypy、tracked-file secret scan、锁文件/compileall 和 Beta target build 均通过；未运行远端 GitHub Actions，阶段 6 不关闭。精确命令及边界见 `docs/HANDOFF.md`。

2026-11-10 阶段 6 用量面板 GUI 检查：本机已完成 Ollama 请求显示 L0、token 输入/输出；费用及缓存命中呈未知，云预算 ¥0/¥100 与估算说明可见。空记录和加载失败仍待 GUI 验收；无云请求。

2026-11-10 阶段 6 模型设置 GUI 检查：显示本地 `qwen3.5:0.8b` 和 Ollama 安装/运行说明；没有 capability 明细面板，故型号配置显示通过而 capability 查询/认证失败 UI 仍开放。

2026-11-10 阶段 6 精确型号 capability 查询：认证 loopback 客户端及设置页显式查询已实现并实机通过；`ollama / qwen3.5:0.8b` 报告精确显示已核验能力、有限能力、未知项及证据时间/引用。Swift 63 项与 Beta build 通过。重启时曾短暂 CUA 超时后恢复，原因未判定。

2026-11-10 阶段 6 capability 负向回归：未知型号保持 unknown，跨型号报告拒绝，HTTP 503 正文不进入客户端错误。Swift 全量增至 66 项，Beta build 通过。

2026-11-10 阶段 6 后续本地门禁：后端 346 passed（1 条既有弃用警告）、Swift 66 passed、Ruff、CI mypy、锁文件、compileall、tracked-file secret scan 和 Beta build 全通过；远端 Actions 未运行，阶段 6 保持开放。

2026-11-10 B8 Skill GUI 冒烟：选择“行动项整理”后发送即清空至 `Skills 0`；本机 qwen3.5:0.8b 超过两分钟仍无正文，停止后已取消。仅选择消费路径通过，延迟原因未判定，不外推为 Skill 缺陷。

2026-11-10 B9 输出质量迭代：专业角色与综合层明确约束相关性、逐项覆盖、未知数值不得臆造及数量/长度/格式；API 回归确认指令传递。多次本机 GUI 合成题表现波动：近期复测未臆造时长，但仍以泛化的工具准备替换明确的场地清洁要求，角色观点超长。单样本不构成保证，不能用于时间/数量承诺或自动执行；B9 保持 IN PROGRESS。后端全量 346 passed，详见 `docs/beta/orchestrator-framework.md`。

2026-11-10 B2 TTS GUI 尝试：本机 qwen3.5:0.8b 合成短句请求超 30 秒无正文后停止；该次未点播。后续已用既有本机回复验收 UI 朗读启停；设备实际可听性仍待用户确认。延迟根因未判定，不归因 TTS；无云请求、无麦克风。

2026-11-10 B2 TTS 控制 GUI：复用已有本机会话回复，点击朗读后状态显示开始，点击停止后显示已停止，控制路径通过；实际扬声器/耳机可听性仍待用户设备确认。

2026-11-10 B3 已保存来源 GUI：创建临时合成确认记忆并验证来源详情可读；操作按钮布局和显式对话跳转按钮已修复，Swift 63 项及 Beta build 通过。新按钮 GUI 点验未完成（重启后 CUA 连续超时）；临时记忆尚未删除，恢复 GUI 后优先完成跳转和清理。

2026-11-10 B3 任务提醒资格边界：过期、无效或缺失时间的任务不再留在重建提醒集合；单条无效重排会撤销同 ID 旧通知。用户拒绝或撤销通知授权时也会关闭提醒偏好并清理 PAC 待发通知。Swift 全量 62 项通过；mock 覆盖授权拒绝/撤销清理，系统通知权限/投递仍未实测。

2026-11-10 B1 本机失败路径 GUI：干净新会话中发送合成短句到临时不存在的 Ollama 模型，失败消息和 run 状态正确、无云 fallback；已恢复原模型 `qwen3.5:0.8b`。该次之后停止/重启 Ollama 路径与云 API 错误 UI 当时仍待验收；2026-11-10 后续恢复成功请求已记录于 B1 主状态和 `docs/HANDOFF.md`。对话保留作本机合成记录，详见 `docs/beta/macOS-beta-chat.md`。

2026-11-10 阶段 6 本机 CI 等价门禁复核：后端全量 341 passed（1 条既有 Starlette/httpx 弃用警告）；Ruff 全目录、CI mypy、compileall、`uv lock --check`、tracked-file detect-secrets、Swift 60 项和 Beta target build 均通过。扫描命中的测试口令均为合成字面量，已逐行 allowlist 并复扫通过。初次桌面状态读取失败；后续 B6 日历/提醒事项当前授权状态下只读查询 GUI 已实测，但首次授权/拒绝路径未验。B1/B3/B5 其他 GUI 验收及远端 GitHub Actions 仍未完成，阶段 6 不关闭。详见 `docs/HANDOFF.md`。

2026-11-10 POC 脚本静态质量：修复两个历史未使用符号，`ruff check scripts` 全目录通过；未运行会启动本机模型/设备的测量脚本。

2026-11-10 工程静态质量：修复并发 ASR/模型测量探针的异构泛型类型错误，并为 FastEmbed 注入引擎补充结构化协议。`mypy pac_poc` 37 个模块通过；Ruff 两个修改模块通过；相关窄测 9 passed；后端全量 341 passed、1 条既有 Starlette/httpx 弃用警告。详细命令见 `docs/HANDOFF.md`。

2026-11-10 B3/V1.1 持久化切片：SQLCipher store/schema、Keychain 密钥私有管道、多会话列表/新建/切换/分别删除、指定会话历史读写，V2 本机任务 CRUD/状态迁移/30 天清理已分段提交。任务状态转移图后由用户按 D-018 确认为产品规则。当前后端全量 305 passed（1 条既有 Starlette/httpx 弃用警告）；Swift 全量 51 项、Beta build、Ruff、mypy、`uv lock --check` 通过。V1.1 已确认记忆来源/修正/历史查看与会话重命名均已接入；来源 UUID 仅在本地数据库/UI 使用，不随 Model Gateway 消息发送。此前全量曾有 APFS-128 临时映像间歇 RuntimeError，目标单测及重跑全量通过，原因未判定。任务和确认记忆基础 UI/API 已接入；记忆版本历史只读查看已接入；历史分页/加载边界、备份/恢复验收仍未完成；会话重命名验证后的当前回归为后端 300 项、Swift 51 项通过。会话现可重命名。纠错编辑现需显式确认且保留版本快照。

2026-11-10 D-003 保留清理改进：数据库密钥启动时立即清理过期完成任务与云安全审计元数据，服务运行期间每 6 小时清理两类 SQLCipher 数据，退出先取消维护任务再关闭 store。定向回归 3 passed，后端全量 340 passed（1 条既有 Starlette/httpx 弃用警告），Ruff/mypy 及阶段追踪契约 9 项通过。实际六小时墙钟等待及 GUI/实机运行周期未验证。

2026-11-10 V1.1 记忆来源选择：已确认记忆表单可浏览全部本机会话、选择历史消息作为来源，并通过游标分页加载更早消息；不发送聊天内容到 Provider。Swift 全量 60 项与 Beta target 构建通过。GUI 手动来源选择/跳转验收仍待执行。

2026-11-10 B5 补充自动客户端证据：Swift URLProtocol 回归捕获认证 loopback `/chat/stream` 请求并确认 `import_ids` 序列化；Swift 全量 44 项通过，`personal-assistant-beta` target 构建通过。另在 API 调用 ContextBuilder 前增加附件字符数下限检查，100,000 字符超大附件在 Orchestrator 构建前返回 413；后端全量 282 passed，1 条既有警告。它不替代 GUI 对话中实际引用资料的手动验收，B5 保持 IN PROGRESS。

2026-11-10 阶段 6 在提交 `4d16bec` 的本机等价门禁：依赖锁、Ruff、mypy、tracked-file secret scan、compileall、后端 282 项、Swift 44 项及 Beta target build 均通过。Swift 门禁首次复现了 B5 URLProtocol 测试共享静态捕获器的并行竞态；已隔离拒绝路径网络探针，修复后 Swift 全量复跑通过。远端 GitHub Actions 未运行。

0. **阶段 1 工程底座（DONE，当前决策范围）**：Loopback API trace、统一错误、依赖注入、最小 health、集中配置和可注入进程启动设置均完成；云凭据保存/删除需 Touch ID 或设备密码 gate。Ruff、mypy、secret scan、锁文件、Python/Swift 测试及 `personal-assistant-beta` 产品构建进入 CI。SQLCipher 数据库、schema migration、聊天/任务/确认记忆持久化与加密备份恢复已按 D-003/D-006/D-007 决策实现并分阶段验收；云 Provider 聊天请求的 30 天 metadata-only 审计已接入并在用量页展示；尚未覆盖的审计事件应在对应安全敏感能力启用前补齐，因此这不是规格书完整 V1 持久化底座验收。

1. **B0 应用可运行骨架（DONE）**：SwiftUI 单实例窗口的本机 Beta 入口已完成；本机后端启动、健康状态、错误恢复和关窗退出清理均已验证。
2. **B1 本机文字对话和模型设置（IN PROGRESS）**：本机 Ollama/固定云端配置选择；选中云端 Provider 后持续授权，聊天时不弹逐条确认；Keychain 凭据和无自动 fallback。用户与本轮 GUI 均确认 Ollama 正常运行时本机聊天可回复。模型设置云端披露已实机复核，Ollama 双进程与模型安装帮助说明已实机确认。长流取消后 Ollama 短请求明显变慢，疑似上游 runner 槽释放问题；停止提示已如实区分客户端取消与上游状态。需确认可用 Ollama 版本/恢复策略，并完成可本地验证的错误路径和云 API 错误 UI 验收。
3. **B2 本地语音**：接入本机实时 Streaming ASR、明确点击才采集、有限内存/队列、partial/final 草稿边界和按键打断；识别失败不得转云。完整双向语音、AEC、自动插话和系统生命周期仍需阶段 3 决策与验证。
4. **单助理编排框架（IN PROGRESS）**：`MainAssistantOrchestrator` 支持封闭的固定 profile registry：主助理、项目、会议、任务规划；角色由 UI 显式选择，后端只接受四个固定键并将固定指导放入 system context，主助理路径保持原样。角色本身没有工具/后台执行/外部写权限。其余已有能力、待验收项详见 `docs/beta/orchestrator-framework.md`；版本化估价和跨实例 SQLCipher 月度预算预留/结算已接入；当前月回填限制、真实云型号 usage/cost E2E 与价格快照更新仍待关闭。
5. 用户已决定本地持久化聊天、任务与确认记忆；B3 存储/API/UI 持续开发。D-014 离线对照现含 24 条合成中英改写题（Embedding 23/24 top-1、24/24 top-3；FTS5 为 0/24）、12 条精确词面控制（均 12/12）、12 条无相关项负例（Embedding 均返回、FTS5 均拒答）；三轮重复资源观察 real 1.48–2.03 秒、中位数 1.57 秒、maximum RSS 909,656,064–911,540,224 bytes。相似度 0.3251/0.2334、资源指标均仅为合成集观察，不作产品阈值或性能保证；仍缺更大且独立复核的平衡人工标注语料、冷缓存启动与产品资源目标，Embedding 保持关闭。D-015 通用导出已暂缓。D-012 文件导入按格式分步启用：TXT/Markdown 的文件选择、暂存、聊天引用和移除已通过单一样本 GUI 验收；PDF 在解析器资源限制安全 POC 前保持禁用。D-006 手动加密备份导出/当前 Mac 恢复已实现；预备份已按新决议只保留最近一份，新副本在恢复切换成功后原子替换；连续恢复窄测通过。GUI、Keychain 实机认证、强制终止/断电恢复仍待验收。B4 千问 Token Plan 文本/实时语音仍须符合个人版条款及 Consent/Policy，不接入自建应用路径。

阶段 1 当前决策允许的工程底座已完成并有 CI 门禁；SQLCipher 产品数据库与迁移已用于当前 Beta。D-005 跨实例原子月预算请求门已实现，真实 Provider 端到端计费核对仍待验收；其余安全操作审计、PDF 产品导入和产品 Embedding 仍未启用，按追踪矩阵触发点排期。TXT/Markdown 导入在 B5 增量实现中，不代表完整文件导入验收。完整阶段状态以追踪矩阵 §6 为准。

### 非阻塞问题回修清单

- **B1 / Ollama 取消后紧接请求变慢**：曾观察到一轮长流取消后短请求延迟明显增加；本机版本、模型、时序和上游行为都可能影响结果，当前根因未证实。2026-11-10 同机复测中默认 thinking 请求延迟波动较大，无法归因；显式 `think:false` 下，短句基线 1.80 秒、长流取消后短句 1.31 秒，未复现取消后变慢。停止提示已说明本机可能仍在收尾。此项不阻塞聊天主闭环；若后续默认配置下仍可稳定复现，再集中排查。详见 `beta/macOS-beta-chat.md`。
- **阶段 0 SQLCipher APFS-128 临时映像 POC 偶发失败**：2026-11-09 全量回归中一轮返回通用 `RuntimeError`，紧接的同用例复跑通过，随后全量通过；2026-11-10 一轮全量回归在 `backup-copy` 场景失败，子进程返回 `{"status":"error","error_type":"OSError"}`，随后目标用例单独复跑通过、全量 265 项也通过，原因未判定。该测试只在仓库 `.poc-data` 下创建临时映像，不影响 Beta 数据；若后续再次出现，集中收集子进程状态/挂载清理证据，不据单次结果推断 APFS 根因。
麦克风复现命令（从仓库根目录，在本机交互式终端运行）：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/run_live_microphone_poc.py .poc-data/models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 --seconds 30
```

## 测试版门禁

- 每个可用闭环先做必要的本机验证并记录实际范围；不为未启用的后期能力预先重复验证。
- 涉及敏感数据持久化、远端出站、麦克风采集或正式分发的能力，必须先满足对应安全与授权要求。
- 每个工作包关闭时，更新实现文档、任务状态和 `HANDOFF.md`，列明验证与剩余限制，并提交 Git。
