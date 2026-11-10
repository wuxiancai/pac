# 对话编排与固定助理角色

更新日期：2026-11-10

## 固定角色（V2 首批）

认证 `/chat/stream` 接受 `assistant_key`：`main_assistant`（默认）、`project_assistant`、`meeting_assistant`、`task_planner`。macOS Beta 显示角色菜单并将用户选择保存到 UserDefaults；每轮请求显式带角色键。后端白名单之外的值由请求模型拒绝，运行时 registry 也拒绝未启用键。

三个专业角色使用代码内固定 system 指导，分别面向项目目标/里程碑/依赖/风险、会议议程与用户提供记录的决策/行动项、任务拆解/优先级/期限。指导明确不声称已执行外部操作；会议角色不会隐式访问日历。没有工具、后台 Agent、团队协作或外部写操作。`main_assistant` 不增加角色提示，保留既有上下文路径。角色是请求级模式，不改变聊天/任务持久化结构，也不自动读取记忆。

## Skills（V3 首版）

新 migration `0003_local_skills` 在本机 SQLCipher `skills` 表中安装固定目录：风险审查、决策简报、行动项整理。每个记录含版本化提示定义与 `{"tools":[],"external_write":false}` 权限清单。认证 `GET /skills` 只返回 ID、键、名称、说明、版本和状态，不返回提示正文；无编辑、导入、删除、代码加载或工具执行接口。

聊天输入可带最多 3 个 `skill_keys`。服务端只解析数据库中 ACTIVE 的登记键，重复、未知、超量选择均拒绝；提示以 system context 加在本轮上下文，不修改持久聊天记录。macOS 菜单选择不写 UserDefaults，发送时带入当前请求并立即清空。当前会话可走已有本机或用户已选择的云端路由；没有新增出站路径，云端内容继续受现有 Consent/Policy 控制。模板不保证模型完全遵守文字指令。

## 当前结构

`backend/pac_poc/orchestrator.py` 提供一条最小、可替换的对话编排路径：

1. `ConversationTurn` 承载一次请求的消息、Provider、模型和授权元数据；对象只在请求生命周期内存在。
2. `PassThroughContextBuilder` 只使用调用方明确提交的消息和用户主动导入的文本资料，不读取任意路径、数据库或记忆。
3. `MainAssistantOrchestrator` 只接受四个封闭固定 profile，构造 `LocalModelRequest` 并把流交给项目自有 `ModelGateway`。
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

## 聊天请求输入边界

`/chat/stream` 只接受缺省或 JSON/`+json` Content-Type，并按 ASGI 请求流分块读取，请求体最多 512 KiB；该上限覆盖 40,000 字符上下文以 UTF-16 surrogate-pair JSON 转义时的字节量及结构开销。未提供 `Content-Length` 的分块请求同样受限，超限在 Pydantic 校验、编排和 Provider 调用前返回 413。语义级上下文仍另受 40,000 字符限制。

## 进程内 Usage 首段

聊天 run 结束时，`UsageLedger` 保存最近最多 512 条请求 metadata，认证 `GET /usage?limit=50` 可读取（limit 最大 100）。记录含 run/provider/model/region/purpose/data level、生命周期状态、wall latency，以及 Provider 明确报告的 token/cache/cost metadata；不含消息、回复、密钥或音频，进程退出即清空。Gateway 已把 Ollama 与 OpenAI-compatible 流最终帧中实际返回的 token 计数交给 ledger；只有 OpenRouter 的非流式或流式响应中，`usage.cost` 经验证且可由有限浮点数表示时才记录为实际 USD；其他 Provider 即使返回同名字段也保持费用 unknown；超大整数、非有限数和负值视为未知，不让异常数值转换中断流处理。未返回或不完整的 usage/cost 在请求明细中仍为 `unknown`/`null`。D-005 版本化 CNY 估算器已接入云请求完成路径，估算额写入 SQLCipher 月度聚合；用量页展示估算累计和 80 元提示，估算累计加本次请求预估触及 100 元时在请求发出前拦截。分项 usage ledger 仍保留 Provider 实报字段语义；估算不代表账单实扣。

Ledger 在写入时拒绝非有限时间戳、布尔/非整数毫秒延迟，以及负数、布尔或非有限音频时长，避免无效数值进入 `/usage` JSON 响应；未知音频时长仍以 `null` 表示。

macOS Beta 的“用量”面板已接入此只读接口，显示最近记录的 Provider/model、用途、数据等级、区域、开始时间、状态、耗时，以及实际/估算/未知 token 和费用。本机与交互式聊天的用途标签分别显示为“本机处理”和“交互式聊天”，本机空区域显示为“本机”；其他空区域仍显示“区域未知”。当前没有真实 token/费用时明确显示为未知，不作推算。面板查询只访问认证 loopback API，不发起模型请求；数据显示依赖当前进程内 ledger，退出后消失。

### 流式 token 与 OpenRouter 费用透传（2026-11-09）

- `ProviderStreamChunk` 在 Gateway 内携带可选文本增量和 Provider 返回的 prompt/completion token 计数；SSE 客户端仍只收到文本增量。Ollama 完成帧的 `prompt_eval_count`/`eval_count` 和 OpenAI-compatible Provider 最终 usage 帧可进入 `UsageLedger`。
- Gateway 现也保留 Provider 报告的缓存命中输入 token：DeepSeek 使用 `usage.prompt_cache_hit_tokens`；Qwen/OpenAI-compatible 用法读取 `usage.prompt_tokens_details.cached_tokens`，校验它不超过 prompt 总 token 后再写入 bounded ledger，并显示在 macOS 用量面板。Qwen 官方说明此字段表示输入缓存命中 token；DeepSeek 官方 usage 分别提供 cache hit/miss token。当前这是原始用量明细，不据此推算费用。
- 对云端流请求附加 `stream_options.include_usage=true`。DeepSeek 官方 Chat Completions API 文档说明 SSE 最后一帧带整次请求 usage；阿里云 Model Studio 文档说明 Qwen OpenAI-compatible streaming 可用此选项返回最终 token usage；OpenRouter API/SDK 文档列出 `stream_options.include_usage`。这些是协议文档依据，不等于 Beta 当前精确型号的真实 usage 实测：未发云请求、未读取 Keychain。
- OpenRouter 最终 `usage.cost` 如为有限、非负数值，按 OpenRouter 报告的 USD 标记为 actual 并记账；[Chat Completions 文档](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion) 在 `usage` schema 列出 `cost`，OpenRouter [支持说明](https://openrouter.ai/support)说明费用依据 Provider 使用量计算。mock 回归覆盖了流最终帧。当前固定 Beta 型号尚未做真实流式费用 E2E；DeepSeek/Qwen 没有经核实的实际费用流字段，因此继续 unknown/null。
- 请求用量明细只有收到非负整数 Provider token 字段才标为 `actual`。中断、缺少最终 usage 或字段不完整时仍是 `unknown`；独立的 D-005 预算估算器会在用量缺失时按请求文本字符数估 token 并标记估算，不改写此实际 usage 记录。请求前预算预估用 UTF-8 字节数和适配器 1,024 输出 token 上限估算，通过跨实例 SQLCipher 事务预留保护预算余量。

#### D-005 计费输入研究（公开官方资料，2026-11-10 更新）

- DeepSeek 当前价目页将 `deepseek-flash` 映射到 V4.1-Flash-1017，并按 cache-hit、cache-miss、输出 token 及 UTC 峰谷时段计价；页面说明费用从充值或赠送余额扣除，价格可能调整。Chat Completions usage 提供 prompt/completion token 与 cache hit/miss 数，不返回每请求 `cost` 金额。因此可验证用量构成，但要按公开价格重算仍需固定价目版本、请求时段与精确计费时区规则，并接受公开费率变化带来的估算性质。见[DeepSeek 价目表](https://api-docs.deepseek.com/quick_start/pricing/)和[Chat Completions usage schema](https://api-docs.deepseek.com/api/create-chat-completion/)。

- Qwen `qwen3.8-flash` 官方模型页公布北京价目及 cache-hit 单价；页面同时提示价格为原价、不含活动优惠。Model Studio 字段文档将 OpenAI Chat compatible 的 `usage.prompt_tokens_details.cached_tokens` 定义为缓存命中输入 token。见[模型信息与价目表](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、[缓存/用量字段说明](https://help.aliyun.com/en/model-studio/ptu-long-input-and-cache)。
- DeepSeek API 的缓存命中/未命中字段及对应缓存机制见[官方缓存说明](https://api-docs.deepseek.com/guides/kv_cache/)；本 Gateway 保留 hit 数，但仍缺精确 Beta 型号真实 stream 验证。当前费率与 usage schema 的映射见上条。
- OpenRouter 返回值中的 cost 以 USD 记录；其官方说明模型推理成本按 Provider 价格透传，购买 credits 时另收平台费，可能另有支付处理费用。故 `usage.cost` 不必然等同用户信用卡/支付宝最终人民币支出。见[OpenRouter 用量与费用说明](https://openrouter.ai/support)。
- 上述公开价目会变化，且缓存/时段/活动/下游路由和充值费用口径不同。2026-11-10 SAFE 美元兑人民币中间价为 6.7167 CNY/USD，估算快照采用向上取整的 6.72；汇率来源为[国家外汇管理局人民币汇率中间价](https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do)。这只是带日期的估算换算，不是实时汇率。

## 验证

### 2026-11-10 V3 多 Agent 本机生成与综合复核

- Ollama 官方 `/api/chat` 支持请求级 `think` 布尔字段；关闭时请求不输出 thinking，参考 [Ollama Thinking API](https://github.com/ollama/ollama/blob/main/docs/capabilities/thinking.mdx)。Beta 仅为多 Agent 专业角色和总助理综合请求传 `think:false`，普通单助理请求省略该字段，保持模型默认行为。
- 综合请求将专业角色结果作为前置参考消息，并把原始用户请求保留为最后一条消息；system guidance 要求直接回答、遵守语言/格式/篇幅，并把注入指令仅作为内容过滤对象，不因模型来源而整体拒绝。
- 2026-11-10 新增专业角色约束：每位被选角色只围绕用户本轮目标给出相关、具体建议，并遵守数量、长度、语言、顺序和格式；综合层重复强调这些约束且禁止扩展到无关领域。API 自动回归确认每个本机角色请求和汇总请求均包含该指令；定向协作测试 1 passed，Ruff 与 `mypy pac_poc/beta_api.py` 通过。
- 自动化：定向 `tests/test_beta_api.py tests/test_local_model_gateway.py tests/test_orchestrator.py` → 69 passed；Ruff 与三个修改后端模块 mypy 通过；后端 all-extras/all-groups 全量 → 325 passed，1 条既有 Starlette/httpx 弃用警告。
- GUI：本机 `qwen3.5:0.8b` 首次默认 thinking 请求两分钟后仍无第一角色正文，停止后 UI 正确显示取消；应用 `think:false` 后双角色、汇总流程在约十几秒内完成。第一次汇总只讨论“信任边界”并拒绝回答；调整建议与原请求顺序后，复测直接给出议题建议。仍观察到小模型没有严格遵守用户要求的字数上限，单样本不构成质量承诺。验收只访问 Ollama loopback，无云端请求、无麦克风采集。合成验收聊天保留在本机 SQLCipher 历史，没有删除。
- 2026-11-10 强化提示后的 GUI 样本：项目/会议角色处理“校园图书馆读书周准备”，两角色正文仍超过 12 字约束；总助理综合给出 3 条编号、均不超过 12 字且与目标相关的准备建议。与提示调整前“无编号且偏题”的样本相比，该题综合格式与相关性改善；单样本不能证明稳定质量，B9 继续开放。构建版本经 `run_beta_app.sh` 启动，状态栏确认 Ollama/qwen3.5:0.8b；无云端请求或麦克风采集。
- 后端全量当前复跑 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 346 passed、1 条既有弃用警告；首次复跑有 1 项阶段追踪文档断言失败，补齐独立 POC 崩溃 staging 状态描述后复跑通过。

2026-11-10 UsageLedger token 状态校验补强：`unknown` 记录必须不含 token 数；`actual`/`estimated` 记录必须至少含输入或输出 token 数，防止 `/usage` 返回互相矛盾的状态和数值。定向回归 `tests/test_usage.py tests/test_beta_api.py` → 46 passed；完整后端回归 → 267 passed、1 条既有 Starlette/httpx 弃用警告；`ruff check pac_poc/usage.py tests/test_usage.py` 与 `mypy pac_poc/usage.py` 均通过。该校验只约束内存用量记录一致性，不估算费用、不持久化、不改变预算策略。

2026-11-10 用量面板元数据显示：每条记录展示用途、数据等级、开始时间和正确区域标签，便于分辨本机处理和带授权的云端交互；空值/未知 token 与费用语义保持不变。`swift test --package-path poc/macos-audio` → 40 passed；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。Swift Codable 回归覆盖本机 L0、空区域→本机、Unix 时间戳，以及交互聊天 L2/DeepSeek China 区域映射。GUI 用量面板手动验收和真实 Provider usage/cost E2E 仍待完成。

在 `backend/` 目录执行：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_usage.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_beta_api.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/usage.py pac_poc/orchestrator.py pac_poc/model_capabilities.py tests/test_usage.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_beta_api.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/usage.py pac_poc/beta_api.py pac_poc/orchestrator.py pac_poc/model_capabilities.py
swift test --package-path poc/macos-audio
```

结果（2026-11-09）：ASGI 层 HTTP 断连回归验证请求断开会关闭上游异步流、run 状态变为 `CANCELLED`，认证 run 查询与 UsageLedger 均返回该终态。另新增 DeepSeek cache-hit 字段解析及 ledger/UI 透传，Qwen/OpenAI-compatible `cached_tokens` 解析、异常计数拒绝及 Swift Codable 覆盖。后端定向回归 8 passed，Ruff 与相关模块 mypy 通过；后端全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 242 passed，1 条既有 Starlette/httpx 弃用警告。Swift 全量 `swift test --package-path poc/macos-audio` → 40 passed；Beta target build 通过。此前能力清单/API 窄回归 39 passed、wheel 检查确认 manifest 随包。GUI 手动冒烟及真实 Provider usage/cost E2E 尚未做；本轮未发起云请求、未读取 Keychain、未采集麦克风，也未增加持久化。

## 下一步

- 已在 Beta GUI 检查有本机请求记录时的用量呈现：本机 L0、token 输入/输出、未知缓存/费用和云预算估算说明可见。空记录、加载失败和认证失败提示仍待 GUI 验收。
- 模型设置 GUI 显示当前本地 `qwen3.5:0.8b` 及 Ollama 运行/安装提示；显式精确型号 capability 查询已实机点验并展示证据和 unknown-safe 状态。重启后首次 CUA 读取短暂超时，稍后恢复，原因未判定；本项最终 GUI 查询通过，详见 `docs/HANDOFF.md`。
- 客户端断连后的服务端取消、run 终态和 usage 记录已有 ASGI 自动回归；仍需在干净 Beta 会话做 GUI 手动冒烟；不提供退出后后台续跑。
- 精确 Beta 云型号真实 usage/cost E2E 仍待对应功能验收；真实云测试须按 Provider 和数据范围另行获得用户明确确认。现有协议透传仅由 mock 回归证明，不作 Provider 端到端证据。
- 工具、多模态和持久化等新能力继续按各自决策、实现和验证门禁推进。


2026-11-10 Consent lease 清理异常回归：Gateway `stream_with_usage()` 将上游 `aclose()` 包在内层清理中，外层 `finally` 无条件注销 Consent 在途操作。合成 iterator 在 `aclose()` 故意抛错后，测试确认 ConsentManager 不再保留 in-flight task；与现有 stream 撤销取消测试定向共 2 passed，Ruff 和 `mypy pac_poc/model_gateway.py` 通过。后端全量 277 passed，1 条既有 Starlette/httpx 弃用警告。

2026-11-10 补充取消路径：若流迭代/取消时上游 `aclose()` 也抛错，Gateway 保留原始 `CancelledError` 或迭代异常，不让清理错误覆盖；正常流完成时仍传播关闭异常。Consent lease 在外层 `finally` 无条件释放。定向 `tests/test_consent_aware_gateway.py -k 'usage_stream_'` → 2 passed；Ruff 与 mypy 通过；后端全量 278 passed、1 条既有 Starlette/httpx 弃用警告。

2026-11-10 补齐无 usage 流接口：`ModelGateway.stream()` 也在取消/迭代异常时保留原异常并尽力关闭上游，正常结束仍传播关闭异常，finally 无条件释放 lease。它与 `stream_with_usage()` 的清理语义一致。定向清理/取消回归 3 passed，Ruff/mypy 通过；后端全量 279 passed，1 条既有 Starlette/httpx 弃用警告。

2026-11-10 RunRegistry 并发创建顺序：`created_at` 现在在取得注册锁后读取，与实际插入及容量淘汰的序列化顺序一致，避免线程被抢占时出现时间戳倒序。并发回归持有注册锁后启动创建线程，确认时间读取发生在锁释放后。`tests/test_orchestrator.py -k run_registry` → 3 passed；Ruff/mypy 通过；后端全量 280 passed、1 条既有弃用警告。

2026-11-10 系统时钟回拨边界：RunRegistry 状态转换令 `updated_at` 不早于前一状态时间；UsageLedger 的 `completed_at` 复用终态 run 的 `updated_at`，避免实际记录完成早于创建时间而被校验拒绝。测试通过回归时将 API 模块墙上时钟模拟为 0，确认失败请求仍写入合法用量记录。定向 `tests/test_orchestrator.py tests/test_beta_api.py -k 'run_registry or local_model_error_is_sanitized'` → 5 passed；Ruff/mypy 通过；后端全量 281 passed、1 条既有弃用警告。


#### D-005 版本化估算器首版（2026-11-10）

- `pac_poc/budget.py` 保存 `PRICE_VERSION=2026-11-10` 的静态价目快照：DeepSeek 直连按官方峰时价估算；Qwen `qwen3.8-flash` 按北京原价；OpenRouter 固定 `deepseek/deepseek-v4.1-flash-1017` 按公开模型目录的输入/缓存/输出费率。USD 统一使用 SAFE 2026-11-10 中间价向上取整为 6.72 CNY/USD，记录汇率版本。缓存 usage 可用时拆分命中/未命中；缺失 token usage 时暂按文本字符数作估算 token，并返回 `estimated` 成本估算。
- 未登记的 Provider/model、价币不符、无效数值拒绝估算（调用方必须 fail-closed）。估算器已连接 Stream API、SQLCipher 月度聚合、80 元用量页提示与 100 元请求前硬拦截；云请求按本地 Asia/Shanghai 自然月分桶，SQLCipher 事务在共享数据库实例间原子预留请求预算并于结束时结算，单个 Beta 服务进程另用异步锁串行发送。预留五分钟过期回收，活动流每分钟续租；当前远端 HTTP 读取空闲超时为 45 秒。OpenRouter reported USD 先换算成人民币估算后计入预算，原始 USD 仍在进程内分项记录中。当前月在此功能启用前已发生的账单无法回填，因此首次启用当月累计可能低估；真实型号 usage/cost E2E 和价目快照更新流程仍待验证。
- 公开来源： [DeepSeek 模型与价目](https://api-docs.deepseek.com/quick_start/pricing/)、[阿里云 Qwen3.8-Flash 价目](https://help.aliyun.com/zh/model-studio/qwen3-8-flash)、[OpenRouter models API](https://openrouter.ai/api/v1/models)、[SAFE 汇率中间价](https://www.safe.gov.cn/AppStructured/hlw/RMBQuery.do)。OpenRouter 实扣推理 USD 转成人民币后仍是估算，且不含充值手续费、税费或个人账户折扣。


2026-11-10 D-005 月预算请求门禁实现：新增 Alembic `0004_monthly_cloud_budget`，只在 SQLCipher 中保存每个自然月的估算人民币总额、请求数和价目版本，不保存提示词或回复。数据库 upsert 原子累加，store 内串行化 SQLCipher 连接池访问；出站前在共享数据库事务中检查累计值和所有未过期预留，再原子创建当前请求预留，完成后在同一事务中删除预留并计入最终估算。单个 Beta 服务进程另用异步锁串行云请求；预估按 UTF-8 字节输入和适配器最大 1,024 输出 token，预留五分钟过期回收、活动流每分钟续租（远端 HTTP 读取空闲超时 45 秒）。无持久库、账本写入失败或未知价目时阻止云请求。`GET /usage` 在单个 SQLCipher read transaction 中返回已结算、在途预留与合计预估，并据合计状态报告 80 元提示和 100 元拦截；macOS 用量页分别显示已累计估算与执行中预留。当前月历史账单无法回填；真实 Provider usage/cost E2E 与价格快照更新流程仍待验收。双 store 实例并发预留/结算自动回归通过，完整测试与 GUI 手动验收详见最新 HANDOFF。

2026-11-10 B9 GUI 复核：新会话显式选择“会议助理”和“项目助理”，提交合成校园图书馆延长开放问题。Beta 显示会议观点、项目观点及总助理综合结论，约 10 秒完成；状态栏确认本轮 `ollama / qwen3.5:0.8b`，符合仅本机顺序调用路径。合成提示要求 3 条且每条不超过 20 字，综合结论中有 1 条超长，角色观点也有偏题建议。说明编排闭环可用，模型内容/格式质量仍不稳定；单次测试不构成质量保证。测试问题和回复保留在本机 SQLCipher 会话；未调用云 Provider、麦克风或 Keychain。

#### D-003 30 天 metadata-only 云请求审计（2026-11-10）

- SQLCipher migration `0005_security_audit` 为当前 Beta 云聊天写入策略拒绝、用户确认/预算门后请求尝试和完成/失败/取消终态。审计仅保留 provider/model/region/purpose/data level/决策与固定 reason code、trace/resource UUID 和时间；不保存 Consent grant、消息正文、回复、Key/Token 或音频。
- 写入、服务启动及认证用量查询时清理 30 天前记录；数据库密钥启动的 Beta 服务另外每 6 小时执行一次本机 SQLCipher 清理，退出时取消维护任务后关闭 store。`GET /usage` 返回最多 100 条审计事件；Swift 用量页按最近 30 天安全记录与进程内 Usage 明细分区显示。自动契约覆盖拒绝/成功路径、超期删除、周期清理循环与无正文；还没有真实 Provider 请求或 GUI 实机呈现验收。Consent 持久授权本身仍不保存，未来新增外部写或其他敏感能力时必须补充对应审计事件。

### 2026-11-10 B8 单轮 Skill GUI 冒烟

- 在新本机会话选择“行动项整理”，输入三项合成读书周事项；发送后 UI 从 `Skills 1` 立即变为 `Skills 0`，证明所选 Skill 不跨轮保留。
- 本机 `qwen3.5:0.8b` 超过两分钟仍显示生成中且没有正文；用户点击停止后 run 标记已取消。不能据此判断 Skill 行为导致延迟；默认 thinking/本机服务状态仍可能影响，原因未判定。无云请求或麦克风采集，聊天保存在本机 SQLCipher。

### 2026-11-10 B9 选择顺序修复与 GUI 复测

- 协作选择原以 `Set` 保存并在发送前排序，导致点选顺序与实际专业角色调用顺序不一致。现以有序数组保存点选顺序，取消单个选择会移除对应项，发送时复制顺序快照并清空选择。
- GUI 合成样本先选“项目助理”、后选“会议助理”，修复后按该顺序展示角色观点；旧书交换活动综合结论三项切题且简短，专业观点仍有条目超过 15 字。该样本证明请求顺序和一题输出，不证明普遍内容质量；B9 继续 IN PROGRESS。
- Swift 全量 62 passed；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。真实调用仅到本机 Ollama，未访问云 Provider、麦克风或 Keychain。

### 2026-11-10 B9 逐项覆盖提示迭代

- 专业角色与综合层现在明确要求：用户列出的每个事项都逐项覆盖，不得漏项或用泛化项替代。API 回归确认专业角色及综合请求均携带该约束；定向测试 1 passed，Ruff/mypy 通过，后端全量 346 passed、1 条既有弃用警告。
- 同一科技节合成任务复测仍显示质量波动：任务规划角色臆造用户未提供的时间值，综合项数字与事项不符且未保留顺序。该提示只能表达意图，不能保证本机小模型输出；B9 继续 IN PROGRESS。
