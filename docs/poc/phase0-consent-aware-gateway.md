# 阶段 0 POC：Gateway 云请求 Consent/Policy 门禁

状态：`IN_PROGRESS`。该包验证远端调用的本机授权边界；没有真实 Provider adapter，也没有发起云请求。

## 契约

- `LocalModelRequest` 携带 provider、model、region、purpose、`DataLevel` 和来源界面。远端请求未提供 region/purpose/source 时拒绝。
- `ConsentAwarePolicy` 对本机 adapter 放行；对远端 adapter 构造 `OutboundRequest` 并调用 `OutboundPolicy`。Adapter 只有在 Gateway 通过授权后才会被调用。
- Consent 需精确匹配 provider/model/region/purpose/data level/action/source 且未过期、状态为 ACTIVE；撤销会保留 REVOKED 状态、阻止后续请求，并尽可能取消以该授权登记的在途 Gateway task。操作类型由 Gateway 调用入口派生，调用方不能自行声明。L3 由既有 `OutboundPolicy` 无条件拒绝。
- `LocalOnlyPolicy` 继续服务本机 POC 的严格本机模式，不改变默认策略。

## 自动化验证

测试用 fake remote adapter 计数，不发网络请求：

- 无 Consent 的 generate 和 stream 在 adapter 调用前拒绝。
- 缺少 region/purpose/source、provider/model/region/purpose/data level/source 任一不匹配、action 不匹配、L3、过期和撤销后的请求均拒绝。
- generate grant 不授权 stream/tool proposal，stream grant 不授权 generate；显式 stream grant 才允许流式请求进入 fake adapter。
- 精确匹配且有效的 L1 Consent 才允许对应操作进入 fake adapter；撤销状态保留并可检查。
- 在 fake adapter 的 generate 与 stream 挂起期间撤销 Consent，会取消当前 asyncio task；同一精确 Consent 下多个并发 generate 也都会被取消；stream 路径同时关闭 adapter async iterator。后续新请求仍被拒绝。

命令：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_consent_aware_gateway.py
```

窄回归：`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_consent_aware_gateway.py tests/test_remote_providers_poc.py tests/test_security_poc.py` → 50 passed。新增同一精确 Consent 下两个并发挂起 generate 同时被撤销取消。2026-11-09 全量：`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 183 passed，1 条既有 Starlette/httpx 弃用警告。并发撤销仅由 fake adapter 验证；已发出的请求数据无法撤回，Provider 侧停止生成/计费语义也未被证明。审计持久化、Consent UI、真实 Provider 出站门禁和费用/区域核验仍未闭环；契约测试不构成 Provider E2E 证据。

## 安全边界

调用仍需 `ModelGateway` 统一路由；未授权时没有适配器网络路径。此 POC 不持有或读取 API Key，不创建 Consent，也不更改默认拒绝策略。API Key 仍只能经 Keychain 凭据写/删/状态 API 管理。
