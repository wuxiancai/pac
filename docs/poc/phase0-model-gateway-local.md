# 阶段 0 POC：本机 Model Gateway 契约（工作包 0C）

状态：`IN_PROGRESS`。这是本机、无外网调用的接口 POC，不是供应商端到端验证，也不代表阶段 0 或 V1 验收通过。

## 范围

- 提供统一的文本生成与流式文本接口。
- 通过 Provider key 路由到不同适配器；fake local adapters 用于契约隔离测试。
- Ollama Adapter 只允许 HTTP loopback URL，并调用本机 `/api/chat`。
- `LocalOnlyPolicy` 在适配器调用前拒绝非本地 Provider。
- 独立工作包新增 `ConsentAwarePolicy`：对远端 adapter 要求精确、未过期、未撤销的 Consent 和 Policy；该测试使用 fake adapter，不发起网络请求，详见 `phase0-consent-aware-gateway.md`。
- 没有云 Provider、Key、Fallback、工具调用、预算/费用归一或 Consent UI；没有任何请求离开本机。

## 本机实际验证

- Ollama 服务：本机 `127.0.0.1:11434`。
- 模型：`qwen3.5:0.8b`，由本机 Ollama 管理，未在本次工作中下载模型。
- 非流式调用从本机 Gateway 返回“只回复：本机 Gateway 正常”。
- 流式调用由 Gateway 汇集本机 Ollama delta，返回“正常”。
- 未记录性能数字；冷启动响应时间不作为性能承诺。

## 自动化测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q
```

- 全量 Python 测试：17 项通过。
- 两个本地适配器可用相同请求契约独立路由。
- 非本地适配器在调用前被拒绝。
- Gateway 的非本地流式请求在打开 adapter stream 前拒绝；关闭下游 stream 会关闭 adapter 的 async generator，避免本地流在消费者取消后继续占用资源。此项由本地契约测试验证，不代表每个供应商都支持远端请求取消。
- Ollama JSON 响应和 NDJSON 流事件可标准化。
- 公网/非 loopback Ollama URL 被构造器拒绝。

## 未解决/未验收

- v1.2 阶段 0 所要求的 2–3 家真实 Provider 文本、流、工具、JSON、区域、价格、错误和取消验证未做。本轮“本机开发/测试/使用”约束下只做本地验证。
- 未比较 LiteLLM/Bifrost/Portkey，也未形成 ADR。
- Provider capability registry 已在单独的 POC 报告实现；本地 Gateway 现有取消语义只验证了本地 async stream 的关闭传播，未实现/验证远端供应商取消、usage/cost、重试或 fallback。
- 云端 Provider 在 Consent Manager、Policy Engine 及用户授权流程完成前保持不可用。

## 安全/范围边界

ASR/TTS/LLM 独立配置不变；本 POC 仅接入本机 Ollama。V1 仍只有一个总助理；不包含 Agent 团队、后台任务、连接器、外部写操作、任意 shell 或任意文件访问。
