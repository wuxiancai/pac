# 阶段 0 POC：真实 Provider 探测准备（工作包 0C）

状态：`IN PROGRESS`。固定目标 adapter、Keychain reader、一次性终端授权入口已实现。用户已分别尝试 DeepSeek 与 OpenRouter 探测，两次均在 Keychain 凭据查找阶段失败，尚未发送真实 Provider 请求。

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

## 尚未验收

- 两次 Keychain 凭据查询均未取得密钥；尚未发生 DeepSeek 或 OpenRouter 网络请求。需要先核对 login 钥匙串中的服务名和账户名是否完全匹配上表。
- 真实费用、模型/区域可用性、错误码、实际 SSE、工具 schema、结构化输出、Usage 统计、同内容跨 Provider 切换尚未验证。当前 `ModelGateway` 文本适配路径只验证计划中的单次合成文本探测；MockTransport 能力不能作为供应商能力证据。
- 本 POC 未实现长期授权存储、交互式产品 Consent UI、持久审计、费用硬限制或产品级 Keychain 生命周期。
- D-010 仍为 Deferred：两家是本次 POC 候选，不自动构成 V1 Provider 选型。
