# 阶段 0 POC：长期记忆存储（工作包 0D）

状态：`IN_PROGRESS`。验证使用进程内 SQLite 临时库；不是产品 schema，不落盘，也未创建 Alembic migration。产品数据库仍必须经 SQLAlchemy/Alembic 建立，并配套备份和回滚说明。

## 本工作包覆盖

- SQLite FTS5 关键词检索，返回原始内容及来源 ID。
- 结构化字段记录 claim 类型、观察时间和生命周期状态；支持事实纠错版本链。
- 纠错后停用旧事实并从全文/向量派生索引移除；删除会从检索、FTS 和 POC 向量表清理。
- 通过 SQLite 内存序列化/反序列化完成同进程备份恢复演练。
- SQLite 默认 FTS tokenizer 没有满足本轮连续中文文本检索测试；POC 加了轻量中文双字索引适配。此算法不是正式产品分词决策。

## 测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_memory_store_poc.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc tests
```

- 先写测试；初次执行因实现缺失而失败。实现后工作包测试 4 项通过。
- 全量 Python 测试 25 项通过；compileall 通过。
- 这里的 Embedding 行使用测试 fixture 向量验证派生索引清理。真实候选下载状态见 `docs/poc/phase0-local-embedding.md`；尚无真实模型向量用于检索验证。

## 未解决/未验收

- 本地多语言 Embedding 候选权重未成功下载；中文语义记忆检索及模型资源占用未验证。
- 冲突发现策略、正式 Schema、敏感级别、时间有效语义、派生数据全生命周期和备份加密尚未确定。
- 恢复演练仅覆盖同一进程内存序列化，未覆盖加密备份、进程重启或磁盘故障。
- 本工作包和阶段 0 均未验收；不可用于产品数据。
