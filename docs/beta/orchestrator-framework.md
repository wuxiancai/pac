# 单助理编排框架

更新日期：2026-11-09

## 当前结构

`backend/pac_poc/orchestrator.py` 提供一条最小、可替换的对话编排路径：

1. `ConversationTurn` 承载一次请求的消息、Provider、模型和授权元数据；对象只在请求生命周期内存在。
2. `PassThroughContextBuilder` 只复制调用方明确提交的消息，不读取文件、数据库或记忆。
3. `MainAssistantOrchestrator` 只接受 `main_assistant`，构造 `LocalModelRequest` 并把流交给项目自有 `ModelGateway`。
4. FastAPI `/chat/stream` 仍负责本机认证、输入大小/L3 检查、云端 Consent/Policy 组合、SSE keep-alive 和面向 UI 的错误映射。

这样 Provider、授权和 HTTP 传输不会进入 Orchestrator；后续上下文构造可通过 `ContextBuilder` 替换，编排逻辑也可由 API 之外调用。此骨架不包含真实 Agent Registry、工具执行、会话保存、长期记忆、费用预算或后台运行。

## 验证

在 `backend/` 目录执行：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_orchestrator.py tests/test_beta_api.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/orchestrator.py pac_poc/beta_api.py tests/test_orchestrator.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/orchestrator.py pac_poc/beta_api.py
```

结果：24 passed；Ruff 全部通过；mypy 无问题。pytest 有一条既有 Starlette/httpx 弃用警告。未发起云请求、未读取 Keychain、未采集麦克风，也未增加持久化。

## 下一步

- 给一次请求增加明确的运行状态/取消边界，并确保断连时状态能被观察，但不做退出后后台续跑。
- 将模型能力验证接到总助理绑定处；不支持的能力在调用 Provider 前明确拒绝。
- 只有在产品明确启用相应功能后，再增加工具、文件上下文或持久化实现。
