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

在完成当前单用户 Beta/V1 可用闭环后，继续规格书 §13 的 V1.1、V2 和 V3 开发，不再把 V1.1/V2/V3 作为“以后再说”的范围。路线依赖仍按阶段门禁推进：V1.1 记忆中心/导出恢复优化；V2 完整任务状态机、只读日历/待办、受控通知；V3 固定专业 Agent、多 Agent 协作、经审批的外部写操作与 Skills。用户已决定本地持久化聊天、任务和已确认记忆；聊天/已确认记忆手动删除，完成任务 30 天后清理。数据库加密方向已选 SQLCipher + Keychain 随机密钥、登录后自动打开；Keychain 生命周期与产品验证仍待完成；手动加密备份已选定为用户位置 + 每份独立口令 + 恢复前认证/预备份，用户已选择 scrypt（N=32768,r=8,p=1）、不保存备份口令、仅当前 Mac 恢复；RTO/副本保留、损坏/中断恢复仍待验证。Embedding、导出细节仍待定。D-003/D-006/D-007/D-014/D-015 按 DECISIONS 状态跟踪。聊天、任务和用户确认记忆当前已通过 B3 写入本机 SQLCipher；本机任务提醒已实现，系统通知授权及实际投递仍待 GUI 验收。

项目开发规格共定义 7 个阶段：阶段 0 POC/工程基线、阶段 1 V1 工程底座、阶段 2 V1 对话与 Model Gateway、阶段 3 实时语音、阶段 4 长期记忆与资料导入、阶段 5 安全加固/备份/运维、阶段 6 V1 系统验收/发布候选。阶段 0 Beta 范围和阶段 1 当前决策允许范围已完成；当前按单用户 Beta 队列继续阶段 2，部分阶段 3/4 能力曾提前实现，不代表相应阶段整体完成。

**阶段 0 Beta 范围已结束（2026-11-09），附未实现/延期清单。** 用户确认剩余小功能按触发条件延期；它们不得标为完成或通过。原始 §13 全量 POC 的 `PARTIAL/OPEN` 外部证据在相关功能启用或正式分发前继续追踪。详细清单见[阶段 0 追踪矩阵](poc/phase0-traceability.md)。阶段 1 当前决策允许的无持久化工程底座已完成（2026-11-09，提交 `5f6fe24`）；其后按重开决议推进 B3，现有 SQLCipher store、Keychain 启动密钥注入、聊天历史与 V2 本机任务 API/UI 已接入。确认记忆、备份恢复、Keychain 实机与加密产品验收仍未完成。

## 单用户 macOS 测试版交付队列

| 顺序 | 工作包 | 状态 | 完成条件 / 说明 |
|---:|---|---|---|
| B0 | 应用可运行骨架 | DONE | SwiftUI `.app` 可由仓库脚本构建启动；本机服务启动失败时按错误类型显示中文提示并可重试；supervisor 对启动/停止/状态读取串行化并覆盖启动中停止。GUI 故意返回无效握手后，替换为本机 health fixture 并点击重试成功；真实本机服务启动连接成功；单窗口关闭后 app 与 backend 均退出且无残留。 |
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或千问应用 API、DeepSeek、OpenRouter 固定路由；本地模型 ID 可配置。选择云端即持续授权后续消息发往该服务商，设置有告知且无逐条弹窗；Keychain、固定目标、L3 拦截、错误脱敏和无自动 fallback 保留。每次发送快照当前 Provider/模型；切换时取消旧客户端流并屏蔽迟到回调，状态栏显示当前及本轮实际 Provider/模型。用户已实机确认模型间可自由切换、打开 Ollama 后 PAC 本地模型可聊天，本机短句也收到精确回复。Ollama 必须运行且模型已安装。设置页云端披露与只读 Key 状态已实机复核（OpenRouter 已保存，未读 Key），新建的 Ollama 配置帮助说明待下次 GUI 启动复核。SSE 注释保活/上游取消自动回归通过（窄回归 22 项）。Ollama 0.40.15 本机直连取消长流后，紧接短请求耗时 46.72 秒（同机默认短请求基线约 2.42 秒）；与 Ollama issue #17131 描述的断流后 runner 槽占用现象相符，根因仍属推断；停止提示已区分客户端停止与上游状态。客户端 HTTP 503 正文脱敏及 SSE error 事件解码通过；后端 fake adapter 覆盖云端 HTTP 401/402/403/429/503 错误提示脱敏、FAILED run 及无 fallback，也覆盖本机异常脱敏、FAILED run 和 unknown usage/cost。本机 HTTPX 连接失败提示检查 Ollama；响应超时提示其可能仍在本机生成，不显示云端计费措辞。远端自动尝试最多 2 次，仅对明确 429 和连接建立前错误；读/写超时不重试，避免服务商可能已受理的请求被重复发送。429 遵从最多 2 秒的数值 Retry-After；Consent 撤销会取消退避中的任务。当前后端全量 282 passed、1 条既有 Starlette/httpx 弃用警告；APFS-128 备份耗尽用例曾间歇失败，隔离复跑和随后全量均通过，原因未判定。Swift 全量 44 项与 Beta build 通过。仍需在干净会话实机确认本机与云错误消息呈现，确认 Ollama 恢复路径，并完成云 API 错误 UI 验收。APFS-128 临时映像偶发失败及复跑证据列于非阻塞问题清单。用户反馈千问现可正常聊天；D-005 云预算硬拦截未实现；D-010 Provider 范围为千问应用 API、DeepSeek（中国）、OpenRouter（Global）；Token Plan `sk-sp-` 个人版不直连自建应用。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | IN PROGRESS | 已扩展为受认证 loopback WebSocket 本机实时 ASR：200 ms PCM 帧、有界队列、临时 partial、停止后 final 入草稿；一次性语音入口也按请求流分块限长，无 Content-Length 时仍执行 30 秒字节上限；批量 ASR 原子获取单会话锁并在等待超时后拒绝并发请求；Uvicorn WebSocket 消息上限为最大协议帧 12,804 字节；用户曾验证 final、取消、文字生成时打断、录音中 Cmd-Q 清理。GUI 曾在停止时断开 socket、随后的第二次录音报 ASR 忙（partial n=2、停止→final n=0）。根因已查明：`LocalVoiceTranscriber.end_stream()`/`abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，清理再次异常使 WebSocket finally 跳过锁释放。现改为重置底层 recognizer，并在清理异常时仍释放会话锁。真实 Uvicorn + 项目本机 ASR 模型连续 3 轮 PCM 流式识别均收到 partial/final/ended；Python 全量 183 项通过（1 条既有 Starlette/httpx 弃用警告）；Apple URLSessionWebSocketTask + 真实 Uvicorn + 本机 sherpa-onnx 模型 + 固定 PCM WAV 连续 3 轮均收到 partial/final/ended。用户已确认 GUI 实时语音故障修复。启动面板单位错误已定位并修复：秒值遗漏乘以 1,000。用户提供的 20 个启动值换算为 500–700 ms，nearest-rank P95=700 ms，低于 5 秒门槛，启动采样计划已完成；partial 更新 216 次、22 个窗口 P95 摘要最高 41.5 ms；停止→final 21 次 pooled P95 97.9 ms、最大 99.9 ms。三项性能均已满足门槛；本机 TTS 现确保第二次点播先停止当前语音，停止失败则不排队，Swift 自动回归覆盖该逻辑；具体结果见 `docs/beta/macOS-beta-voice.md`。D-013 启动 20 个样本计划已完成。模型报告已通过本机 SHA-256 将双语 Zipformer 与 Qwen ONNX 权重精确对应到公开模型 revision；模型训练数据、Qwen 转换代码/工件和随包音频许可仍开放。详见 `beta/macOS-beta-voice.md` 与 `poc/phase0-model-license-review.md`。 |
| B3 | 会话保存与恢复 | IN PROGRESS | 用户已决定本地持久化聊天、任务与已确认记忆：聊天/记忆手动删除，完成任务 30 天清理；SQLCipher + Keychain 随机密钥、手动加密备份方向已选。Beta 已接入本机 SQLCipher、Keychain 启动密钥管道、多会话读写/新建/切换/重命名/分别删除、V2 任务 CRUD/提醒与清理、手工确认记忆 CRUD/FTS/显式修正版本、版本历史只读查看及消息来源关联/查看。当前后端全量 305 passed（1 条既有 Starlette/httpx 弃用警告）、Swift 全量 51 项通过，Beta build、Ruff、mypy、锁文件检查通过。仍未完成：历史分页/虚拟化和大历史加载边界、来源跨会话跳转、备份口令容器及 SQLCipher 在线导出核心已实现，API/UI/预备份/恢复/回滚仍未接入；真实 Keychain/通知验收未做。任务状态转移图仍为暂定规则，Embedding 关闭。详见 `beta/persistent-storage.md`。 |
| B4 | 千问 Token Plan 扩展接入 | DEFERRED | 个人版条款仅允许经官方支持的编程/智能体工具扩展交互使用，排除本项目自建应用后端。只有取得允许自建应用的官方授权/套餐，或实现受支持工具扩展集成后，才能纳入应用选项。协议、地址和状态见 `beta/qwen-token-plan-integration.md`。 |
| B5 | V1 文件导入及正式发布扩展 | IN PROGRESS | 已实现用户主动选择 TXT/Markdown、本机临时导入、显式移除及仅本机模型上下文；10 MB/UTF-8/普通文件名验证，有界进程内内存，无路径持久化。Swift 客户端已自动验证 basename/内容/认证 loopback 请求、无路径传输和 PDF/超限网络前拒绝；Beta UI 对文件导入增加单飞状态，导入期间禁用重复选择、发送和语音入口，避免并发上传绕过客户端 4 文件上限；Swift 全量 40 项通过且 Beta target build 通过；后端导入接收也采用 API 单飞门禁，另一上传在首请求分块接收期间立即返回 409，且请求体未被消费，避免并发请求在注册表容量检查前各自暂存 10 MiB；GUI 文件选择、导入暂存和显式移除已由当前 Beta 实机冒烟通过：141-byte 合成 TXT 显示 65 字符，移除后 chip 消失且状态成功；应用选择本机 Ollama，未发消息或触发 Provider。自动化还验证合成提示注入文本与 JSON 样式文件名仍作为单条 user 消息中的 JSON 不可信资料，system/user 角色固定且无工具注册；此测试只验证上下文边界，不证明模型语义层面对任意注入免疫。聊天中引用已导入资料的 UI 路径仍待验证。较早旧实例控件树未呈现入口，当前仓库构建入口可见。新增可选隔离 pypdf 安全 POC，7 项自动测试覆盖输入/页数/文本/解析工作边界、合成 FlateDecode 解压上限、提取文本字符上限和超时转换；CI 显式安装 PDF POC extra，确保相关自动化用例不被依赖缺失而跳过。本机尝试以 `RLIMIT_AS/DATA/RSS` 设置 512 MiB 硬内存上限失败；另以 `/bin/sh ulimit -v` 在 worker 启动前设置 768 MiB、1 GiB、1.5 GiB 均被 macOS 拒绝（`Invalid argument`）。仍缺代表性恶意语料、真实 CPU/墙钟超时压力证据及 GUI 验收，PDF 继续禁用。详见 `docs/beta/file-import.md`。D-014 已允许持久化用户确认的记忆，但 Embedding 型号/格式待定；D-015 数据导出范围仍待确认；云语音、备份/恢复、自动恢复、完整许可通知和正式签名分发仍延后至对应功能开发/发布前。 |

## 阶段 0 证据状态（已结束；延期项保留原状态）

**Beta 范围阶段 0 收尾评审：PASS（2026-11-09）**。当前已启用本机优先 Beta 路径的证据和回归已核对；原始 §13 全量 POC 仍有 `PARTIAL/OPEN` 项，不宣称全量阶段 0 通过。按 C-007，这些项目在对应能力启用或正式分发前补齐，触发点见追踪矩阵。0A–0H 的历史证据和未闭环项仍见追踪矩阵。2026-11-10 当前代码复核：Python 全量 281 passed、1 条既有 Starlette/httpx 弃用警告；此前一轮全量中 APFS-128 `backup-copy` 临时映像子进程通用 `OSError`，目标用例单独复跑 1 passed，随后当前全量也通过，偶发原因未判定；Swift 全量 43 项通过，Beta target 构建成功。2026-11-10 于代码基线 `0418d25` 复核 CI 等价门禁：Ruff、mypy、`uv lock --check`、后端全量 276 passed、compileall、tracked-file detect-secrets、Swift 43 项与 Beta target build 全部通过；本次没有触发远端 GitHub Actions。历史 GitHub Actions run `42489738004` 仍只证明旧 commit `51b9ab9`（当时 Python 162、Swift 31）。当前本地提交尚未推送，PR 触发路径未实际运行；最新 Python SBOM 已按 `uv.lock` 重生成并校验 63/63 非根依赖。D-013 Beta GUI 样本已达到计划数量并低于门槛：启动 n=20/P95=700 ms，partial 216 次/各窗口 P95≤41.5 ms，停止→final n=21/P95=97.9 ms。POC-01 并发 probe 新增 13 轮，详见 `phase0-local-asr.md` 与逐轮 CSV；Consent/Policy 新增在途 generate/stream 撤销取消 fake-adapter 回归，窄回归 50 项通过（含同一 Consent 下并发撤销）；完整 Agent/产品负载和 Consent 持久审计仍未验收。其他缺口继续按追踪矩阵逐项关闭，不以延期冒充通过。

2026-11-10 0G 更新：核对 Qwen 官方 Apache-2.0 声明、sherpa 官方导出指引、第三方转换仓库文件列表和镜像模型卡后，仍未找到转换工件与随包音频的独立许可；训练数据权利链也无逐项证据。阶段 0 原始模型许可项继续 PARTIAL；Beta 不打包该候选。详见 `poc/phase0-model-license-review.md`。

2026-11-10 D-005 费用输入补证：DeepSeek 官方当前价目将 `deepseek-flash` 映射到 V4.1-Flash-1017，并按缓存命中/未命中、输出 token、UTC 峰谷时段定价；Chat Completions usage 提供 token 分类但没有请求级费用字段，价目可调整。故现有 token 只能支持明示为估算的计算，不能据此声称实扣成本；仍须确定估算口径/版本更新、OpenRouter USD 与实际充值支出的关系、缺失值 fail-closed、跨进程累加及并发/月界策略。D-005 保持未实现，细节见 `docs/beta/orchestrator-framework.md`。

## 当前执行顺序

2026-11-10 B3/V1.1 持久化切片：SQLCipher store/schema、Keychain 密钥私有管道、多会话列表/新建/切换/分别删除、指定会话历史读写，V2 本机任务 CRUD/状态迁移/30 天清理已分段提交。当前任务状态转移图是明确记录的实现暂定规则，规格只列状态集合，V2 完整验收前仍需产品语义复核。当前后端全量 305 passed（1 条既有 Starlette/httpx 弃用警告）；Swift 全量 51 项、Beta build、Ruff、mypy、`uv lock --check` 通过。V1.1 已确认记忆来源/修正/历史查看与会话重命名均已接入；来源 UUID 仅在本地数据库/UI 使用，不随 Model Gateway 消息发送。此前全量曾有 APFS-128 临时映像间歇 RuntimeError，目标单测及重跑全量通过，原因未判定。任务和确认记忆基础 UI/API 已接入；记忆版本历史只读查看已接入；来源跨会话选择/跳转、历史分页/加载边界、备份/恢复仍未完成；会话重命名验证后的当前回归为后端 300 项、Swift 51 项通过。会话现可重命名。纠错编辑现需显式确认且保留版本快照。

2026-11-10 B5 补充自动客户端证据：Swift URLProtocol 回归捕获认证 loopback `/chat/stream` 请求并确认 `import_ids` 序列化；Swift 全量 44 项通过，`personal-assistant-beta` target 构建通过。另在 API 调用 ContextBuilder 前增加附件字符数下限检查，100,000 字符超大附件在 Orchestrator 构建前返回 413；后端全量 282 passed，1 条既有警告。它不替代 GUI 对话中实际引用资料的手动验收，B5 保持 IN PROGRESS。

2026-11-10 阶段 6 在提交 `4d16bec` 的本机等价门禁：依赖锁、Ruff、mypy、tracked-file secret scan、compileall、后端 282 项、Swift 44 项及 Beta target build 均通过。Swift 门禁首次复现了 B5 URLProtocol 测试共享静态捕获器的并行竞态；已隔离拒绝路径网络探针，修复后 Swift 全量复跑通过。远端 GitHub Actions 未运行。

0. **阶段 1 工程底座（DONE，当前决策范围）**：Loopback API trace、统一错误、依赖注入、最小 health、集中配置和可注入进程启动设置均完成；云凭据保存/删除需 Touch ID 或设备密码 gate。Ruff、mypy、secret scan、锁文件、Python/Swift 测试及 `personal-assistant-beta` 产品构建进入 CI。数据库/迁移/会话持久化/静态加密和 metadata-only 30 天审计日志明确未实现，按 D-003/D-007 触发条件延期；因此这不是规格书完整 V1 持久化底座验收。

1. **B0 应用可运行骨架（DONE）**：SwiftUI 单实例窗口的本机 Beta 入口已完成；本机后端启动、健康状态、错误恢复和关窗退出清理均已验证。
2. **B1 本机文字对话和模型设置（IN PROGRESS）**：本机 Ollama/固定云端配置选择；选中云端 Provider 后持续授权，聊天时不弹逐条确认；Keychain 凭据和无自动 fallback。用户与本轮 GUI 均确认 Ollama 正常运行时本机聊天可回复。模型设置云端披露已实机复核，本机提示新文案待下次启动确认。长流取消后 Ollama 短请求明显变慢，疑似上游 runner 槽释放问题；停止提示已如实区分客户端取消与上游状态。需确认可用 Ollama 版本/恢复策略，并完成可本地验证的错误路径和云 API 错误 UI 验收。
3. **B2 本地语音**：接入本机实时 Streaming ASR、明确点击才采集、有限内存/队列、partial/final 草稿边界和按键打断；识别失败不得转云。完整双向语音、AEC、自动插话和系统生命周期仍需阶段 3 决策与验证。
4. **单助理编排框架（IN PROGRESS）**：已把总助理请求、上下文构建和 Model Gateway 流式调用抽为独立 `MainAssistantOrchestrator`；目前仅启用 `main_assistant`，上下文只使用本轮明确消息和用户主动导入的文本资料，不读写持久存储。API 路由保留认证、云授权和 SSE 错误映射。每次流式请求有有界进程内运行状态，可按 run ID 经认证 API 查询；macOS UI 显示短 ID 和状态，并在停止/切换模型后查询终态。新增认证 `/usage` 及有界进程内用量 ledger 和只读用量面板，现显示用途、数据等级、状态、区域及 token/费用状态；Gateway 可透传 Ollama 与云端流最终帧的实际 token 数，缺少最终 usage 为 UNKNOWN；OpenRouter 若返回 `usage.cost` 则以 actual USD 记录，其他缺失费用仍 UNKNOWN，不做货币换算或预算拦截。UsageLedger 现在校验 UNKNOWN 必须没有 token 数、ACTUAL/ESTIMATED 必须至少有一个 token 数，避免状态与明细矛盾。能力注册表已从随包 JSON 精确装配并注入默认 Orchestrator；认证 `/model-capabilities` 查询状态和证据，工具能力有限时标 LIMITED，未收录型号/能力保持 UNKNOWN。当前基本聊天不请求额外能力，不改变路由行为。HTTP 客户端断连后的上游取消、run `CANCELLED` 终态与 UsageLedger 记录已有 ASGI 层自动回归；DeepSeek/Qwen 流 usage 报告的 cached prompt token 已透传到 ledger 与 Swift 用量面板，但不据此估价。当前后端全量 282 passed、1 条既有 Starlette/httpx 弃用警告；Swift 全量 44 项与 Beta target build 通过。用量面板 GUI 手动冒烟及精确云型号 usage/cost E2E 仍待做；细节见 `docs/beta/orchestrator-framework.md`、`docs/beta/file-import.md`。
5. 用户已决定本地持久化聊天、任务与确认记忆；B3 存储/API/UI 接入仍在开发。D-014 的 Embedding 型号/格式与 D-015 导出规格仍待确认。D-012 文件导入按格式分步启用：TXT/Markdown 的文件选择、暂存和移除已通过 GUI 冒烟；资料进入聊天上下文的 GUI 引用路径仍待验证。PDF 在解析器资源限制安全 POC 前保持禁用。按 D-006 用户选择手动加密备份，产品流程尚未实现。B4 千问 Token Plan 文本/实时语音仍须符合个人版条款及 Consent/Policy，不接入自建应用路径。

阶段 1 当前决策允许的无持久化工程底座已完成并有 CI 门禁；预算硬拦截、持久审计、PDF 导入、Embedding、数据库迁移等均明确未实现，按追踪矩阵触发点排期。TXT/Markdown 导入在 B5 增量实现中，不代表完整文件导入验收。完整阶段状态以追踪矩阵 §6 为准。

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
