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
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或千问应用 API、DeepSeek、OpenRouter 固定路由；本地模型 ID 可配置。选择云端即持续授权后续消息发往该服务商，设置有告知且无逐条弹窗；Keychain、固定目标、L3 拦截、错误脱敏和无自动 fallback 保留。每次发送快照当前 Provider/模型；切换时取消旧客户端流并屏蔽迟到回调，状态栏显示当前及本轮实际路由；用户已实机确认模型间可自由切换，切换后当前聊天使用新选择。用户反馈千问现可正常聊天，旧的一次合成探测失败不再代表当前状态。停止/取消请求 GUI 行为仍需单独复核。D-005 已定自然月 100 元预算/80 元提醒/100 元硬拦截，Beta 尚无费用归一或限额实现，不能作为当前保护承诺；D-010 已确认 V1 Provider 范围为默认千问应用 API、另支持 DeepSeek（中国）与 OpenRouter（Global）；Token Plan `sk-sp-` 个人版不直连自建应用。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | IN PROGRESS | 已扩展为受认证 loopback WebSocket 本机实时 ASR：200 ms PCM 帧、有界队列、临时 partial、停止后 final 入草稿；用户已验证 final、取消、文字生成时打断、录音中 Cmd-Q 清理。快速重复录音 GUI 复测仍报服务 bad response；后端先清理并释放 ASR 锁再发送 `ended`，busy 时现于 WebSocket 握手后返回明确 error 事件；客户端对本机握手最多重试 5 次（200 ms 间隔），Python 全量 177 项通过，GUI 修复效果待用户复测。用户报告 20 次启动值均低于 5 秒，但原范围文本有歧义；partial 与停止→final 分布尚未取得。真实硬件驱动异常仍未复现。D-013 使用 opt-in、仅内存诊断；V1 不做云 Realtime、AEC/自动声学插话或睡眠/锁屏等 ADR-021 排除项。详见 `beta/macOS-beta-voice.md`。 |
| B3 | 会话保存与恢复 | DEFERRED | D-003 已决定不保存对话，D-006 确认 V1 不提供备份/恢复，D-007 确认 V1 不设 app 数据库，D-008 确认不支持外接盘活动数据目录；持久化仍不在当前范围。若未来恢复会话保存，须先重开 ADR-019、完成加密/migration/备份及介质决策和验证。 |
| B4 | 千问 Token Plan 扩展接入 | DEFERRED | 个人版条款仅允许经官方支持的编程/智能体工具扩展交互使用，排除本项目自建应用后端。只有取得允许自建应用的官方授权/套餐，或实现受支持工具扩展集成后，才能纳入应用选项。协议、地址和状态见 `beta/qwen-token-plan-integration.md`。 |
| B5 | V1 文件导入及正式发布扩展 | OPEN | D-012 已确定用户主动只读导入 TXT/Markdown/PDF，每个文件最多 10 MB；尚未实现。启用前须完成 PDF 解析资源限制、文件类型/路径安全 POC。D-014 确认 V1 不提供长期记忆/Embedding，D-015 确认 V1 不提供 app 数据导出；云语音、备份/恢复、自动恢复、完整许可通知和正式签名分发仍延后至对应功能开发/发布前。 |

## 阶段 0 证据状态（保留追踪，不作为测试版总门禁）

0A–0H 的历史证据和未闭环项仍见追踪矩阵。2026-11-09 最新本机回归：Python 176 项、Swift 32 项通过，`uv lock --check`、`compileall` 通过；历史 GitHub Actions run `42489738004` 仍只证明旧 commit `51b9ab9`（当时 Python 162、Swift 31）。当前本地改动尚未推送，PR 触发路径未实际运行；最新 Python SBOM 已按 `uv.lock` 重生成并校验 55/55 非根依赖。D-013 已设启动/ASR 延迟门槛，当前没有 Beta 端到端 P95 证据。其他缺口继续按追踪矩阵逐项关闭，不以延期冒充通过。

## 当前执行顺序

1. **B0 应用可运行骨架**：基于现有 SwiftUI lifecycle demo，形成开发者可重复启动的单用户 app 入口；本机后端启动、健康状态、错误提示和退出清理纳入该闭环。
2. **B1 本机文字对话和模型设置**：本机 Ollama/固定云端配置选择；选中云端 Provider 后持续授权，聊天时不弹逐条确认；Keychain 凭据和无自动 fallback；完成设置 UI 手动复核及 API Key/错误路径验证。
3. **B2 本地语音**：接入本机实时 Streaming ASR、明确点击才采集、有限内存/队列、partial/final 草稿边界和按键打断；识别失败不得转云。完整双向语音、AEC、自动插话和系统生命周期仍需阶段 3 决策与验证。
4. 后续再按用户实际使用反馈决定会话持久化；D-014 确认 V1 不提供长期记忆/Embedding，D-015 确认 V1 不提供 app 数据导出。文件导入已由 D-012 纳入 V1 范围（TXT/Markdown/PDF，10 MB），需先通过安全 POC 再启用。备份/恢复按 D-006 不在 V1。B4 千问 Token Plan 文本/实时语音仍须符合个人版条款及 Consent/Policy，不接入自建应用路径。

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
