# 项目上下文

最后核对：2026-11-08（Asia/Shanghai）

## 项目目标

依据 [个人 AI 助理开发规格 v1.2](../个人AI助理可执行开发规格书%20v1.2.md)，建设本机优先的个人 AI 助理。当前处于阶段 0：验证关键技术路径和工程基线；阶段 0 未验收前，不进入阶段 1 的完整产品实现。

## 当前状态

- 当前阶段：阶段 0 POC，未验收；阶段 1 未开始。
- 实现形态：macOS SwiftUI 客户端 + 本机 Python/FastAPI 服务；仓库内各工作包的当前状态和证据见 [阶段 0 追踪矩阵](poc/phase0-traceability.md)。
- 本机语音：中文 Streaming ASR、麦克风捕获 CLI、TTS 打断已有 POC 和部分实测；用户提供的 Qwen3-ASR 0.6B INT8 ONNX 已完成随包中/英离线评估。另下载 sherpa-onnx 官方中英双语 Streaming Zipformer，10 条合成音频均产生 final；用户三次实机运行 CLI 均观察到 partial/final；5 条中英/混说 manifest 合成 WAV 的本机 ASR-final→AVSpeechSynthesizer 链路共 7/7 完成；另一次麦克风未打开时验证 Ctrl-C 可停止；自动回归模拟覆盖 ASR 解码异常、PortAudio 启动失败和 callback status 错误时的流/缓冲清理，真实设备驱动故障仍未测。用户指定当前真人语音目标为功能冒烟，模型识别质量后续再优化；中英 Streaming Zipformer 仓库声明 Apache-2.0，但上游来源标识和训练数据权利链尚未核清；ASR+LLM 有四轮同一合成样本并发观察，独立语料/多负载资源结果未覆盖；SwiftUI 麦克风/AEC 属规格书阶段 3，当前不列为阶段 0 阻塞；详情见 `docs/poc/phase0-local-asr.md`。
- SwiftUI 安全客户端：显式系统认证测试按钮已在真实 demo 窗口两次成功验证、一次用户取消验证，均确认未访问钥匙串；UI 按 LocalAuthentication 错误码区分用户取消和系统中断；GUI 后端启停另经两轮复测且无重复子进程。
- Gateway、安全、记忆、Embedding、SQLCipher 和后端生命周期均有 POC；MemoryStore 显式注入固定 Embedding 权重的严格离线合成检索最新为 4/4 top-1。它们不等同于产品功能验收。详情按需查阅 [`docs/poc/`](poc/)。
- 根目录现有 `README.md`、`AGENTS.md` 和 `.github/workflows/ci.yml`；2026-11-08 本机 CI 等价全量验证通过（Python 153 项、Swift 31 项、Python compileall、`uv lock --check`），GitHub Actions 尚未执行（当前仓库无 remote）。D-001–D-015 与 ADR-019/020/021/022 按用户 2026-11-08 指示延期；延期不豁免阶段验收证据。
- 每次工作的 Git 基线以 `git log -1` 为准；工作开始前先检查 `git status`，保护已有改动。

## 架构和安全边界

- UI 通过本机 Loopback API 与后端通信；服务由 Swift supervisor 固定启动，不经任意 shell 命令。
- Model Gateway 使用 Adapter 和精确 Provider/Model capability registry；未知能力默认不支持。
- 本地优先。远端模型调用必须在发送前通过 Consent Manager 与 Policy Engine；默认拒绝；凭据来自 Keychain。不得以 fallback 扩大授权。阶段 0 已加入 DeepSeek 与 OpenRouter 固定端点 adapter 和逐请求终端确认；两家各有用户确认后的合成文本真实请求成功记录，同一 Gateway 顺序跨 Provider 路由已真实通过一次；逐项能力探测脚本已就绪，所有后续出站仍需逐次主动确认；远端 HTTP 401 会提示凭据认证失败，Keychain 缺失与认证拒绝分开提示，错误响应正文不保留。无 Consent 的真实 HTTPX 检查在两家均于 Adapter 前拒绝、credential reads=0，PID 级 `lsof` 观察无活动网络 socket；全系统包捕获的 TCP/443 流量因未按进程过滤不作归因。
- Agent Registry 当前为模拟 POC；权限不得超出父权限，不实现 Agent 团队或任意执行器。
- 记忆 POC 使用 disposable 内存 SQLite/FTS5；Embedding 显式 opt-in。不得把 POC schema 当作产品 schema。
- ASR、TTS、LLM 分开配置；原始音频默认不持久化；本地 ASR 失败不得静默切到云端。
- 规格限制的 V1 范围不包括后台任务、外部写操作、跨设备或多用户能力。

## 记录规则

- 稳定事实和架构边界写在本文件；产品或架构取舍写在 [DECISIONS.md](DECISIONS.md)；当前状态、负责人和验收条件写在 [TASKS.md](TASKS.md)；每次交接摘要写在 [HANDOFF.md](HANDOFF.md)。
- 阶段验收的详细证据以 `docs/poc/phase0-traceability.md` 及其链接的 POC 报告为准。避免在多个文档复制长篇测试结果。
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
