# 阶段 0 POC：记忆仓库的可选本地 Embedding（工作包 0D/0G）

状态：`PARTIAL`。本工作包仅把固定 revision 的 FastEmbed 候选通过可注入 provider 接入 disposable in-memory `MemoryStore`，验证来源追踪、纠错、删除和恢复；不是产品数据库 schema、模型 ADR 或记忆质量验收。

## 设计边界

- `MemoryStore` 默认不配置 embedding provider，原有 FTS 搜索行为不变。只有构造时显式传入 provider 才会生成向量并启用 `search_semantic`；未配置时语义检索明确报错，不静默切换到 FTS。
- provider 的 `model_id` 作为派生向量索引键；向量只写入该 POC 自建的 `:memory:` SQLite `memory_embeddings` 表。没有修改产品 schema，也没有新增/运行 Alembic migration。
- 语义结果仍返回 memory ID、claim 类型和来源 ID，并按 cosine similarity 排序。只查询 `active` 记忆和当前 provider 的模型 ID。
- correction 在生成新向量成功后才变更旧记录；事务内 supersede 旧记忆、删除旧 FTS/embedding 派生项并写入新记录/向量。删除同样清除 FTS 与 embedding 索引。
- `restore_bytes` 需要调用方再次显式传入 provider；provider 不序列化进备份，也不自动下载模型。
- ASR/TTS/LLM 配置和网络策略不受影响。此 POC 不调用模型 Gateway，不联网，不接收用户记忆。

## 测试证据

- 单元/契约测试覆盖默认未配置时 fail closed、source evidence、语义排序、纠错替换旧向量、删除清理派生向量、provider 错误时保留旧 active 记忆/向量，以及显式 provider 下备份恢复。
- 固定模型本机离线集成命令：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp \
HF_HOME=.poc-data/hf-home HF_HUB_CACHE=.poc-data/hf-home/hub \
XDG_CACHE_HOME=.poc-data/xdg-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
uv run --locked --extra phase0-embedding python scripts/evaluate_memory_embedding_poc.py
```

- 2026-11-08 扩展固定合成案例后，离线运行输出只含聚合统计：`memory_count=4`、`query_count=4`、`top1_matches=4`、`source_evidence_returned=true`、`query_or_memory_text_logged=false`。四组覆盖中文回复偏好、编程语言、周末爱好和工作城市。小型合成集的一次 4/4 结果不代表真实用户数据质量、稳定检索率或性能指标。
- 测试命令：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp \
uv run --locked pytest -q tests/test_memory_store_poc.py tests/test_memory_embedding_evaluation.py
```

## 未解决/未验收

- 产品默认 Embedding 型号、许可、CPU/RSS/延迟目标、语言覆盖及是否启用仍未决；当前 provider 是显式注入的 POC 候选。
- 合成检索集仍很小；未使用真实用户数据或有标注的代表性查询集，也未形成 Recall@k、稳定性能分布。
- 没有持久化 repository、SQLCipher/Alembic 产品 schema、索引重建/模型升级迁移或长期故障恢复验证。
- 阶段 0 仍未验收，阶段 1 未开始。
