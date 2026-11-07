# 阶段 0 POC：本地 Embedding 候选（工作包 0G）

状态：`IN_PROGRESS`；只有接口/算法单测通过，真实模型检索 POC 未完成。未选择 V1 默认模型。

## 候选与边界

- 暂用 FastEmbed `0.9.1`，候选模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。FastEmbed 列为 384 维、多语言、约 0.22 GB；模型卡列出 50 种语言、Apache-2.0。它只是待评估候选，不是架构决策。
- `FastEmbedCandidate` 仅允许注册的候选 ID；权重缓存强制位于 `backend/.poc-data`；`local_files_only=True` 是默认值，只有显式 `allow_download=True` 才尝试下载。
- `LocalEmbeddingSearch` 仅在内存运行合成样本，提供来源追踪、cosine ranking 和 source 删除；没有数据库持久化、云推理或静默 fallback。
- 用户模型目录没有被扫描或修改；现有 Ollama 目录不在项目允许操作范围内，因此没有读取其模型文件。

## 已测试

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_local_embedding_poc.py
```

- 候选单测 7 项通过，覆盖来源检索、cosine 排序、派生向量删除、零向量/维度错误、模型白名单、项目缓存范围、提供商输出校验。
- 当前全部本机 Python 测试（`phase0-security` + `phase0-embedding` extras）42 项通过；compileall、`uv lock --check` 通过。Swift 全量测试 12 项通过。
- 真实模型权重下载尝试 74 秒后仍只有 5 个文件中的 3 个完成，两个权重文件保持 0 字节 `.incomplete`；为避免无限等待已中止。中断产物已清理。
- 没有产生真实 embedding、没有跑合成检索准确性评估，也没有性能数据。

## 未解决/未验收

- 真实 FastEmbed 模型在本机初始化、中文语义检索质量、内存/CPU/冷启动和离线重启加载都未验证；实际请求样本仍为脚本内合成 fixtures。
- 本地模型安装需要完整的权重缓存；当前 Hub 传输未完成，原因未确定。可保留 FastEmbed 作为可选 extra，不得宣称真实 embedding 已验证。
- 模型维度、Embedding 版本迁移和与 SQLCipher memory schema 的集成仍需确定性 POC；产品默认模型选择继续待决策。
