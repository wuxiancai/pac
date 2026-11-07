# 阶段 0 POC：模型许可与分发线索（工作包 0B/0G）

核对日期：2026-11-07。此记录整理公开来源和本机包 metadata，不构成法律意见或产品分发批准。

## Embedding 候选

- 固定权重来自 `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q` revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`。该 revision 的 [Hugging Face 模型页](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/tree/faf4aa4225822f3bc6376869cb1164e8e3feedd0) 标注 `apache-2.0`。
- 对应上游 [Sentence Transformers 模型页](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) 也标注 `apache-2.0`。
- 本机固定安装 FastEmbed `0.9.1` 的 Python package metadata 标注 `Apache-2.0`；通过 `uv run --locked --extra phase0-embedding` 读取。
- 以上建立了模型候选与直接运行库的初步线索；仍需生成完整依赖 SBOM、核对所有随包依赖和通知义务，并由产品负责人确定是否采用（D-014）。目前没有把该模型设为默认或纳入产品 schema。
- 2026-11-07 新增三次离线重复：每次 4 个合成 query 均 top-1 命中 4/4；wall 0.81–1.19 秒；`/usr/bin/time -l` observed maximum RSS 883,130,368–883,490,816 bytes。仅为固定小型合成集和本机进程观察，不代表检索质量、产品资源目标或稳定分布。

## 中文 ASR 候选

- 本机权重目录的 README 指向 `yuekai/icefall-asr-multi-zh-hans-zipformer-large`，上游可由 [sherpa-onnx 模型索引](https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/pretrained_models/online-transducer/zipformer-transducer-models.rst) 找到。
- 上游 Hugging Face 仓库当前要求登录并接受访问条件；公开页面没有显示许可正文或具体再分发条款：[上游模型页](https://huggingface.co/yuekai/icefall-asr-multi-zh-hans-zipformer-large)。sherpa-onnx 索引给出模型来源和下载说明，但该页面本身未提供这组权重的明确许可证。
- 因此当前证据不足以确认这组 ASR 权重是否可随产品打包、镜像或再分发。当前本机 POC 已能使用，不代表产品分发许可已核实。关闭该项需从授权页面取得并归档具体条款，确认模型权重与训练数据要求；否则另选许可清晰的候选并重做识别验证。

## 阶段影响

- Embedding 候选：许可初核完成，真实标注集、完整依赖清单、资源阈值和产品模型决定仍开放。
- 中文 ASR 候选：产品分发条款仍未核实，是 0B 发布/分发证据缺口；英语多语言模型仍按用户决定留待后续，不是当前代码 bug。
- 阶段 0 保持未验收；不得将公开页面标签、访问成功或本机推理通过解释为完整许可审批。
