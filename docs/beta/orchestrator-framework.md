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

Beta 运行时现从随包的 `pac_poc/beta_model_capabilities.json` 装配默认 registry 并注入 Orchestrator。清单只收录已有本地证据锚点的精确型号：`ollama/qwen3.5:0.8b`、`deepseek/deepseek-flash` 和 `openrouter/deepseek/deepseek-v4.1-flash-1017`。文本生成与流式状态有对应报告；工具能力因样本有限标为 `limited`，不会通过支持门。千问应用 API 型号未有成功的本产品请求证据，因此仍为 `UNKNOWN`。

认证 `GET /model-capabilities?provider_id=...&model_id=...` 返回报告证据引用及全部能力状态；未收录型号或省略能力都返回 `unknown`。该查询不发模型请求。当前聊天不声明额外工具/多模态能力，因此加载清单没有改变基本文本流行为。静态 JSON 已作为 Python package data，并通过 wheel 内容检查确认随包。

## 进程内 Usage 首段

聊天 run 结束时，`UsageLedger` 保存最近最多 512 条请求 metadata，认证 `GET /usage?limit=50` 可读取（limit 最大 100）。记录含 run/provider/model/region/purpose/data level、生命周期状态、wall latency，以及 Provider 明确报告的 token/cache/cost metadata；不含消息、回复、密钥或音频，进程退出即清空。Gateway 已把 Ollama 与 OpenAI-compatible 流最终帧中实际返回的 token 计数交给 ledger；OpenRouter 若返回经校验的 `usage.cost`，则记录其实际 USD 金额。未返回或不完整的 usage/cost 仍为 `unknown`/`null`。这不是完整费用账单或预算保护：精确 Beta 型号真实 usage/cost E2E、其他 Provider 费用来源及人民币归一尚未完成；D-005 月额度拦截当前未实现。

Ledger 在写入时拒绝非有限时间戳、布尔/非整数毫秒延迟，以及负数、布尔或非有限音频时长，避免无效数值进入 `/usage` JSON 响应；未知音频时长仍以 `null` 表示。

macOS Beta 的“用量”面板已接入此只读接口，显示最近记录的 Provider/model、region、状态、耗时，以及实际/估算/未知 token 和费用。当前没有真实 token/费用时明确显示为未知，不作推算。面板查询只访问认证 loopback API，不发起模型请求；数据显示依赖当前进程内 ledger，退出后消失。

### 流式 token 与 OpenRouter 费用透传（2026-11-09）

- `ProviderStreamChunk` 在 Gateway 内携带可选文本增量和 Provider 返回的 prompt/completion token 计数；SSE 客户端仍只收到文本增量。Ollama 完成帧的 `prompt_eval_count`/`eval_count` 和 OpenAI-compatible Provider 最终 usage 帧可进入 `UsageLedger`。
- Gateway 现也保留 Provider 报告的缓存命中输入 token：DeepSeek 使用 `usage.prompt_cache_hit_tokens`；Qwen/OpenAI-compatible 用法读取 `usage.prompt_tokens_details.cached_tokens`，校验它不超过 prompt 总 token 后再写入 bounded ledger，并显示在 macOS 用量面板。Qwen 官方说明此字段表示输入缓存命中 token；DeepSeek 官方 usage 分别提供 cache hit/miss token。当前这是原始用量明细，不据此推算费用。
- 对云端流请求附加 `stream_options.include_usage=true`。DeepSeek 官方 Chat Completions API 文档说明 SSE 最后一帧带整次请求 usage；阿里云 Model Studio 文档说明 Qwen OpenAI-compatible streaming 可用此选项返回最终 token usage；OpenRouter API/SDK 文档列出 `stream_options.include_usage`。这些是协议文档依据，不等于 Beta 当前精确型号的真实 usage 实测：未发云请求、未读取 Keychain。
- OpenRouter 最终 `usage.cost` 如为有限、非负数值，按 OpenRouter 报告的 USD 标记为 actual 并记账；[Chat Completions 文档](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion) 在 `usage` schema 列出 `cost`，OpenRouter [支持说明](https://openrouter.ai/support)说明费用依据 Provider 使用量计算。mock 回归覆盖了流最终帧。当前固定 Beta 型号尚未做真实流式费用 E2E；DeepSeek/Qwen 没有经核实的实际费用流字段，因此继续 unknown/null。
- 只有收到非负整数 Provider token 字段才标为 `actual`。中断、缺少最终 usage 或字段不完整时仍是 `unknown`；不从字符长度估 token。费用仅在 OpenRouter 返回已核验的实际 USD 字段时标为 `actual`；其他缺失值保持 `unknown/null`，不依据 token 或价目表估算、不做 USD/CNY 换算，D-005 预算门保持未实现。

#### D-005 计费输入研究（公开官方资料，2026-11-09）

- Qwen `qwen3.8-flash` 官方模型页公布北京价目及 cache-hit 单价；页面同时提示价格为原价、不含活动优惠。Model Studio 字段文档将 OpenAI Chat compatible 的 `usage.prompt_tokens_details.cached_tokens` 定义为缓存命中输入 token。见[模型信息与价目表](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、[缓存/用量字段说明](https://help.aliyun.com/en/model-studio/ptu-long-input-and-cache)。
- DeepSeek 官方价目把输入分为 cache hit/miss，并按峰谷时段区别价格；API usage 文档分别给出 `prompt_cache_hit_tokens` 和 `prompt_cache_miss_tokens`。本 Gateway 现保留 hit 数，但仍缺供应商真实 stream 验证及可依据模型、时段和账户口径归一费用的完整信息。见[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)和[缓存命中字段](https://api-docs.deepseek.com/guides/kv_cache/)。
- OpenRouter 返回值中的 cost 以 USD 记录；其官方说明模型推理成本按 Provider 价格透传，购买 credits 时另收平台费，可能另有支付处理费用。故 `usage.cost` 不必然等同用户信用卡/支付宝最终人民币支出。见[OpenRouter 用量与费用说明](https://openrouter.ai/support)。
- 上述公开价目会变化，且缓存/时段/活动/下游路由和充值费用口径不同。它们能支持后续设计估算或上界规则，但不足以当前实现“实扣费用”人民币累加。D-005 仍需确定价目版本/更新、USD→CNY 口径、未知字段拦截、额度跨进程保存及并发/月界事务策略，再进入预算 enforcement；未完成前保持 unknown，不拦截或宣称预算保护。

## 验证

在 `backend/` 目录执行：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_usage.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_beta_api.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/usage.py pac_poc/orchestrator.py pac_poc/model_capabilities.py tests/test_usage.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_beta_api.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/usage.py pac_poc/beta_api.py pac_poc/orchestrator.py pac_poc/model_capabilities.py
swift test --package-path poc/macos-audio
```

结果（2026-11-09）：ASGI 层 HTTP 断连回归验证请求断开会关闭上游异步流、run 状态变为 `CANCELLED`，认证 run 查询与 UsageLedger 均返回该终态。另新增 DeepSeek cache-hit 字段解析及 ledger/UI 透传，Qwen/OpenAI-compatible `cached_tokens` 解析、异常计数拒绝及 Swift Codable 覆盖。后端定向回归 8 passed，Ruff 与相关模块 mypy 通过；后端全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 242 passed，1 条既有 Starlette/httpx 弃用警告。Swift 全量 `swift test --package-path poc/macos-audio` → 40 passed；Beta target build 通过。此前能力清单/API 窄回归 39 passed、wheel 检查确认 manifest 随包。GUI 手动冒烟及真实 Provider usage/cost E2E 尚未做；本轮未发起云请求、未读取 Keychain、未采集麦克风，也未增加持久化。

## 下一步

- 客户端断连后的服务端取消、run 终态和 usage 记录已有 ASGI 自动回归；仍需在干净 Beta 会话做 GUI 手动冒烟；不提供退出后后台续跑。
- 在正常启动 Beta 时手动检查“用量”面板的空记录、UNKNOWN/null 呈现和加载失败提示。
- 精确 Beta 云型号仍需按功能触发条件验证真实 usage/cost E2E；目前已实现的协议透传只由 mock 回归证明。之后再明确各 Provider 的费用来源、汇率与缺失值 fail-closed 规则，并实现 D-005 预算门；当前不做云调用，也不把 mock 当作供应商端到端证据。
- 在正常启动 Beta 时检查精确型号 capability 查询、用量面板、空记录和认证失败状态。
- 精确云型号的 usage 兼容性尚需依产品功能触发条件验证；工具、多模态和持久化仍须各自完成决策、实现与验证后再启用。
