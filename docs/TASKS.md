# 阶段任务清单

最后核对：2026-11-08（Asia/Shanghai）

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
| B0 | 应用可运行骨架 | IN PROGRESS | 新增 SwiftUI 测试版 `.app` 构建/启动入口；真实启动后显示本机模型已连接，supervisor 管理后端。仍需关闭窗口后确认服务清理，并完善启动失败体验。 |
| B1 | 本机文字对话及模型设置 | IN PROGRESS | GUI 可选本地 Ollama 或固定 DeepSeek/OpenRouter 云路由；本地模型 ID 可配置；云端有 Keychain 保存、完整对话预览、逐请求 Consent、L3 凭据拦截和无自动 fallback。Python 159 项、Swift 31 项通过，GUI Accessibility 树确认设置按钮显示；sheet 实际交互及真实云请求尚未手动验收。D-010 仍待决。详见 `beta/macOS-beta-chat.md`。 |
| B2 | 本地语音闭环 | OPEN | 在应用内显式开始/停止麦克风，连接已验证本地 ASR 和本机 TTS；原始音频不落盘，失败不静默上云。 |
| B3 | 会话保存与恢复 | DEFERRED | 等待最小数据保留和静态加密决策；在决定前不持久化敏感对话。 |
| B4 | 千问文本/实时语音 | DEFERRED | Token Plan 服务端支持文本和 Realtime WebSocket，但个人版条款仅允许在编程/智能体工具内交互使用，排除自建应用后端；因此不把个人版 Key 接入本项目 SwiftUI/FastAPI 测试版。取得适用于自定义应用的 API 凭据后再评估启用。协议、地址和事件见 `beta/qwen-token-plan-integration.md`。 |
| B5 | 正式发布与扩展功能 | DEFERRED | 文件导入、Embedding 记忆、云语音、备份/恢复、自动恢复、完整许可通知、正式签名分发在对应功能实现前再补决策和测试。 |

## 阶段 0 证据状态（保留追踪，不作为测试版总门禁）

0A–0H 的历史证据和未闭环项仍见追踪矩阵。GitHub Actions 实际运行、独立标注语料/长时压力、Provider 服务端取消与更广稳定性、云 ASR/TTS、许可闭包、锁屏/休眠、系统卷/断电恢复等均延期至对应能力开发或正式发布前；不要将其记作已验证。用户已明确识别质量可后续优化，SwiftUI 麦克风/AEC 属原规格阶段 3。

## 当前执行顺序

1. **B0 应用可运行骨架**：基于现有 SwiftUI lifecycle demo，形成开发者可重复启动的单用户 app 入口；本机后端启动、健康状态、错误提示和退出清理纳入该闭环。
2. **B1 本机文字对话和模型设置**：本机 Ollama/已验证固定云端配置选择；云端逐请求内容预览与 Consent、Keychain 凭据和无自动 fallback；完成设置 UI 手动复核及 API Key/错误路径验证。
3. **B2 本地语音**：把已有 ASR、麦克风捕获和 TTS 接入 app；录音只在用户明确开始后采集并留在内存，识别失败不得转云。
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
