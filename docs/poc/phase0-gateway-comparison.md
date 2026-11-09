# 阶段 0 POC：开源 Gateway 对照（工作包 0J）

状态：`PARTIAL`。本报告对照规格书和 V1.1 列明的 LiteLLM、Bifrost 与 Portkey；只使用官方文档/仓库进行桌面研究，没有安装、运行或向这些 Gateway 发请求。第三方 Gateway 运行依赖仍未定案；2026-11-09 用户确认 ADR-020：V1 使用项目自有轻量 ModelGateway，不引入第三方 Gateway 运行依赖；本报告作为后续重新评估的参考，不替代 POC-02 的 Provider E2E。

## 评估范围与安全门槛

本项目当前 Model Gateway 是项目内 Python 模块；云出站先经 Consent Manager 与 Policy Engine，默认拒绝；API Key 仅来自 macOS Keychain；L3 不得进入普通模型 API。外部 Gateway 的虚拟密钥、预算、Guardrail 或审计能力不能替代本地授权判断，也不能自行开通出站路径。V1 仅一个总助理；不启用外部连接器、后台队列或工具执行扩展。

用户已说明本机是软件开发、测试和运行设备，未来可由本机软件访问云 Provider。此比较因此评估同一台 Mac 上的开发/运行可行性，不将“本机”误解为禁止云请求；真实云请求仍需逐次符合现有 Consent/Policy 门禁和凭据规则。

## 官方资料观察

| 方案 | 官方资料显示的形态 | 对本项目可能有用的部分 | 集成与边界成本 / 未验证项 |
|---|---|---|---|
| LiteLLM | Python SDK + 可独立运行的 Proxy/Gateway；其 Proxy 请求链包括鉴权/预算、限流、Router、Provider 翻译和异步用量日志。Proxy 的 auth/spend tracking 需要数据库；多实例限流/路由状态使用 Redis。 | Python 接口与现有 FastAPI/Pydantic 后端相邻；适合对照 Adapter 翻译、能力覆盖、路由与费用字段。 | Proxy 会增加服务/依赖及其独立 auth、配置和日志面；必须证明请求在到达 LiteLLM 前由本项目门禁裁决、不会绕过 L3 拒绝，且供应商凭据不会迁入普通配置/数据库。仅以 SDK 使用也需评估依赖面和数据日志。当前没有本项目运行或版本/许可审查。 |
| Bifrost | 官方仓库/文档将其描述为 Go Gateway，并提供 Go SDK；网关有统一 API、路由、fallback、virtual key、预算/限流和日志内容控制。官方安装指南支持本机 npx binary 或 Docker。 | 可比较独立 Go 进程的数据面隔离、统一接口、重试/fallback 和按内容关闭日志；其官方文档对日志元数据与内容分层有明确描述。 | 会增加 Go/NPX 或容器运行时、进程生命周期和本地配置面。必须确保 fallback 永不扩大数据等级、Provider/region 或预算权限；还须实测禁用内容日志是否覆盖每个 sink，以及 Keychain/Consent 接口是否可保持在应用边界。官方性能数字是供应商基准，不作为本项目测量。 |
| Portkey Gateway | 官方仓库提供本机 Node/npm 启动方式、OpenAI 兼容 API、重试/fallback/路由与 Guardrail 示例；仓库将 Gateway 2.0 标为预发布，并说明企业 Gateway 能力并入开源的方向。 | 可参考轻量本机运行、配置化可靠性策略与 Guardrail Hook 的设计；符合原架构所定“参考对象”。 | 需核实稳定版本与 2.0 预发布功能边界、开源与托管/企业能力边界，并评估 Node/npm 运行时和 Console/日志面。其 Guardrail 不能代替本地 Consent/Policy，也不可据此判断本地数据等级。没有做版本 pinning 或运行验证。 |

## 对项目接口的影响评估

1. 保留项目自己的 `ModelGateway`、Provider Adapter、Capability Registry、Consent/Policy 和审计契约作为应用边界。即便后续选第三方 Gateway，也只能作为被适配的内部传输组件；不能由它自行判定 Consent 或数据等级。
2. Provider/API Key 继续只通过 Keychain 出入。不得因第三方产品的密钥存储配置方便而将 API Key 放进普通 YAML、数据库、环境文件或日志。
3. Gateway 返回的 capability 仍须按 `(provider_id, model_id)` 有证据地登记；未知即拒绝。任何重试/fallback 必须复核原始授权的 Provider、模型、区域、用途、数据等级和费用上限。
4. 只记录规格要求的 usage 元数据；提示词、音频、工具参数和响应内容默认不持久化。若候选工具无法关闭/隔离内容日志，或无法阻止未经授权的外发，则不满足项目边界。
5. V1 当前无任意工具执行或外部写操作。第三方 Gateway 中的 MCP、Agent、插件、连接器等能力不属于本次评估范围，不得启用。

## 桌面评估结论（非架构定案）

- LiteLLM 是 Python 接口/代理能力的主要对照；其独立 Proxy 带来的数据库、部署和安全配置面需要以真实集成实验量化。
- Bifrost 是独立 Go 网关及治理/日志分层的对照；本地进程额外成本和权限门禁可组合性需实际验证。
- Portkey 只按基线作为参考对象；预发布与托管/企业边界要求先固定版本再评估。
- 目前没有证据表明任一候选能降低本项目维护成本且不削弱 Consent/Policy/Audit。维持 V1.1 当前文字中的自建项目 Gateway 方案；这仅是基线重述，不是本工作包新作的选型决策。
- `ADR-020` 已 `Accepted`：V1 不安装或运行第三方 Gateway，继续用项目自有轻量 ModelGateway。若后续重新评估第三方运行依赖，应新增决策和迁移/安全证据。本报告没有安装软件或发起出站请求。

## 后续验证计划

- 锁定候选的稳定 tag/commit 与许可证，再在本机隔离环境中测进程启动/关闭、资源、流式取消、结构化输出、工具提案（不执行）、错误映射和 usage 元数据。
- 使用 fake provider 先验证 Consent/Policy 位于不可绕过的调用路径，并覆盖 L3、超时、撤销、fallback 目标不匹配、日志脱敏；通过后才评估真实 Provider 请求。
- 真实 Provider 实测须使用合成数据、明确 Consent/Policy、Keychain 凭据、已核验区域和费用上限。无授权时须能证明请求未抵达任何网络 adapter。
- 不用本报告中的供应商自报性能或功能清单替代本机测量与契约测试。

## 来源（第一方）

- LiteLLM [Request architecture](https://docs.litellm.ai/docs/proxy/architecture)、[Authentication](https://docs.litellm.ai/docs/proxy/authentication)、[Deployment dependencies](https://docs.litellm.ai/docs/proxy/deploy)、[repository](https://github.com/BerriAI/litellm)。
- Bifrost [Overview](https://docs.getbifrost.ai/overview)、[local setup](https://docs.getbifrost.ai/quickstart/gateway/setting-up)、[Virtual Keys](https://docs.getbifrost.ai/features/governance/virtual-keys)、[Content Logging](https://docs.getbifrost.ai/features/observability/content-logging)、[repository](https://github.com/maximhq/bifrost)。
- Portkey [Gateway repository README](https://github.com/Portkey-AI/gateway)。

## 验证记录

- 依据以上官方页面进行人工资料核对；未安装第三方软件、未发出 Provider 请求。
- 自动化文档契约测试：`cd backend && UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_gateway_comparison_report.py`。
- 测试只保证基线候选、安全边界、Deferred 状态及第一方来源链接留在报告中，不代表 Gateway 集成已经验证。
