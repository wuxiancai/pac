# 项目上下文

最后核对：2026-11-09（Asia/Shanghai）

## 项目目标

依据 [个人 AI 助理开发规格 v1.2](../个人AI助理可执行开发规格书%20v1.2.md)，建设本机优先的个人 AI 助理。当前按 C-007 建设单用户 macOS 测试版。阶段 0 的未完成验证按功能启用或正式发布需要逐项补齐，不再整体阻塞测试版核心闭环。

## 当前状态

- 阶段状态（2026-11-09）：阶段 0 的 Beta 范围已结束，附带明确的未实现/延期清单；原始 §13 全量 POC 仍有 `PARTIAL/OPEN`，不宣称全量验收。阶段 1 当前决策允许的无持久化工程底座已完成并接入 CI lint/type/test/secret-scan 门禁。Loopback API 已有 trace、统一错误、依赖注入、最小 health、可注入启动设置和集中校验配置；云凭据写入/删除需通过 Touch ID 或设备密码。数据库、schema/migration、会话持久化、静态加密、预算硬拦截、PDF 导入及 30 天持久安全审计明确未实现；TXT/Markdown 导入由 B5 增量实现，完整文件导入未完成。触发条件见 `docs/poc/phase0-traceability.md` 和 `docs/TASKS.md`。
- 阶段路线：规格书共 7 阶段（0–6）；当前继续推进阶段 2 的对话/Gateway/Usage 主线。阶段 3 实时语音及阶段 4 文件导入均已有部分能力提前进入 Beta，但各自阶段验收仍未完成。各阶段范围见 `docs/TASKS.md` 与规格书 §13。
- 最新开发检查点（2026-11-09）：阶段 4 B5 新增独立、默认关闭的 PDF 安全解析 POC；后端全量测试为 233 passed、1 条既有 Starlette/httpx 弃用警告。B1 新增 Swift 客户端 HTTP 503 正文脱敏测试；Swift 37 项通过，Beta build 通过。macOS `RLIMIT_AS/DATA/RSS` 有限内存限制尝试失败，PDF 因缺少硬内存和攻击样本压力证据仍保持禁用。阶段 2 仍是当前主线；继续处理 GUI 错误路径和 B5 文本导入 GUI 冒烟等可在现有授权内完成的闭环。

- 2026-11-08 模型设置更新：SwiftUI 聊天页增加本地/云端选择，默认本机 Ollama；云端默认千问按量计费应用 API（`qwen3.8-flash`、`sk-ws-`、Keychain account `qwen-app`），另有 DeepSeek/OpenRouter 路由。选择云 Provider 即持续授权后续聊天发送到该服务商，不再逐条弹窗；设置文案披露此行为，Key 存 login Keychain，L3 凭据在后端出站前拒绝。千问 Token Plan 个人版 `sk-sp-` 官方条款明确排除自建应用后端，未接入直连 Provider；本会话一次千问合成请求返回通用错误且未重试，用户随后反馈已可正常聊天；未在本地记录该次成功响应/usage。详见 `docs/beta/macOS-beta-chat.md` 和 `docs/beta/qwen-token-plan-integration.md`。
- 当前目标：单用户 macOS 本机优先测试版；POC 证据仍标为 POC，阶段 0 完整 V1/正式发布验收未完成。SwiftUI Beta、受认证的本机 `/chat/stream`、Ollama 增量对话和 Provider/模型切换已实现；GUI 发消息/显示回复、模型切换与语音冒烟已由用户实机复核，详情见 `docs/beta/macOS-beta-chat.md`、`docs/beta/macOS-beta-voice.md`。生成请求使用 request ID 隔离回调；对话不持久化。B2 现为显式点击采集、本机实时 ASR、partial/final 草稿和手动 AVSpeechSynthesizer 朗读；用户实机验证 final、取消、点击打断和录音中 Cmd-Q 退出清理。延期能力保持清晰扩展边界，不宣称已通过验证。
- 对话主干已增加独立 `MainAssistantOrchestrator` / `ContextBuilder`、有界进程内 `RunRegistry`、精确型号能力门和随包静态 capability manifest、认证 Usage API 和有界进程内 UsageLedger，以及用户主动 TXT/Markdown 文件导入。认证 `/model-capabilities` 返回型号报告和证据；未登记型号及缺省能力为 UNKNOWN，证据有限的工具状态为 LIMITED。macOS Beta 已提供认证只读用量面板；Gateway 可透传 Ollama 与云 Provider 流最终帧中的实际 token 数，未收到时明确为 UNKNOWN。OpenRouter 若报告 `usage.cost` 则原样记为实际 USD；其他供应商缺失费用仍为 UNKNOWN。没有 USD/CNY 换算或预算拦截；精确云型号真实 usage/cost 尚未实测。导入内容只留本机进程内存，可移除，只用于本机模型并按不可信资料加入上下文；PDF 保持禁用直至解析资源限制验证完成。当前只路由 `main_assistant`，run 状态可经认证 API 查询，macOS UI 显示短 ID 和状态，记录不含对话正文且不跨进程保存；后续主线优先推进，不影响闭环的小问题先登记回修，具体规则见根目录 `AGENTS.md` 与 `docs/TASKS.md`。
- B0 已完成（2026-11-09）：主界面采用 SwiftUI 单实例 `Window`，关闭窗口即退出应用；启动失败分类提示/GUI 重试、真实本机服务启动和关窗后 app/backend 无残留均已复核。supervisor 的 start/stop/isRunning 由生命周期锁串行化，启动期间停止的回归通过。
- B1 本机依赖（2026-11-09）：PAC 本地聊天通过 Ollama 提供模型服务，Ollama 需在本机运行且选择的模型已安装；用户及本轮 GUI 均确认短句可正常返回。Ollama 0.40.15 本机直连接受控取消长流后，下一短请求延迟 46.72 秒；与 Ollama 上游断连占用 runner 槽报告相符，因果尚未完全确认。PAC 停止提示已说明 Ollama 可能仍在结束旧生成；新设置帮助会明确 PAC 后端与 Ollama 分开运行。详见 `docs/beta/macOS-beta-chat.md`。
- 实现形态：macOS SwiftUI 客户端 + 本机 Python/FastAPI 服务；仓库内各工作包的当前状态和证据见 [阶段 0 追踪矩阵](poc/phase0-traceability.md)。
- 本机语音：中文 Streaming ASR、麦克风捕获 CLI、TTS 打断已有 POC 和部分实测；用户提供的 Qwen3-ASR 0.6B INT8 ONNX 已完成随包中/英离线评估。官方中英双语 Streaming Zipformer 的 10 条合成音频均产生 final；用户三次实机运行 CLI 均观察到 partial/final；5 条中英/混说 manifest 合成 WAV 的本机 ASR-final→AVSpeechSynthesizer 链路共 7/7 完成。Beta 已接入 200 ms loopback WebSocket 实时本机 ASR、临时 partial/final 草稿和文字生成中的点击打断；用户验证停止后 final 入草稿、取消清空 partial、点击打断生成及录音中 Cmd-Q 清理。最新 GUI 故障的根因已通过本机 ASR 离线复现：`LocalVoiceTranscriber.end_stream()` 与 `abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，清理再次抛 `AttributeError` 并导致 WebSocket finally 跳过锁释放。现调用底层 recognizer reset，且 finally 保证释放锁。真实 Uvicorn + 本机 ASR 模型和 Apple URLSessionWebSocketTask + sherpa-onnx + PCM WAV 连续 3 轮均完成 partial/final/ended；Python 全量 183 项通过；用户现已确认 GUI 故障修复。D-013 启动面板单位错误已定位并修复：秒值遗漏乘以 1,000，显示仍标为毫秒。用户提供 20 个启动值，范围 500–700 ms、nearest-rank P95=700 ms，低于 5 秒门槛且启动样本计划已完成；partial 216 次、22 个窗口 n=7/9/10，各窗口 P95 最高 41.5 ms；停止→final 21 次 pooled P95=97.9 ms、最大 99.9 ms，均低于各自门槛。云 Realtime、AEC/自动声学插话和锁屏/休眠仍未实现，ADR-021 已 Accepted。用户指定当前真人语音目标为功能冒烟，模型识别质量后续再优化；本机双语 Zipformer 与 Qwen ONNX 权重 SHA-256 已分别匹配公开固定模型 revision，但训练数据、Qwen 转换工件和随包音频许可仍待核；详见 `docs/poc/phase0-local-asr.md` 与 `docs/beta/macOS-beta-voice.md`。
- 阶段 1 最终复核（2026-11-09，`5f6fe24`）：Python 全量 192 passed（1 条既有 Starlette/httpx 弃用警告），Swift 33 passed；Beta build、Ruff、mypy、`compileall`、`uv lock --check`、tracked-file secret scan 通过。该提交尚未运行远端 CI。
- SwiftUI 安全客户端：显式系统认证测试按钮已在真实 demo 窗口两次成功验证、一次用户取消验证，均确认未访问钥匙串；UI 按 LocalAuthentication 错误码区分用户取消和系统中断；GUI 后端启停另经两轮复测且无重复子进程。
- Gateway、安全、记忆、Embedding、SQLCipher 和后端生命周期均有 POC；MemoryStore 显式注入固定 Embedding 权重的严格离线合成检索最新为 4/4 top-1。它们不等同于产品功能验收。详情按需查阅 [`docs/poc/`](poc/)。
- 0G 许可审查现覆盖当前 macOS Python arm64 wheel：Pillow 自带 SBOM 包含 GPL/LGPL 组件，SQLCipher/PortAudio/sherpa 内嵌 ONNX Runtime 有独立许可或 notices。实际产品安装依赖未定，模型工件及完整发行通知闭包仍开放，详见 `docs/poc/phase0-model-license-review.md`。
- 根目录现有 `README.md`、`AGENTS.md` 和 `.github/workflows/ci.yml`；2026-11-09 本轮 Python 全量 183 项通过（1 条既有 Starlette/httpx 弃用警告）；Swift 33 项在本轮收尾复核通过，`compileall` 与 `uv lock --check` 本轮通过。GitHub Actions 历史 `Phase 0 checks` run `42489738004` 在 `main` commit `51b9ab9` 成功（当时 Python 162、Swift 31）；当前分支提交尚未运行远端 PR CI；本地全量 Python/Swift 回归已在收尾复核通过。Python CycloneDX SBOM 已按最新锁文件重生成并验证 55 个非根依赖匹配；许可线索清单已包含 `websockets==17.4`，最终发行物审计仍未完成。D-001–D-015 已由用户逐项确认或限定后续决策触发时机：V1 不保存对话/不做备份、不设 app 数据库、不支持外接盘活动数据目录、不提供长期记忆/Embedding 或 app 数据导出；其余范围和阈值见 `DECISIONS.md`。ADR-019 仍 Deferred（持久化前重开），ADR-020 已 Accepted 为项目自有轻量 Gateway，ADR-021 已 Accepted 为本机点击触发实时 ASR/点击打断、不做 AEC/自动声学插话/云 Realtime，ADR-022 已 Accepted。阶段 0 的 Beta 范围收尾评审于 2026-11-09 通过；原始 §13 全量 POC 仍保留 PARTIAL/OPEN。D-013 Beta GUI 采样三项均低于门槛；ASR+本机 Ollama 并发 probe 已扩至 20 轮（新增 13 轮），但不是完整 Agent 或产品负载验收；远端 CI、macOS 14 实机、硬件音频与许可/发布等证据仍按追踪矩阵未关闭项处理。
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
