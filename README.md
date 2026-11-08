# Personal AI Assistant — macOS Beta

本仓库从技术 POC 转入单用户 macOS 测试版开发（决策 C-007）。阶段 0 的未闭环验证仍保留在追踪矩阵中，按功能启用或正式发布需要补齐；它们不再整体阻塞测试版核心闭环。POC 结果不构成产品承诺。

## 项目文档

- [项目上下文](docs/PROJECT_CONTEXT.md)：目标、架构边界和文档规则。
- [任务清单](docs/TASKS.md)：工作包状态、完成条件和下一步。
- [决策记录](docs/DECISIONS.md)：已确认边界与待决产品事项。
- [交接记录](docs/HANDOFF.md)：最近完成内容和接续点。
- [阶段 0 追踪矩阵](docs/poc/phase0-traceability.md)：验收要求、证据、缺口和风险。
- [千问 Token Plan 接入备忘](docs/beta/qwen-token-plan-integration.md)：文本与实时语音地址、协议、Key 边界、状态和后续步骤。
- [POC 报告](docs/poc/)：按工作包记录实现与验证。

开始改动前先读取 `AGENTS.md` 和上述项目文档，并检查 `git status`。

## 目录

- `backend/`：Python/FastAPI 本机后端与阶段 0 POC。
- `poc/macos-audio/`：Swift 包，包含音频控制、Loopback 客户端和后端生命周期 POC。
- `docs/`：追踪矩阵、工作包证据、决策和任务进度。
- `个人AI助理可执行开发规格书 v1.2.md`：产品开发基线。

## 本机开发与验证

Python（在 `backend/`）：

```bash
uv sync --locked --extra phase0-security --extra phase0-embedding --group dev
uv run --locked pytest -q
uv run --locked python -m compileall -q pac_poc scripts tests
```

Swift（在 `poc/macos-audio/`）：

```bash
swift test
```

上述命令不下载 ASR/Embedding 权重、不调用远端 Provider，也不采集麦克风。需要模型的本机 POC 请按对应 `docs/poc/` 报告执行；音频采集只在用户明确操作后开始。

## 启动 macOS 测试版

当前测试版先提供本机文字对话，使用已安装的 Ollama `qwen3.5:0.8b`；对话不会保存到磁盘。首次启动前需在 `backend/` 执行 `uv sync --locked`，并确认 Ollama 服务和模型已就绪。

```bash
./poc/macos-audio/scripts/run_beta_app.sh
```

测试版在窗口视图消失时会调用清理逻辑停止由应用管理的本机后端（`onDisappear` → `supervisor.stop()`）；关闭窗口后是否确定无残留后端进程仍待实机冒烟确认，见 `docs/beta/macOS-beta-chat.md`。该脚本依赖当前仓库环境，不是独立安装包。

## CI

`.github/workflows/ci.yml` 在 GitHub Actions 的 macOS arm64 runner 上运行锁定依赖的 Python 全量测试、编译检查和 Swift 测试。它只使用仓库依赖，不注入 Provider 密钥，不下载模型，不启动麦克风。

该 workflow 已在 `main` 分支上由 push 真实触发并成功通过（最近一次对应 commit `51b9ab9`，日志记录 Python `162 passed`、Swift `31 tests passed`）。PR 触发路径尚未实际经历。
