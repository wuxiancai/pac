# 阶段 0 POC：逐型号能力注册表（工作包 0I）

状态：`IN_PROGRESS`。此实现验证 capability evidence 的数据契约，不宣称完成 POC-02 多供应商能力验收。

## 契约

- 键必须精确为 `(provider_id, model_id)`；不会按品牌、模型家族或 OpenAI 兼容格式推导能力。
- 能力包含文本、流式、工具/并行工具、JSON Schema、视觉、音频输入/输出、Embedding、rerank、实时音频、batch、取消。
- 未登记模型或未登记能力返回 `UNKNOWN`；明确负向证据可登记 `UNSUPPORTED`；所有支持结论必须带验证时间和证据引用。
- `require` 只允许 `SUPPORTED`；`UNKNOWN`、`UNSUPPORTED`、`LIMITED` 均拒绝当前能力执行。
- 不改变 Gateway Adapter、调用路由或数据库，不增加工具执行功能。

## 当前真实本机证据边界

- `ollama-local / qwen3.5:0.8b` 有本地文本生成与流式 smoke 记录（见 `phase0-model-gateway-local.md`）。这只支持把文本和流式登记为候选已验证能力。
- 工具调用、并行工具、严格 JSON Schema、vision/audio、Embedding、rerank、取消、区域、费用及供应商数据政策都仍是 `UNKNOWN`，不能用于产品决策或费用估算。
- Fake provider 测试只验证应用契约，不证明任何具体模型支持上述能力。

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_model_capability_registry_poc.py
```

- 4 项通过：默认未知、精确型号匹配、明确不支持与未知区分、支持结论需要证据、重复记录拒绝。
- 当前全量 Python 测试（含安全/SQLCipher 与 Embedding extras）48 项通过；compileall、`uv lock --check` 通过。
- 本工作包没有远程 Provider 调用。

## 未解决/未验收

- POC-02 的 2–3 家供应商端到端能力矩阵、费用/错误/取消和 Gateway 开源方案比较尚未完成；本机使用边界下不调用云端供应商。
- Registry 目前是进程内 POC；未持久化、未绑定模型配置 UI，也未由 Gateway `generate/stream` 自动消费。
- Gateway 能力差异仍需由后续实现按能力拒绝/降级并重新验证 Consent/Policy；任何 fallback 不得扩大数据范围或费用权限。
