# 阶段任务清单

最后核对：2026-11-09（Asia/Shanghai）

## 状态和流程

- `DONE`：工作包的明确完成条件已满足，证据可复核。
- `IN PROGRESS`：正在执行，尚有明确完成条件未满足。
- `OPEN`：可继续推进，尚未开始或证据不足。
- `BLOCKED`：依赖产品决定、用户操作、凭据或外部条件；记录解除阻塞所需输入。
- `DEFERRED`：按用户或基线范围暂缓，不作为当前缺陷。

执行顺序：开始前读取根目录 `AGENTS.md`（如存在）、`PROJECT_CONTEXT.md`、`TASKS.md`、`DECISIONS.md`、`HANDOFF.md`；检查 Git 状态；按下面的顺序选取未阻塞任务；实现后执行适用验证、更新 POC 报告与追踪矩阵、更新本清单和交接文档，最后提交 Git。用户已按 C-007 授权先建设单用户 macOS 测试版。阶段 0 仍保留为完整 V1/正式发布证据清单，但不再整体阻塞测试版；延期验证须在对应能力启用或正式分发前补齐。

阶段 0 的原始证据以 [追踪矩阵](poc/phase0-traceability.md) 为准；本清单另行定义当前测试版交付顺序。

## 单用户 macOS 测试版交付队列

| 顺序 | 工作包 | 状态 | 完成条件 / 说明 |
|---:|---|---|---|
| B0 | 应用可运行骨架 | IN PROGRESS | 新增 SwiftUI 测试版 `.app` 构建/启动入口；本轮经启动脚本实机显示本机服务已连接，Cmd-Q 后进程检查未见 app/backend 残留。窗口关闭路径及启动失败恢复体验仍需复核。 |
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或千问应用 API、DeepSeek、OpenRouter 固定路由；本地模型 ID 可配置。选择云端即持续授权后续消息发往该服务商，设置有告知且无逐条弹窗；Keychain、固定目标、L3 拦截、错误脱敏和无自动 fallback 保留。每次发送快照当前 Provider/模型；切换时取消旧客户端流并屏蔽迟到回调，状态栏显示当前及本轮实际路由（已构建，GUI 手动切换/请求冒烟待复核）。此前本机一次千问合成请求结果不明；用户随后反馈千问已可正常聊天（本轮未独立复测）。D-010 仍待决；Token Plan `sk-sp-` 个人版不直连自建应用。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | IN PROGRESS | 已扩展为受认证 loopback WebSocket 本机实时 ASR：200 ms PCM 帧、有界队列、临时 partial、停止后 final 入草稿；文字生成中可点击打断并开始语音输入。补齐锁定的 `websockets` 服务端依赖并重启后，GUI 确认新版本已运行；用户还需复试 partial/final。云 Realtime、AEC/自动声学插话和睡眠/锁屏等仍按阶段 3/ADR-021 处理。手动本机朗读仍保留。详见 `beta/macOS-beta-voice.md`。 |
| B3 | 会话保存与恢复 | DEFERRED | 等待最小数据保留和静态加密决策；在决定前不持久化敏感对话。 |
| B4 | 千问 Token Plan 扩展接入 | DEFERRED | 个人版条款仅允许经官方支持的编程/智能体工具扩展交互使用，排除本项目自建应用后端。只有取得允许自建应用的官方授权/套餐，或实现受支持工具扩展集成后，才能纳入应用选项。协议、地址和状态见 `beta/qwen-token-plan-integration.md`。 |
| B5 | 正式发布与扩展功能 | DEFERRED | 文件导入、Embedding 记忆、云语音、备份/恢复、自动恢复、完整许可通知、正式签名分发在对应功能实现前再补决策和测试。 |

## 阶段 0 证据状态（保留追踪，不作为测试版总门禁）

0A–0H 的历史证据和未闭环项仍见追踪矩阵。GitHub Actions 已在 `main` 上真实成功运行（2026-11-09 复核，run `42489738004`，Python `162 passed`、Swift `31 tests passed`），不再是延期项；PR 触发路径尚未经历。独立标注语料/长时压力、Provider 服务端取消与更广稳定性、云 ASR/TTS、许可闭包、锁屏/休眠、系统卷/断电恢复等仍延期至对应能力开发或正式发布前；不要将其记作已验证。用户已明确识别质量可后续优化，SwiftUI 麦克风/AEC 属原规格阶段 3。

## 当前执行顺序

1. **B0 应用可运行骨架**：基于现有 SwiftUI lifecycle demo，形成开发者可重复启动的单用户 app 入口；本机后端启动、健康状态、错误提示和退出清理纳入该闭环。
2. **B1 本机文字对话和模型设置**：本机 Ollama/固定云端配置选择；选中云端 Provider 后持续授权，聊天时不弹逐条确认；Keychain 凭据和无自动 fallback；完成设置 UI 手动复核及 API Key/错误路径验证。
3. **B2 本地语音**：接入本机实时 Streaming ASR、明确点击才采集、有限内存/队列、partial/final 草稿边界和按键打断；识别失败不得转云。完整双向语音、AEC、自动插话和系统生命周期仍需阶段 3 决策与验证。
4. 后续再按用户实际使用反馈决定会话持久化、记忆、文件导入和备份。B4 千问 Token Plan 文本/实时语音已按用户确认列入候选，但排在本机对话和本地语音基础之后；进入可用路径前按单次 Consent 和对应协议验证。

当前首要实现是 B0/B1 的真实端到端应用体验，不继续扩展与当前测试版无关的 POC 矩阵。
麦克风复现命令（从仓库根目录，在本机交互式终端运行）：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/run_live_microphone_poc.py .poc-data/models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 --seconds 30
```

## 测试版门禁

- 每个可用闭环先做必要的本机验证并记录实际范围；不为未启用的后期能力预先重复验证。
- 涉及敏感数据持久化、远端出站、麦克风采集或正式分发的能力，必须先满足对应安全与授权要求。
- 每个工作包关闭时，更新实现文档、任务状态和 `HANDOFF.md`，列明验证与剩余限制，并提交 Git。
