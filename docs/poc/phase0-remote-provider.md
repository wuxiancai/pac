# 阶段 0 POC：真实 Provider 探测准备（工作包 0C）

状态：`IN PROGRESS`。固定目标 adapter、Keychain reader、一次性终端授权入口已实现。用户已分别对 DeepSeek 与 OpenRouter 完成单独真实探测，并通过同一 ModelGateway 实例、逐次独立授权，完成两家顺序真实路由且均精确匹配合成响应。更广的 Provider 能力矩阵仍未验收。

## 用户确认与固定范围

- 用户指定两个测试候选：DeepSeek、OpenRouter。
- 用户确认 DeepSeek 按中国处理，OpenRouter 使用 Global 路由。DeepSeek 官方隐私政策称其服务数据在中国处理；OpenRouter 默认 `openrouter.ai` 为全球路由，US/EU in-region routing 另需 Business/Enterprise 账户条件。见 [DeepSeek 隐私政策](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html?os=v0)、[OpenRouter US/EU in-region routing](https://openrouter.ai/business/eu/)。
- 本 POC 固定使用 DeepSeek `deepseek-flash`、`https://api.deepseek.com/chat/completions`（[官方模型/API 文档](https://api-docs.deepseek.com/api/create-chat-completion)）；OpenRouter `deepseek/deepseek-v4.1-flash-1017`、`https://openrouter.ai/api/v1/chat/completions`（[官方模型目录](https://openrouter.ai/deepseek)）。模型和费用可能变化，真实请求前应按官方当前账号目录再次确认。
- 基础探测正文为 `Reply with exactly this text: phase0-probe-ack`，L1 合成文本，最多 64 output tokens；基础 CLI 每次只执行一条非流式 chat-completions 请求，不带工具、不重试。能力矩阵探测使用同等级合成内容，按独立命令测试 SSE、工具提案、JSON、错误处理和 metadata。OpenRouter Global 初始选择一个符合条件的上游端点，adapter 设置 `provider.allow_fallbacks=false` 禁止跨 Provider 故障切换；请求启用路由 metadata，并输出实际选择的 Provider、服务区域、token 用量和服务报告的 USD cost（如 API 返回）。

## 本机 Keychain 配置

**不要把 API Key 发到聊天、终端命令参数、环境变量或普通配置文件。** 用 macOS 自带“钥匙串访问”保存：在 Spotlight 搜索 `Keychain Access` / `钥匙串访问`，选择 `login` 钥匙串，按 Command-N 新建密码项（[Apple 操作说明](https://support.apple.com/en-ge/guide/keychain-access/kyca699a9058/mac)）。分别新建两项：

| 字段 | DeepSeek | OpenRouter |
|---|---|---|
| Keychain Item Name / Service | `com.personal-ai-assistant.phase0.provider` | `com.personal-ai-assistant.phase0.provider` |
| Account Name | `deepseek` | `openrouter` |
| Password | 该 Provider 的 API Key | 该 Provider 的 API Key |

2026-11-08 用户已按流程输入两次确认短语，但两次均返回 `provider credential is missing or unavailable in Keychain`。脚本已进入 Keychain 查询，但未取得凭据，因此未发送 HTTP 请求。请检查钥匙串访问中是否在 **login** 钥匙串创建了“通用密码”项，且名称/Service、账户名完全匹配上表；不要删除或覆盖其他钥匙串项。可先只创建一项，再重试对应 Provider。

随后用户提供 Keychain Access 截图；只读元数据查询确认 `login` 钥匙串中 `deepseek` 与 `openrouter` 两条 generic-password 记录均匹配上述 service/account（未读取密钥值）。用户之后报告 DeepSeek 探测正常成功；未提供响应、token/cost 或实际上游元数据，因此只记录为一次用户报告的合成文本端到端成功。OpenRouter 未成功，用户判断账户无余额并要求按预期失败处理；此原因未经响应码/账单验证，不能作为 OpenRouter 连通或模型能力证据。

`MacOSKeychainCredentialProvider` 通过 argv 固定的 `/usr/bin/security find-generic-password` 从登录钥匙串读取；不使用 shell，不将密钥放进进程参数，stdout 只由当前 Python 进程捕获在内存中。只有 CLI 的精确确认短语通过后，Gateway 才会通过 `ConsentAwarePolicy`，之后 adapter 才会请求读取对应条目。每次请求的 Consent grant 最长 60 秒，完成后立即撤销。

## 逐次手动运行

在仓库 `backend` 目录分别运行，每条命令只对指定 provider 发一条合成请求：

```bash
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_remote_provider_poc.py deepseek
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_remote_provider_poc.py openrouter
```

脚本会先展示 provider/model/region/purpose/data level/完整合成正文/max tokens，并要求输入精确短语 `ALLOW DEEPSEEK` 或 `ALLOW OPENROUTER`。空输入、错误输入、缺失凭据、无有效授权时均不会发送请求；每次只发一条请求。OpenRouter 由服务选择一个 Global 上游端点，但禁止请求失败后转发给其他上游。若 macOS 要求访问 Keychain，建议只允许本次访问。脚本只输出合成探测响应、路由/usage metadata 和是否精确匹配，不输出 API Key。

必须在运行时再次确认该 provider 的这一次精确请求；地区选择不等同于单次 Consent。运行一次 `deepseek` 不会授予 `openrouter`，反之亦然。

### 同一 Gateway 跨 Provider 路由 POC

在 `backend` 目录运行 `UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_switch_poc.py`。脚本在一个 `ModelGateway` 实例注册两家固定 adapter，并依次路由同一合成请求。每家请求前都会展示完整目标和内容，并分别要求 `ALLOW DEEPSEEK`、`ALLOW OPENROUTER`。拒绝、凭据缺失或请求失败均不会触发另一家代发，也不会重试或自动 failover。脚本成功与否不能由本地 mock 代替，须用户实际运行并提供输出后记录真实证据。

### Provider 能力矩阵探测

每条命令只探测一家 Provider 的一项能力。进入 `backend` 目录后可分别运行：

```bash
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py deepseek stream
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py deepseek cancel
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py deepseek tools
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py deepseek json
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py deepseek error
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py deepseek metadata --repeat 2
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py openrouter stream
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py openrouter cancel
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py openrouter tools
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py openrouter json
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py openrouter error
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py openrouter metadata --repeat 2
```

`cancel` 启动一条真实 SSE 请求，首个文本 delta 到达后即关闭客户端流；这会产生一次 Provider 请求/可能计费，只能验证客户端取消和本地响应流清理，不能单独证明 Provider 停止生成。每个外发请求都会打印实际 payload 并要求独立精确确认，短语格式为 `ALLOW <PROVIDER> <CAPABILITY> <序号>`；没有某项确认就不会读取 Keychain 或发送该项请求。`tools` 使用强制 tool_choice，仅返回合成函数提案，不执行工具。DeepSeek 工具探测显式设置 `thinking.type=disabled`：官方文档说明 thinking 默认启用，而 thinking mode 不支持指定工具的 named `tool_choice`，会返回 HTTP 400。见 [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [Tool Calls 指南](https://api-docs.deepseek.com/guides/tool_calls/)。OpenRouter 工具探测设置 `provider.require_parameters=true` 与 `allow_fallbacks=false`，以筛掉不支持请求参数的端点且不启用 fallback；官方说明部分不支持工具调用的端点可能忽略 tools 并返回普通文本。见 [OpenRouter 工具调用指南](https://openrouter.ai/blog/tutorials/tool-calling/) 和 [Provider routing 文档](https://openrouter.ai/blog/insights/model-routing/)。若没有 tool call，CLI 会显示普通文本、finish_reason、实际模型及 OpenRouter 下游 Provider/区域（服务有返回时），用于诊断。`json` 请求 JSON object 并检查响应，同时输出 finish_reason、模型/路由、token 和费用 metadata，便于识别空正文。`error` 故意发送无效 `response_format` 并把 HTTP 4xx 视为预期拒绝；请求可能计费，不重试。`metadata --repeat 2` 会逐次确认并发送两条请求，打印模型、Provider/region、token 和费用，供重复观察；DeepSeek 若不返回 region/cost 会如实显示缺失。

拒绝边界可在不联网的情况下，分别对 `deepseek` 与 `openrouter` 运行 `UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/probe_provider_capability_poc.py <provider> deny-check`。它将 Consent policy 前接 HTTP MockTransport tripwire，断言无授权时 Keychain 读取数和 transport 调用数都为零。这是进程内网络边界证据，不是操作系统抓包证据。 2026-11-08 本轮在两家 Provider 配置上重跑均通过：Keychain reads=0、HTTP transport calls=0。

新增 `backend/scripts/probe_denied_egress_poc.py <provider>` 用真实 HTTPX client（不注入 MockTransport）和凭据读取 tripwire，在无 Consent 下尝试 Gateway 请求，并留出观察窗口。2026-11-08 分别实跑 OpenRouter、DeepSeek：两者均由 Policy 在 Adapter 前拒绝，credential reads=0。针对两个测试 PID 的 macOS `lsof -nP -a -p <PID> -i` 检查均无网络 socket；正向对照确认同一工具能列出 loopback TCP sockets。用户同时提供 `tcpdump -i en0` 窗口结果（546 packets），其中有已建立 TCP/443 流量；该捕获未按 PID/目标过滤，不能归因给拒绝 harness。结合 Policy 顺序、credential tripwire 与 PID 级 OS socket 表，当前 POC 请求拒绝路径未建立网络 socket；此证据不是包级、全系统绝对零流量证明，lsof 是观察时刻的活动 socket 快照。

## 已验证（仅本地 MockTransport）

- 默认拒绝发生在 Keychain 读取和 adapter 网络调用之前。
- 同一 `ModelGateway` 实例可按 request.provider 分别选中两家固定 adapter；本地 MockTransport 回归验证两条 endpoint 顺序命中、Keychain account 按 provider 读取、两次响应正文精确匹配。这不是远端服务证据。
- 本地 MockTransport 另外验证 streaming 事件解析、工具调用作为数据返回不执行、`response_format` 与 `tool_choice` 透传、HTTP 错误脱敏。拒绝 tripwire CLI 运行结果为无 Consent 时 Keychain 读取数=0、HTTP transport 调用数=0。
- DeepSeek 首次真实工具探测已获当次确认但返回 HTTP 400；错误正文按安全设计未保留。根据 DeepSeek 官方文档，thinking 默认启用且 thinking mode 不接受 named `tool_choice`，这是与观察一致的原因推断，非对错误正文的直接确认。POC 已调整为 DeepSeek 工具请求显式关闭 thinking，并在新 Consent 通过后复测。
- 精确授权后 adapter 才从凭据接口取密钥；HTTP header/body 与固定 model/endpoint 匹配。
- OpenRouter Global SSE streaming 分块解析；非流式响应 metadata 可报告实际选择的上游 Provider/region、token 数和 cost；请求禁用跨 Provider failover；tool call 仅作为 `ToolCallResult` 数据返回，不执行工具。
- JSON `response_format` 透传；Provider 非 2xx 错误只暴露 HTTP 状态，不保留 response body；端点/model/region 配置均固定 allowlist。
- Keychain reader 只允许 `deepseek` / `openrouter` 两个 account，CLI 参数不包含秘密，缺失/拒绝读取错误不暴露原始 stderr。
- 窄回归命令：`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_remote_providers_poc.py tests/test_local_model_gateway.py tests/test_consent_aware_gateway.py`；当前 **31 passed**，含同一 Gateway 双 adapter 切换、OpenRouter tool 参数过滤和拒绝 tripwire 回归。这些都是本地测试，不是 Provider 端到端证据。
- 当前全量 Python：`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security --extra phase0-embedding --group dev pytest -q`：**142 passed**（2026-11-08，含 OpenRouter tool 参数过滤回归）。`compileall`、`uv lock --check` 均通过；macOS Swift Testing `swift test`：**27 passed**（既有基线）。
- DeepSeek SSE 的一次真实结果已补记；其他能力矩阵脚本的真实 Provider 请求仍待用户执行逐项确认。本地拒绝 tripwire 与远端 adapter 窄回归见本轮 HANDOFF。不得把本地 transport 测试记作真实 Provider 能力。

## 用户实机真实请求结果（2026-11-08）

### API Key 错误提示与 DeepSeek JSON 第三次观察

- 用户询问 JSON 空正文是否可能由 API Key 错误导致。随后一次 DeepSeek JSON 请求成功返回 `{"phase0":"ack"}`，结构检查 True，finish_reason=`stop`，模型 `deepseek-flash`，tokens=68/28/96。成功的 chat completion 表明该次请求的 Key 已被 Provider 接受；先前空正文不能单独证明 Key 错误。
- 适配器现在对 HTTP 401 输出明确的“Provider rejected API credentials”提示；本地 Keychain 缺失仍沿用单独的凭据不可用错误。HTTP 402、403、429 分别提示余额/付款、权限和限流状态；错误响应正文仍丢弃，不泄露密钥。这里只按状态码分类，不尝试探测或回显 Key。
- `error` 能力探测只把 HTTP 400/422 视为无效请求格式的预期拒绝。认证、余额、权限、限流及服务端错误不会被误记为 payload 错误路径通过。新增本地 MockTransport 回归；未为验证 API Key 额外发送请求。
- DeepSeek 官方错误码将 401 定义为认证失败（错误 API Key），402 为余额不足，422 为参数无效，429 为限流：[官方错误码说明](https://api-docs.deepseek.com/quick_start/error_codes/)。OpenRouter chat completions 文档区分 401、402、403、422、429 等响应状态：[官方 Chat Completions API](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request)。

- **DeepSeek**：用户在 CLI 输入 `ALLOW DEEPSEEK` 后发送一条 L1 合成文本请求，返回 `phase0-probe-ack`，与期望文本完全匹配。实际模型 `deepseek-flash`；token 用量 prompt 42 / completion 41 / total 83。服务未返回下游 Provider、区域或费用信息。
- **OpenRouter Global**：用户在 CLI 输入 `ALLOW OPENROUTER` 后发送一条 L1 合成文本请求，返回 `phase0-probe-ack`，与期望文本完全匹配。实际模型 `deepseek/deepseek-v4.1-flash-1017`；下游 Provider `Relace`、服务区域 `HKG`；token 用量 prompt 42 / completion 17 / total 59；报告费用 USD 0.000008752。
- **同一 Gateway 顺序路由复测**：用户随后运行 `probe_provider_switch_poc.py`，分别输入 `ALLOW DEEPSEEK` 与 `ALLOW OPENROUTER`。同一 Gateway 实例向 DeepSeek（`deepseek-flash` / China）和 OpenRouter（`deepseek/deepseek-v4.1-flash-1017` / Global）各发送一条 L1 合成非流式请求；两条响应均精确匹配 `phase0-probe-ack`。OpenRouter 报告下游 Provider `Relace`、区域 `HKG`。本轮输出未包含 token、费用或 DeepSeek 下游/区域元数据，故不补记这些值。
- 本次真实跨 Provider 证据证明在相同 Gateway 配置下可按请求 provider 顺序调用两家适配器；不是失败后的自动 fallback，也不证明真实 SSE、工具、结构化输出、错误路径或可重复性能。所有真实请求均由用户对当次显示的 Provider、model、区域和固定合成正文分别确认。OpenRouter 用户早先报告的一次余额不足失败已由后续成功请求补充；早期 Keychain 缺失错误也已解决。
- **DeepSeek SSE**：用户按 `probe_provider_capability_poc.py deepseek stream` 执行并输入本次精确确认。流式分块拼接后得到 `phase0-probe-ack`，精确匹配为 True。未提供 token/cost 或服务侧 Provider/region metadata；只证明 DeepSeek `deepseek-flash` 的一次真实流式合成文本成功，不代表 OpenRouter 或稳定性。
- **DeepSeek SSE 客户端取消**：用户输入 `ALLOW DEEPSEEK CANCEL 1` 后，收到首个文本片段 `phase`，客户端随即主动关闭 SSE。证明一次客户端侧中断路径运行；Provider 是否因此停止生成/计费未由响应或服务端记录证明。
- **OpenRouter SSE**：用户按 `probe_provider_capability_poc.py openrouter stream` 输入 `ALLOW OPENROUTER STREAM 1` 后，流式分块拼接得到 `phase0-probe-ack`，精确匹配为 True。未提供 token/cost 或流式 metadata；只证明 OpenRouter `deepseek/deepseek-v4.1-flash-1017` Global 的一次真实流式合成文本成功，不代表稳定性或其他能力。
- **OpenRouter SSE 客户端取消**：用户输入 `ALLOW OPENROUTER CANCEL 1` 后，收到首个文本片段 `phase0-probe-`，客户端随即主动关闭 SSE。证明一次客户端侧中断路径运行；Provider 是否因此停止生成/计费未由响应或服务端记录证明。
- **DeepSeek JSON**：首次用户确认后返回空正文、结构检查失败；该次旧 CLI 未打印 finish_reason/usage/路由 metadata，没有重试。增强诊断后第二、第三次用户分别确认，均返回 `{"phase0":"ack"}`，结构检查 True、finish_reason=`stop`，模型 `deepseek-flash`，tokens 分别为 68/46/114 与 68/28/96；下游 Provider、region、cost 未提供。三次观察为一次空正文、两次成功，说明此前空正文不是 API Key 错误的证据，且后续请求证明凭据可用；空正文原因仍未知，样本也不足以推断稳定性。
- **OpenRouter JSON**：用户输入 `ALLOW OPENROUTER JSON 1` 后返回 `{"phase0":"ack"}`，结构检查为 True，finish_reason=`stop`。实际模型 `deepseek/deepseek-v4.1-flash-1017`，下游 Provider `Relace`、区域 `HKG`；prompt/completion/total tokens=46/36/82，服务报告费用 USD `0.000018276`。只证明本配置的一次结构化输出成功。
- **DeepSeek 错误路径**：用户输入 `ALLOW DEEPSEEK ERROR 1` 后，对故意无效的 `response_format` 收到 HTTP 422；CLI 只输出状态码，未暴露响应正文/凭据。原 CLI 只认 HTTP 400，导致这次合理的 4xx 拒绝未被识别为预期路径；本轮已收紧为仅 HTTP 400/422 计作预期无效请求拒绝；401/402/403/429 不再被误报为该错误路径通过，并以 MockTransport 回归覆盖分类。该真实请求未输出费用 metadata。
- **OpenRouter 错误路径**：用户输入 `ALLOW OPENROUTER ERROR 1` 后，对同一故意无效 `response_format` 收到 HTTP 400；CLI 输出脱敏状态码并报告错误路径验证通过。两家各一次真实 4xx 拒绝，不等于所有服务错误类别已覆盖。此请求未输出费用或路由 metadata。
- **OpenRouter metadata 重复观察**：用户对 `metadata --repeat 2` 两条请求分别输入精确确认。两次响应均精确匹配；模型均为 `deepseek/deepseek-v4.1-flash-1017`，下游均为 Relace、区域均为 HKG。第 1 次 tokens=42/17/59，cost USD `0.000008752`；第 2 次 tokens=42/16/58，cost USD `0.000008252`。观察到路由与区域一致，费用差异与 completion token 数差异同时出现；样本仅两次，不据此推断定价公式或稳定性。
- **DeepSeek metadata 重复观察**：用户分别输入 `ALLOW DEEPSEEK METADATA 1`、`ALLOW DEEPSEEK METADATA 2`。两次模型均为 `deepseek-flash`，服务均未返回下游 Provider、区域或费用。第 1 次 tokens=42/29/71，响应未精确匹配；第 2 次 tokens=42/16/58，精确匹配。旧 CLI 未显示不匹配的实际正文，无法分析第 1 次差异；现已加入 JSON 字符串编码后的正文诊断，未自动重发。只证明模型标识与 token usage 可读取，不证明服务返回区域/计费 metadata 的能力。
- **DeepSeek 工具提案**：首次请求返回 HTTP 400。依据 DeepSeek 官方说明，thinking 默认启用且 named `tool_choice` 在 thinking mode 不受支持；脚本随后显式关闭 thinking，并由用户对更新后的完整 schema/payload 再次独立确认。第二次请求返回 `phase0_echo_synthetic`，参数为 `{"marker":"phase0-probe-ack"}`。提案只作为数据展示，未执行任何工具。该实测证明 DeepSeek `deepseek-flash` 在此配置下的一次工具提案成功；不证明 OpenRouter、执行安全或稳定性。
- **OpenRouter 工具提案**：前两次逐次确认后均返回空 proposal list（第二次普通文本也为空）。加入 finish_reason/路由诊断后，用户再次输入 `ALLOW OPENROUTER TOOLS 1`，第三次请求成功返回 `phase0_echo_synthetic`，参数为 `{"marker":"phase0-probe-ack"}`；finish_reason=`tool_calls`，实际模型 `deepseek/deepseek-v4.1-flash-1017`，下游 Provider `Relace`、区域 `HKG`。工具仅作为提案展示，未执行。此证据证明该固定配置的一次真实工具提案成功，不证明稳定性或执行安全；前两次空结果的原因仍未知。

## 尚未验收

- 两家真实 SSE 各有一次成功；DeepSeek 与 OpenRouter 工具提案各有一次成功且均未执行（OpenRouter 前两次曾为空）；两家 JSON 各有一次结构匹配成功，DeepSeek另有一次空正文；DeepSeek 服务侧费用/区域字段未返回；无 Consent 时 PID 级 OS socket 检查无活动 socket；客户端 SSE 取消探测已实现，本地测试证明关闭响应流；DeepSeek 已有一次首片段后客户端取消结果，OpenRouter 取消待测；两家 Provider 是否停止生成/计费未由服务侧证实。DeepSeek JSON 重复一致性仍待观察。能力矩阵 CLI 已准备，每个外发请求仍须用户逐次确认。PID 级 lsof 是活动 socket 快照，不是完整包级证明；用户提供的全局 tcpdump 流量未按 PID 过滤，无法归因。Provider 响应元数据仍只有少量观测，不能视为稳定性或性能证据。
- 本 POC 未实现长期授权存储、交互式产品 Consent UI、持久审计、费用硬限制或产品级 Keychain 生命周期。
- D-010 仍为 Deferred：两家是本次 POC 候选，不自动构成 V1 Provider 选型。
