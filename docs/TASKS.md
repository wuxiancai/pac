# 阶段任务清单

最后核对：2026-11-09（Asia/Shanghai）

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

项目开发规格共定义 7 个阶段：阶段 0 POC/工程基线、阶段 1 V1 工程底座、阶段 2 V1 对话与 Model Gateway、阶段 3 实时语音、阶段 4 长期记忆与资料导入、阶段 5 安全加固/备份/运维、阶段 6 V1 系统验收/发布候选。阶段 0 Beta 范围和阶段 1 当前决策允许范围已完成；当前按单用户 Beta 队列继续阶段 2，部分阶段 3/4 能力曾提前实现，不代表相应阶段整体完成。

**阶段 0 Beta 范围已结束（2026-11-09），附未实现/延期清单。** 用户确认剩余小功能按触发条件延期；它们不得标为完成或通过。原始 §13 全量 POC 的 `PARTIAL/OPEN` 外部证据在相关功能启用或正式分发前继续追踪。详细清单见[阶段 0 追踪矩阵](poc/phase0-traceability.md)。阶段 1 当前决策允许的无持久化工程底座已完成（2026-11-09，提交 `5f6fe24`）；D-007 范围内的数据库、schema、migration、会话保存和静态加密未实现，保持延期。

## 单用户 macOS 测试版交付队列

| 顺序 | 工作包 | 状态 | 完成条件 / 说明 |
|---:|---|---|---|
| B0 | 应用可运行骨架 | DONE | SwiftUI `.app` 可由仓库脚本构建启动；本机服务启动失败时按错误类型显示中文提示并可重试；supervisor 对启动/停止/状态读取串行化并覆盖启动中停止。GUI 故意返回无效握手后，替换为本机 health fixture 并点击重试成功；真实本机服务启动连接成功；单窗口关闭后 app 与 backend 均退出且无残留。 |
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或千问应用 API、DeepSeek、OpenRouter 固定路由；本地模型 ID 可配置。选择云端即持续授权后续消息发往该服务商，设置有告知且无逐条弹窗；Keychain、固定目标、L3 拦截、错误脱敏和无自动 fallback 保留。每次发送快照当前 Provider/模型；切换时取消旧客户端流并屏蔽迟到回调，状态栏显示当前及本轮实际路由；用户已实机确认模型间可自由切换、打开 Ollama 后 PAC 本地模型可聊天，本轮 GUI 本机短句也已收到精确回复。Ollama 必须运行且模型已安装。设置页云端披露与只读 Key 状态已实机复核（OpenRouter 已保存，未读 Key），检查后恢复本机来源且未发云请求。新构建设置帮助说明 PAC 服务连接不代表 Ollama 已运行，待随下次启动做 GUI 确认。SSE 注释保活/上游取消自动回归通过（窄回归 22 项）。Ollama 0.40.15 本机直连取消长流后，紧接短请求耗时 46.72 秒（同机默认短请求基线约 2.42 秒）；与 Ollama issue #17131 描述的断流后 runner 槽占用现象相符，根因仍属推断。已调整停止提示：本地说明 Ollama 可能仍在收尾，云端说明 Provider 是否停止未知；Swift 34 项与 Beta build 通过，本机 GUI 停止提示实测通过。仍需确认上游恢复策略及可本地验证的错误路径收尾。Python 全量 193 passed、1 个 APFS-128 disk exhaustion 用例因 OSError 失败。用户反馈千问现可正常聊天；D-005 云预算硬拦截未实现；D-010 Provider 范围为千问应用 API、DeepSeek（中国）、OpenRouter（Global）；Token Plan `sk-sp-` 个人版不直连自建应用。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | IN PROGRESS | 已扩展为受认证 loopback WebSocket 本机实时 ASR：200 ms PCM 帧、有界队列、临时 partial、停止后 final 入草稿；用户曾验证 final、取消、文字生成时打断、录音中 Cmd-Q 清理。GUI 曾在停止时断开 socket、随后的第二次录音报 ASR 忙（partial n=2、停止→final n=0）。根因已查明：`LocalVoiceTranscriber.end_stream()`/`abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，清理再次异常使 WebSocket finally 跳过锁释放。现改为重置底层 recognizer，并在清理异常时仍释放会话锁。真实 Uvicorn + 项目本机 ASR 模型连续 3 轮 PCM 流式识别均收到 partial/final/ended；Python 全量 183 项通过（1 条既有 Starlette/httpx 弃用警告）；Apple URLSessionWebSocketTask + 真实 Uvicorn + 本机 sherpa-onnx 模型 + 固定 PCM WAV 连续 3 轮均收到 partial/final/ended。用户已确认 GUI 实时语音故障修复。启动面板单位错误已定位并修复：秒值遗漏乘以 1,000。用户提供的 20 个启动值换算为 500–700 ms，nearest-rank P95=700 ms，低于 5 秒门槛，启动采样计划已完成；partial 更新 216 次、22 个窗口 P95 摘要最高 41.5 ms；停止→final 21 次 pooled P95 97.9 ms、最大 99.9 ms。三项性能均已满足门槛；D-013 启动 20 个样本计划已完成。模型报告已通过本机 SHA-256 将双语 Zipformer 与 Qwen ONNX 权重精确对应到公开模型 revision；模型训练数据、Qwen 转换代码/工件和随包音频许可仍开放。详见 `beta/macOS-beta-voice.md` 与 `poc/phase0-model-license-review.md`。 |
| B3 | 会话保存与恢复 | DEFERRED | D-003 已决定不保存对话，D-006 确认 V1 不提供备份/恢复，D-007 确认 V1 不设 app 数据库，D-008 确认不支持外接盘活动数据目录；持久化仍不在当前范围。若未来恢复会话保存，须先重开 ADR-019、完成加密/migration/备份及介质决策和验证。 |
| B4 | 千问 Token Plan 扩展接入 | DEFERRED | 个人版条款仅允许经官方支持的编程/智能体工具扩展交互使用，排除本项目自建应用后端。只有取得允许自建应用的官方授权/套餐，或实现受支持工具扩展集成后，才能纳入应用选项。协议、地址和状态见 `beta/qwen-token-plan-integration.md`。 |
| B5 | V1 文件导入及正式发布扩展 | IN PROGRESS | 已实现用户主动选择 TXT/Markdown、本机临时导入、显式移除及仅本机模型上下文；10 MB/UTF-8/普通文件名验证，有界进程内内存，无路径持久化。PDF 仍禁用，待独立验证解析器资源限制后再启用。详见 `docs/beta/file-import.md`。D-014 确认 V1 不提供长期记忆/Embedding，D-015 确认 V1 不提供 app 数据导出；云语音、备份/恢复、自动恢复、完整许可通知和正式签名分发仍延后至对应功能开发/发布前。 |

## 阶段 0 证据状态（已结束；延期项保留原状态）

**Beta 范围阶段 0 收尾评审：PASS（2026-11-09）**。当前已启用本机优先 Beta 路径的证据和回归已核对；原始 §13 全量 POC 仍有 `PARTIAL/OPEN` 项，不宣称全量阶段 0 通过。按 C-007，这些项目在对应能力启用或正式分发前补齐，触发点见追踪矩阵。0A–0H 的历史证据和未闭环项仍见追踪矩阵。2026-11-09 最新本机回归：Python 183 项、Swift 33 项通过，`uv lock --check`、`compileall` 通过；历史 GitHub Actions run `42489738004` 仍只证明旧 commit `51b9ab9`（当时 Python 162、Swift 31）。当前本地提交尚未推送，PR 触发路径未实际运行；最新 Python SBOM 已按 `uv.lock` 重生成并校验 55/55 非根依赖。D-013 Beta GUI 样本已达到计划数量并低于门槛：启动 n=20/P95=700 ms，partial 216 次/各窗口 P95≤41.5 ms，停止→final n=21/P95=97.9 ms。POC-01 并发 probe 新增 13 轮，详见 `phase0-local-asr.md` 与逐轮 CSV；Consent/Policy 新增在途 generate/stream 撤销取消 fake-adapter 回归，窄回归 50 项通过（含同一 Consent 下并发撤销）；完整 Agent/产品负载和 Consent 持久审计仍未验收。其他缺口继续按追踪矩阵逐项关闭，不以延期冒充通过。

## 当前执行顺序

0. **阶段 1 工程底座（DONE，当前决策范围）**：Loopback API trace、统一错误、依赖注入、最小 health、集中配置和可注入进程启动设置均完成；云凭据保存/删除需 Touch ID 或设备密码 gate。Ruff、mypy、secret scan、锁文件、Python/Swift 测试进入 CI。数据库/迁移/会话持久化/静态加密和 metadata-only 30 天审计日志明确未实现，按 D-003/D-007 触发条件延期；因此这不是规格书完整 V1 持久化底座验收。

1. **B0 应用可运行骨架（DONE）**：SwiftUI 单实例窗口的本机 Beta 入口已完成；本机后端启动、健康状态、错误恢复和关窗退出清理均已验证。
2. **B1 本机文字对话和模型设置（IN PROGRESS）**：本机 Ollama/固定云端配置选择；选中云端 Provider 后持续授权，聊天时不弹逐条确认；Keychain 凭据和无自动 fallback。用户与本轮 GUI 均确认 Ollama 正常运行时本机聊天可回复。模型设置云端披露已实机复核，本机提示新文案待下次启动确认。长流取消后 Ollama 短请求明显变慢，疑似上游 runner 槽释放问题；停止提示已如实区分客户端取消与上游状态。需确认可用 Ollama 版本/恢复策略，并完成可本地验证的错误路径和云 API 错误 UI 验收。
3. **B2 本地语音**：接入本机实时 Streaming ASR、明确点击才采集、有限内存/队列、partial/final 草稿边界和按键打断；识别失败不得转云。完整双向语音、AEC、自动插话和系统生命周期仍需阶段 3 决策与验证。
4. **单助理编排框架（IN PROGRESS）**：已把总助理请求、上下文构建和 Model Gateway 流式调用抽为独立 `MainAssistantOrchestrator`；目前仅启用 `main_assistant`，上下文只使用本轮明确消息和用户主动导入的文本资料，不读写持久存储。API 路由保留认证、云授权和 SSE 错误映射。每次流式请求有有界进程内运行状态，可按 run ID 经认证 API 查询；macOS UI 显示短 ID 和状态，并在停止/切换模型后查询终态。新增认证 `/usage` 及有界进程内用量 ledger 和只读用量面板；Gateway 可透传 Ollama 与云端流最终帧的实际 token 数，缺少最终 usage 为 UNKNOWN；OpenRouter 若返回 `usage.cost` 则以 actual USD 记录，其他缺失费用仍 UNKNOWN，不做货币换算或预算拦截。能力注册表已从随包 JSON 精确装配并注入默认 Orchestrator；认证 `/model-capabilities` 查询状态和证据，工具能力有限时标 LIMITED，未收录型号/能力保持 UNKNOWN。当前基本聊天不请求额外能力，不改变路由行为。Python 全量 228 项通过；清单 wheel 内容检查通过；Swift 36 项与 Beta target build 通过。用量面板 GUI 手动冒烟及精确云型号 usage/cost E2E 仍待做；细节见 `docs/beta/orchestrator-framework.md` 和 `docs/beta/file-import.md`。
5. 后续再按用户实际使用反馈决定会话持久化；D-014 确认 V1 不提供长期记忆/Embedding，D-015 确认 V1 不提供 app 数据导出。D-012 文件导入按格式分步启用：TXT/Markdown 本机闭环已实现并待 GUI 冒烟；PDF 在解析器资源限制安全 POC 前保持禁用。备份/恢复按 D-006 不在 V1。B4 千问 Token Plan 文本/实时语音仍须符合个人版条款及 Consent/Policy，不接入自建应用路径。

阶段 1 当前决策允许的无持久化工程底座已完成并有 CI 门禁；预算硬拦截、持久审计、PDF 导入、Embedding、数据库迁移等均明确未实现，按追踪矩阵触发点排期。TXT/Markdown 导入在 B5 增量实现中，不代表完整文件导入验收。完整阶段状态以追踪矩阵 §6 为准。

### 非阻塞问题回修清单

- **B1 / Ollama 取消后紧接请求变慢**：曾观察到一轮长流取消后短请求延迟明显增加；本机版本、模型、时序和上游行为都可能影响结果，当前根因未证实。停止提示已说明本机可能仍在收尾。当前不阻塞聊天主闭环；等框架和核心功能主线完成后，若仍影响正常使用，再按可复现步骤做一次集中排查。
麦克风复现命令（从仓库根目录，在本机交互式终端运行）：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/run_live_microphone_poc.py .poc-data/models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 --seconds 30
```

## 测试版门禁

- 每个可用闭环先做必要的本机验证并记录实际范围；不为未启用的后期能力预先重复验证。
- 涉及敏感数据持久化、远端出站、麦克风采集或正式分发的能力，必须先满足对应安全与授权要求。
- 每个工作包关闭时，更新实现文档、任务状态和 `HANDOFF.md`，列明验证与剩余限制，并提交 Git。
