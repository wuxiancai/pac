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

阶段 0 不再以完整 V1/发布证据清单阻塞当前 Beta。按 C-007，目标是在 1–2 个集中工作轮次内完成“Beta 范围阶段 0 收尾评审”：重跑当前 Python/Swift 回归，复核已启用的文字/模型切换/本机语音/Consent 安全路径，并为每个不属于当前 Beta 的残余项写明具体延期触发条件。该评审不把延期项改成 PASS；原始 §13 全量 POC 的外部证据在相关功能启用或正式分发前继续追踪。详细收尾标准见 [阶段 0 追踪矩阵](poc/phase0-traceability.md)。

## 单用户 macOS 测试版交付队列

| 顺序 | 工作包 | 状态 | 完成条件 / 说明 |
|---:|---|---|---|
| B0 | 应用可运行骨架 | IN PROGRESS | 新增 SwiftUI 测试版 `.app` 构建/启动入口；本轮经启动脚本实机显示本机服务已连接，Cmd-Q 后进程检查未见 app/backend 残留。窗口关闭路径及启动失败恢复体验仍需复核。 |
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或千问应用 API、DeepSeek、OpenRouter 固定路由；本地模型 ID 可配置。选择云端即持续授权后续消息发往该服务商，设置有告知且无逐条弹窗；Keychain、固定目标、L3 拦截、错误脱敏和无自动 fallback 保留。每次发送快照当前 Provider/模型；切换时取消旧客户端流并屏蔽迟到回调，状态栏显示当前及本轮实际路由；用户已实机确认模型间可自由切换，切换后当前聊天使用新选择。用户反馈千问现可正常聊天，旧的一次合成探测失败不再代表当前状态。停止/取消请求 GUI 行为仍需单独复核。D-005 已定自然月 100 元预算/80 元提醒/100 元硬拦截，Beta 尚无费用归一或限额实现，不能作为当前保护承诺；D-010 已确认 V1 Provider 范围为默认千问应用 API、另支持 DeepSeek（中国）与 OpenRouter（Global）；Token Plan `sk-sp-` 个人版不直连自建应用。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | IN PROGRESS | 已扩展为受认证 loopback WebSocket 本机实时 ASR：200 ms PCM 帧、有界队列、临时 partial、停止后 final 入草稿；用户曾验证 final、取消、文字生成时打断、录音中 Cmd-Q 清理。GUI 曾在停止时断开 socket、随后的第二次录音报 ASR 忙（partial n=2、停止→final n=0）。根因已查明：`LocalVoiceTranscriber.end_stream()`/`abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，清理再次异常使 WebSocket finally 跳过锁释放。现改为重置底层 recognizer，并在清理异常时仍释放会话锁。真实 Uvicorn + 项目本机 ASR 模型连续 3 轮 PCM 流式识别均收到 partial/final/ended；Python 全量 183 项通过（1 条既有 Starlette/httpx 弃用警告）；Apple URLSessionWebSocketTask + 真实 Uvicorn + 本机 sherpa-onnx 模型 + 固定 PCM WAV 连续 3 轮均收到 partial/final/ended。用户已确认 GUI 实时语音故障修复。启动面板单位错误已定位并修复：秒值遗漏乘以 1,000。用户提供的 20 个启动值换算为 500–700 ms，nearest-rank P95=700 ms，低于 5 秒门槛，启动采样计划已完成；partial 更新 216 次、22 个窗口 P95 摘要最高 41.5 ms；停止→final 21 次 pooled P95 97.9 ms、最大 99.9 ms。三项性能均已满足门槛；D-013 启动 20 个样本计划已完成。模型报告已通过本机 SHA-256 将双语 Zipformer 与 Qwen ONNX 权重精确对应到公开模型 revision；模型训练数据、Qwen 转换代码/工件和随包音频许可仍开放。详见 `beta/macOS-beta-voice.md` 与 `poc/phase0-model-license-review.md`。 |
| B3 | 会话保存与恢复 | DEFERRED | D-003 已决定不保存对话，D-006 确认 V1 不提供备份/恢复，D-007 确认 V1 不设 app 数据库，D-008 确认不支持外接盘活动数据目录；持久化仍不在当前范围。若未来恢复会话保存，须先重开 ADR-019、完成加密/migration/备份及介质决策和验证。 |
| B4 | 千问 Token Plan 扩展接入 | DEFERRED | 个人版条款仅允许经官方支持的编程/智能体工具扩展交互使用，排除本项目自建应用后端。只有取得允许自建应用的官方授权/套餐，或实现受支持工具扩展集成后，才能纳入应用选项。协议、地址和状态见 `beta/qwen-token-plan-integration.md`。 |
| B5 | V1 文件导入及正式发布扩展 | OPEN | D-012 已确定用户主动只读导入 TXT/Markdown/PDF，每个文件最多 10 MB；尚未实现。启用前须完成 PDF 解析资源限制、文件类型/路径安全 POC。D-014 确认 V1 不提供长期记忆/Embedding，D-015 确认 V1 不提供 app 数据导出；云语音、备份/恢复、自动恢复、完整许可通知和正式签名分发仍延后至对应功能开发/发布前。 |

## 阶段 0 证据状态（保留追踪，不作为测试版总门禁）

0A–0H 的历史证据和未闭环项仍见追踪矩阵。2026-11-09 最新本机回归：Python 183 项、Swift 33 项通过，`uv lock --check`、`compileall` 通过；历史 GitHub Actions run `42489738004` 仍只证明旧 commit `51b9ab9`（当时 Python 162、Swift 31）。当前本地改动尚未推送，PR 触发路径未实际运行；最新 Python SBOM 已按 `uv.lock` 重生成并校验 55/55 非根依赖。D-013 Beta GUI 样本已达到计划数量并低于门槛：启动 n=20/P95=700 ms，partial 216 次/各窗口 P95≤41.5 ms，停止→final n=21/P95=97.9 ms。POC-01 并发 probe 新增 13 轮，详见 `phase0-local-asr.md` 与逐轮 CSV；Consent/Policy 新增在途 generate/stream 撤销取消 fake-adapter 回归，窄回归 50 项通过（含同一 Consent 下并发撤销）；完整 Agent/产品负载和 Consent 持久审计仍未验收。其他缺口继续按追踪矩阵逐项关闭，不以延期冒充通过。

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
