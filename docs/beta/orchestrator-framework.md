# 单助理编排框架

更新日期：2026-11-09

## 当前结构

`backend/pac_poc/orchestrator.py` 提供一条最小、可替换的对话编排路径：

1. `ConversationTurn` 承载一次请求的消息、Provider、模型和授权元数据；对象只在请求生命周期内存在。
2. `PassThroughContextBuilder` 只使用调用方明确提交的消息和用户主动导入的文本资料，不读取任意路径、数据库或记忆。
3. `MainAssistantOrchestrator` 只接受 `main_assistant`，构造 `LocalModelRequest` 并把流交给项目自有 `ModelGateway`。
4. FastAPI `/chat/stream` 仍负责本机认证、输入大小/L3 检查、云端 Consent/Policy 组合、SSE keep-alive 和面向 UI 的错误映射。
5. `RunRegistry` 为每次对话创建 UUID 和 `CREATED → RUNNING → COMPLETED/FAILED/CANCELLED` 状态；仅保留有界进程内元数据，不记录消息、生成内容或凭据。SSE 响应头 `X-PAC-Run-ID` 和完成事件提供 ID，认证的 `GET /chat/runs/{run_id}` 查询状态。macOS 客户端读取 run ID、正常结束/失败时查询终态，并在用户停止或切换模型后短暂轮询。
6. `ConversationTurn.required_capabilities` 可声明本轮必需能力；Orchestrator 用精确 `(provider, model)` 的 `ModelCapabilityRegistry` 在构造 Gateway 请求前逐项校验。未知、不支持或受限能力均拒绝。现有基础文本流未声明额外能力，所以用户自选的本机模型和既有 Provider 路由不受新证据门槛影响；这是为后续工具、多模态等扩展预置的安全接缝。

这样 Provider、授权和 HTTP 传输不会进入 Orchestrator；后续上下文构造可通过 `ContextBuilder` 替换，编排逻辑也可由 API 之外调用。运行状态查询不代表任务可脱离请求后台继续执行；进程退出会清空状态。此骨架不包含真实 Agent Registry、工具执行、会话保存、长期记忆、费用预算或后台运行。

## 能力报告装配

`ModelCapabilityRegistry.from_json()` 接收 schema version 1 的 JSON manifest，逐项校验字段、能力/状态枚举和精确 `(provider_id, model_id)` 唯一性。每份包含能力声明的报告必须带 `verified_at` 与至少一条 `evidence_refs`；省略的能力保持 `UNKNOWN`，型号名称不会产生推断。错误版本、未知字段、重复报告或没有证据锚点的声明会拒绝装配。

```json
{
  "schema_version": 1,
  "reports": [{
    "provider_id": "local-fixture",
    "model_id": "fixture-v1",
    "entries": [{"capability": "streaming", "state": "supported"}],
    "verified_at": "2026-11-09T00:00:00Z",
    "evidence_refs": ["docs/poc/phase0-model-gateway-local.md"]
  }]
}
```

当前装配 API 是框架入口；运行时仍不从外部文件自动加载能力清单，也没有因此新增已启用能力。只有核对具体报告证据后，才应把构造出的 registry 注入 Orchestrator。

## 验证

在 `backend/` 目录执行：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_beta_api.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/orchestrator.py tests/test_orchestrator.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/orchestrator.py pac_poc/model_capabilities.py
swift test --package-path poc/macos-audio
```

结果：能力清单改动后，以上 Python 命令 43 passed；Ruff 全部通过；mypy 无问题。pytest 有一条既有 Starlette/httpx 弃用警告。Swift 35 项及 Beta target 编译记录见上一轮交接，本轮未改 Swift。未重启 GUI 做手动 run 状态冒烟；未发起云请求、未读取 Keychain、未采集麦克风，也未增加持久化。

## 下一步

- 补齐客户端断连与取消路径的生命周期 GUI 手动冒烟；不提供退出后后台续跑。
- 建立有证据锚点的能力报告装配入口；按已验证的 Provider/model/能力逐步启用，未知项继续默认拒绝。
- 下一步选取具体、已核对证据的 Provider/model 报告接入运行时；工具、多模态和持久化仍须各自完成决策、实现与验证后再启用。
