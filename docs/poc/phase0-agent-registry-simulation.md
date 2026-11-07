# 阶段 0 POC：Agent Registry 与结果协议模拟（工作包 0C）

状态：`IN_PROGRESS`。此工作包只验证可扩展接口及权限继承边界；不实现或运行 Agent 团队，也不改变 V1 的单一总助理范围。

## 范围与设计

- `AgentDefinition` 保存标识、模型绑定、权限集合及是否为 POC 模拟条目。
- Registry 强制存在唯一 `main_assistant` 产品定义；其他条目必须显式标为模拟，且不产生产品 Agent run。
- `AgentResult` 以有限状态承载摘要、证据、产物、警告和限制。
- 子项权限仅取父权限与请求权限的交集。
- 没有 Agent Router、并发执行、后台任务、队列、工具调用或外部连接器。

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_local_agent_poc.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q
```

- 工作包测试：4 项通过。
- 全量 Python 测试：21 项通过。

## 未解决/未验收

- 本模拟仅证明注册与结果/权限契约；不是多 Agent 功能验收。
- 具体 Agent 扩展策略仍受 v1.2 的 V1 单总助理边界约束；不在本 POC 内作产品决策。
- 阶段 0 及 V1 均未验收。
