# 阶段 0 POC：模型许可与分发线索（工作包 0B/0G）

核对日期：2026-11-07。此记录整理公开来源和本机包 metadata，不构成法律意见或产品分发批准。

## Embedding 候选

- 固定权重来自 `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q` revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`。该 revision 的 [Hugging Face 模型页](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/tree/faf4aa4225822f3bc6376869cb1164e8e3feedd0) 标注 `apache-2.0`。
- 对应上游 [Sentence Transformers 模型页](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) 也标注 `apache-2.0`。
- 本机固定安装 FastEmbed `0.9.1` 的 Python package metadata 标注 `Apache-2.0`；通过 `uv run --locked --extra phase0-embedding` 读取。
- 以上建立了模型候选与直接运行库的初步线索。Python 锁定依赖 CycloneDX SBOM 已生成，54/54 个 `uv.lock` 包均纳入，见 [`phase0-python-sbom.md`](phase0-python-sbom.md)。该导出没有内嵌许可证字段，50 个当前安装包可由 distribution metadata 取得许可证线索，另检查 2 个本机 LICENSE 文件；2 个仅在 Windows 安装的锁定包和完整通知义务仍需核查。模型权重/词表和模型随包依赖也不在此 SBOM 内。D-014 仍待产品负责人决定；目前没有把该模型设为默认或纳入产品 schema。
- 2026-11-07 新增三次离线重复：每次 4 个合成 query 均 top-1 命中 4/4；wall 0.81–1.19 秒；`/usr/bin/time -l` observed maximum RSS 883,130,368–883,490,816 bytes。仅为固定小型合成集和本机进程观察，不代表检索质量、产品资源目标或稳定分布。

## 中文 ASR 候选

- 本机权重目录的 README 指向 `yuekai/icefall-asr-multi-zh-hans-zipformer-large`，上游可由 [sherpa-onnx 模型索引](https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/pretrained_models/online-transducer/zipformer-transducer-models.rst) 找到。
- 上游 Hugging Face 仓库当前要求登录并接受访问条件；公开页面没有显示许可正文或具体再分发条款：[上游模型页](https://huggingface.co/yuekai/icefall-asr-multi-zh-hans-zipformer-large)。sherpa-onnx 索引给出模型来源和下载说明，但该页面本身未提供这组权重的明确许可证。
- 因此当前证据不足以确认这组 ASR 权重是否可随产品打包、镜像或再分发。当前本机 POC 已能使用，不代表产品分发许可已核实。关闭该项需从授权页面取得并归档具体条款，确认模型权重与训练数据要求；否则另选许可清晰的候选并重做识别验证。

## 新增 Qwen3-ASR ONNX 候选

- 用户于 2026-11-08 提供 `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25`。目录 README 指向 [ModelScope 转换模型目录](https://modelscope.cn/models/zengshuishui/Qwen3-ASR-onnx/files) 与 [Wasser1462/Qwen3-ASR-onnx 转换项目](https://github.com/Wasser1462/Qwen3-ASR-onnx)；本地权重目录没有 `LICENSE`/`NOTICE` 文件。转换项目页面列出的文件仅有 README、脚本和 WAV 样本，没有展示单独许可证。
- [Qwen 官方 Qwen3-ASR 源项目](https://github.com/QwenLM/Qwen3-ASR) 标注 Apache-2.0；这提供上游项目的许可证线索，但不能单独确认第三方导出/量化 ONNX 权重包、其随附音频与 transcript 的再分发条件。
- 此候选仅保留在本机 `backend/.poc-data/models/` 并被 Git 忽略。阶段 0 的本机推理已完成；产品分发仍需确认 ONNX 转换产物和测试语料各自的许可/来源。
- 推理说明：此包由 sherpa-onnx `OfflineRecognizer.from_qwen3_asr` 执行整段识别。Qwen 官方文档说明 streaming inference 当前仅提供给 vLLM backend；本次没有验证流式运行时。许可证核查不能取代实时语音技术验收。

## 阶段影响

- Embedding 候选：模型卡和直接运行库许可初核完成，Python 锁定依赖清单已生成；许可证闭包、真实标注集、资源阈值和产品模型决定仍开放。
- 原中文 ASR 候选：产品分发条款仍未核实，是 0B 发布/分发证据缺口。新 Qwen3-ASR 候选可做本机离线英语识别，但转换权重/测试音频的分发许可仍待核，且还未通过实时麦克风验收。
- Qwen3-ASR ONNX 候选：上游 Qwen 项目是 Apache-2.0，但第三方转换权重包/随附测试 WAV 的具体许可未确认；只在本地 POC 使用，不纳入产品打包判断。
- 阶段 0 保持未验收；不得将公开页面标签、访问成功或本机推理通过解释为完整许可审批。
