# 阶段 0 POC：本地 Embedding 候选（工作包 0G）

状态：`PARTIAL`；候选接口测试及扩展后的离线真实模型合成检索已完成。D-014 要求先离线候选评测，再决定产品启用；本报告结果不构成选型或产品验收。

## 候选与边界

- 暂用 FastEmbed `0.9.1`，候选模型 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`。FastEmbed 登记为 384 维、多语言、约 0.22 GB；此候选不是架构决策。
- `FastEmbedCandidate` 仅允许注册的候选 ID；权重缓存强制位于 `backend/.poc-data`；`local_files_only=True` 是默认值，只有显式 `allow_download=True` 才尝试下载。
- `LocalEmbeddingSearch` 仅在内存运行合成样本，提供来源追踪、cosine ranking 和 source 删除；没有数据库持久化、云推理或静默 fallback。
- 用户模型目录没有被扫描或修改；现有 Ollama 目录不在项目允许操作范围内，因此没有读取其模型文件。

## 权重来源和完整性

- 模型仓库：`Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q`；revision：`faf4aa4225822f3bc6376869cb1164e8e3feedd0`。
- ONNX `model_optimized.onnx`：235,052,644 bytes；SHA-256 `634d0f66c29dc934c8fa72b8a4fe91dd4d420a22f1d82a241058d4316e659a99`。
- `tokenizer.json`：17,083,009 bytes；SHA-256 `fa685fc160bbdbab64058d4fc91b60e62d207e8dc60b9af5c002c5ab946ded00`。
- `unigram.json`：14,763,260 bytes；SHA-256 `da145b5e7700ae40f16691ec32a0b1fdc1ee3298db22a31ea55f57a966c4a65d`。
- 文件大小和 SHA-256 均与 revision 元数据预期精确匹配；下载 staging 和 Hugging Face cache 都位于 `backend/.poc-data`。
- 最后一个 20 MB curl 范围段多次重试会重写该段输出，观察到字节长度回退；该不完整尝试保留为 `onnx-09.failed-attempt.part`，没有用于组装。将该范围拆为 20 个独立的 1 MB 请求，每段长度验证通过后组装；整体 ONNX SHA-256 再次通过。

## 已测试

接口/算法测试：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_local_embedding_poc.py
```

- 候选单测 7 项通过，覆盖来源检索、cosine 排序、派生向量删除、零向量/维度错误、模型白名单、项目缓存范围、提供商输出校验。

本地真实权重合成检索（不带 `--download-model`，且候选默认 `local_files_only=True`）：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp \
HF_HOME=.poc-data/hf-home HF_HUB_CACHE=.poc-data/hf-home/hub \
XDG_CACHE_HOME=.poc-data/xdg-cache \
/usr/bin/time -l uv run --locked --extra phase0-embedding \
  python scripts/run_local_embedding_eval.py
```

完全离线环境变量下的二次加载：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp \
HF_HOME=.poc-data/hf-home HF_HUB_CACHE=.poc-data/hf-home/hub \
XDG_CACHE_HOME=.poc-data/xdg-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/usr/bin/time -l uv run --locked --extra phase0-embedding \
  python scripts/run_local_embedding_eval.py
```

两次执行均返回 4 个合成 query 全部 top-1 命中（`top1_matches=4/4`；脚本原始字段为 `top1_matches=4`）。第一次记录 1.95 秒 real、851,804,160 bytes 最大 RSS；offline 环境下的第二次记录 1.54 秒 real、868,909,056 bytes 最大 RSS。以上为两次单次进程级观察，不是稳定基准。

2026-11-07 再执行三次独立离线进程：三次均 4/4 top-1；real time 分别 1.19、0.81、0.81 秒；最大 RSS 分别 883,490,816、883,261,440、883,130,368 bytes。三次执行均设置 `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`，不下载权重。这仍是 4 条合成 query，不构成真实检索质量或产品资源验收。

检索集只有 4 条人工构造记忆和 4 个对应 query。该 top-1 结果不能外推到真实用户记忆、中文或多语言召回率、一般排序质量、长时间运行或产品性能门槛。记录 RSS 是这两次命令的 observed max RSS，产品资源目标尚未确认。

新增文档契约测试：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_embedding_report.py
```

## 未解决/未验收

- 需要真实、有代表性的中英文记忆/query 标注集与重复测量，才能评价 Recall@k、排序、CPU/RSS、冷启动和资源目标；当前用户数据没有参与。
- 尚未与持久 memory repository/SQLCipher schema 集成，也未评估模型版本变化、embedding 重算和索引迁移。
- 产品 Embedding 型号、格式/维度、保留策略和默认实现继续待决策；FastEmbed 仅可选候选，不得因为合成命中而默认选型。
- 2026-11-07 对照 pinned revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0` 的 [Qdrant 模型卡](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/tree/faf4aa4225822f3bc6376869cb1164e8e3feedd0) 和上游 [Sentence Transformers 模型卡](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)：两者均标注 Apache-2.0。当前安装 FastEmbed 0.9.1 的本地包 metadata 也标注 Apache-2.0。Python 锁定依赖 SBOM 于 2026-11-09 更新，覆盖 55/55 个非根锁定依赖，见 [`phase0-python-sbom.md`](phase0-python-sbom.md)；许可证闭包仍有缺项，SBOM 不构成法律审查或产品选型批准。


## 2026-11-10 离线扩展候选评测

D-014 的用户决定允许先进行离线候选评测，但不自动批准产品启用。本次把检索脚本扩展为 12 条人工合成的中英记忆及 24 条独立改写查询（中、英文各 12 条），按 cosine 排序记录 top-1/top-3，并区分查询语言。语料全部为合成主题，不包含真实用户记录。

命令（`backend/`）：

```bash
UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp \
HF_HOME=.poc-data/hf-home HF_HUB_CACHE=.poc-data/hf-home/hub \
XDG_CACHE_HOME=.poc-data/xdg-cache HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
/usr/bin/time -l uv run --locked --extra phase0-embedding \
  python scripts/run_local_embedding_eval.py
```

运行三次独立离线进程，结果均为 top-1 **23/24**、top-3 **24/24**；中文查询 top-1 为 **12/12**，英文为 **11/12**。唯一 top-1 错排是英文“工作地点在哪个城市？”将工作时间偏好排在前面；正确工作地点记忆仍在 top-3。首轮 real time **1.25 秒**，observed maximum RSS **881,983,488 bytes**。后两轮主要用于结果重复性，没有记录独立资源指标。本次环境强制 `HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1` 和 `UV_OFFLINE=1`，未下载模型。

这个错误显示当前候选在相近“工作”语境上存在首位混淆。样本仍过小且人工构造，不能据此判断真实多语言召回率、排序质量、实际用户体验或资源目标；Embedding 仍保持产品关闭。下一步需建立经人工标注且不含真实敏感用户数据的中英文候选语料，再对照 FTS/无 Embedding 基线并复核模型许可、migration、重算和删除派生数据。
