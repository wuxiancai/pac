# 阶段 0 POC：Gateway 云请求 Consent/Policy 门禁

状态：`IN_PROGRESS`。该包验证远端调用的本机授权边界；没有真实 Provider adapter，也没有发起云请求。

## 契约

- `LocalModelRequest` 携带 provider、model、region、purpose 和 `DataLevel`。远端请求未提供 region/purpose 时拒绝。
- `ConsentAwarePolicy` 对本机 adapter 放行；对远端 adapter 构造 `OutboundRequest` 并调用 `OutboundPolicy`。Adapter 只有在 Gateway 通过授权后才会被调用。
- Consent 需精确匹配 provider/model/region/purpose/data level 且尚未过期；撤销后下一次请求拒绝。L3 由既有 `OutboundPolicy` 无条件拒绝。
- `LocalOnlyPolicy` 继续服务本机 POC 的严格本机模式，不改变默认策略。

## 自动化验证

测试用 fake remote adapter 计数，不发网络请求：

- 无 Consent 的 generate 和 stream 在 adapter 调用前拒绝。
- 缺少 region/purpose、provider/model/region/purpose/data level 任一不匹配、L3 和撤销后请求均拒绝。
- 精确匹配且有效的 L1 Consent 才允许进入 fake adapter。

命令：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_consent_aware_gateway.py
```

当前该测试文件 11 项通过。实际 HTTP provider、Keychain 取凭据、审计持久化、Consent UI、并发撤销取消请求、费用/区域核验尚未接入或测试；此契约测试不是 Provider E2E 证据。

## 安全边界

调用仍需 `ModelGateway` 统一路由；未授权时没有适配器网络路径。此 POC 不持有或读取 API Key，不创建 Consent，也不更改默认拒绝策略。API Key 仍只能经 Keychain 凭据写/删/状态 API 管理。
