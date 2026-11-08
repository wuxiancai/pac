# 阶段 0 POC：真实 Provider 探测准备（工作包 0C）

状态：`IN PROGRESS`。固定目标 adapter、Keychain reader、一次性终端授权入口已实现。用户已分别对 DeepSeek 与 OpenRouter 完成一次经逐次确认的合成文本真实请求；更广的能力矩阵与跨 Provider 切换仍未验收。

## 用户确认与固定范围

- 用户指定两个测试候选：DeepSeek、OpenRouter。
- 用户确认 DeepSeek 按中国处理，OpenRouter 使用 Global 路由。DeepSeek 官方隐私政策称其服务数据在中国处理；OpenRouter 默认 `openrouter.ai` 为全球路由，US/EU in-region routing 另需 Business/Enterprise 账户条件。见 [DeepSeek 隐私政策](https://cdn.deepseek.com/policies/en-US/deepseek-privacy-policy.html?os=v0)、[OpenRouter US/EU in-region routing](https://openrouter.ai/business/eu/)。
- 本 POC 固定使用 DeepSeek `deepseek-flash`、`https://api.deepseek.com/chat/completions`（[官方模型/API 文档](https://api-docs.deepseek.com/api/create-chat-completion)）；OpenRouter `deepseek/deepseek-v4.1-flash-1017`、`https://openrouter.ai/api/v1/chat/completions`（[官方模型目录](https://openrouter.ai/deepseek)）。模型和费用可能变化，真实请求前应按官方当前账号目录再次确认。
- 唯一探测正文为 `Reply with exactly this text: phase0-probe-ack`，L1 合成文本，最多 64 output tokens；只执行一次非流式 chat-completions 请求，不带工具、不重试。OpenRouter Global 初始选择一个符合条件的上游端点，adapter 设置 `provider.allow_fallbacks=false` 禁止跨 Provider 故障切换；请求启用路由 metadata，并输出实际选择的 Provider、服务区域、token 用量和服务报告的 USD cost（如 API 返回）。

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

## 已验证（仅本地 MockTransport）

- 默认拒绝发生在 Keychain 读取和 adapter 网络调用之前。
- 精确授权后 adapter 才从凭据接口取密钥；HTTP header/body 与固定 model/endpoint 匹配。
- OpenRouter Global SSE streaming 分块解析；非流式响应 metadata 可报告实际选择的上游 Provider/region、token 数和 cost；请求禁用跨 Provider failover；tool call 仅作为 `ToolCallResult` 数据返回，不执行工具。
- JSON `response_format` 透传；Provider 非 2xx 错误只暴露 HTTP 状态，不保留 response body；端点/model/region 配置均固定 allowlist。
- Keychain reader 只允许 `deepseek` / `openrouter` 两个 account，CLI 参数不包含秘密，缺失/拒绝读取错误不暴露原始 stderr。
- 窄回归命令：`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_remote_providers_poc.py tests/test_local_model_gateway.py tests/test_consent_aware_gateway.py`；当前 **28 passed**。拒绝确认路径另外在本机子进程运行，断言退出码 2 且提示未读 Keychain/未发送请求。这些都是本地测试，不是 Provider 端到端证据。
- 当前全量 Python：`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security --extra phase0-embedding --group dev pytest -q`：**139 passed**。`compileall`、`uv lock --check` 均通过；macOS Swift Testing `swift test`：**27 passed**。

## 用户实机真实请求结果（2026-11-08）

- **DeepSeek**：用户在 CLI 输入 `ALLOW DEEPSEEK` 后发送一条 L1 合成文本请求，返回 `phase0-probe-ack`，与期望文本完全匹配。实际模型 `deepseek-flash`；token 用量 prompt 42 / completion 41 / total 83。服务未返回下游 Provider、区域或费用信息。
- **OpenRouter Global**：用户在 CLI 输入 `ALLOW OPENROUTER` 后发送一条 L1 合成文本请求，返回 `phase0-probe-ack`，与期望文本完全匹配。实际模型 `deepseek/deepseek-v4.1-flash-1017`；下游 Provider `Relace`、服务区域 `HKG`；token 用量 prompt 42 / completion 17 / total 59；报告费用 USD 0.000008752。
- 两次请求均由用户在运行时对显示的 Provider、model、区域和固定合成正文逐次确认。仅证明各自一次非流式文本请求成功；不证明真实 SSE、工具、结构化输出、错误路径、跨 Provider 自动切换或可重复性能。OpenRouter 用户早先报告的一次余额不足失败已由后续成功请求补充；早期 Keychain 缺失错误也已解决。

## 尚未验收

- 真实费用、模型/区域可用性、错误码、实际 SSE、工具 schema、结构化输出、拒绝/撤销出站边界、同内容跨 Provider 切换尚未充分验证。Provider 响应元数据只采集到上述各一次；MockTransport 能力不能作为供应商能力证据。
- 本 POC 未实现长期授权存储、交互式产品 Consent UI、持久审计、费用硬限制或产品级 Keychain 生命周期。
- D-010 仍为 Deferred：两家是本次 POC 候选，不自动构成 V1 Provider 选型。
