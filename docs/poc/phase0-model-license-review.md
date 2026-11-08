# 阶段 0 POC：模型许可与分发线索（工作包 0B/0G）

核对日期：2026-11-07。此记录整理公开来源和本机包 metadata，不构成法律意见或产品分发批准。

## Embedding 候选

- 固定权重来自 `Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q` revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`。该 revision 的 [Hugging Face 模型页](https://huggingface.co/Qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q/tree/faf4aa4225822f3bc6376869cb1164e8e3feedd0) 标注 `apache-2.0`。
- 对应上游 [Sentence Transformers 模型页](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) 也标注 `apache-2.0`。
- 本机固定安装 FastEmbed `0.9.1` 的 Python package metadata 标注 `Apache-2.0`；通过 `uv run --locked --extra phase0-embedding` 读取。
- 以上建立了模型候选与直接运行库的初步线索。Python 锁定依赖 CycloneDX SBOM 已生成，54/54 个 `uv.lock` 包均纳入，见 [`phase0-python-sbom.md`](phase0-python-sbom.md)。该导出没有内嵌许可证字段；50 个当前安装包可由 distribution metadata（包括 Trove license classifiers）取得许可证线索，另检查 2 个本机 LICENSE 文件，剩余 2 个 Windows-only 包已由其精确版本 PyPI 页面取得许可证标识。54 个依赖现均有初步许可证来源线索，但许可证适用范围、通知义务、原生依赖和随包内容仍需审查。模型权重/词表和模型随包依赖也不在此 SBOM 内。D-014 仍待产品负责人决定；目前没有把该模型设为默认或纳入产品 schema。
- 2026-11-07 新增三次离线重复：每次 4 个合成 query 均 top-1 命中 4/4；wall 0.81–1.19 秒；`/usr/bin/time -l` observed maximum RSS 883,130,368–883,490,816 bytes。仅为固定小型合成集和本机进程观察，不代表检索质量、产品资源目标或稳定分布。

## 中文 ASR 候选

- 本机权重目录的 README 指向 `yuekai/icefall-asr-multi-zh-hans-zipformer-large`，上游可由 [sherpa-onnx 模型索引](https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/pretrained_models/online-transducer/zipformer-transducer-models.rst) 找到。
- 上游 Hugging Face 仓库当前要求登录并接受访问条件；公开页面没有显示许可正文或具体再分发条款：[上游模型页](https://huggingface.co/yuekai/icefall-asr-multi-zh-hans-zipformer-large)。sherpa-onnx 索引给出模型来源和下载说明，但该页面本身未提供这组权重的明确许可证。
- 因此当前证据不足以确认这组 ASR 权重是否可随产品打包、镜像或再分发。当前本机 POC 已能使用，不代表产品分发许可已核实。关闭该项需从授权页面取得并归档具体条款，确认模型权重与训练数据要求；否则另选许可清晰的候选并重做识别验证。

## 实际使用的中英 Streaming Zipformer 候选

- 本机归档包 `sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/README.md` 的 front matter 声明 `apache-2.0`，正文指向 `pfluo/k2fsa-zipformer-chinese-english-mixed`。sherpa-onnx 官方模型索引将发布包列为社区贡献模型，但其转换来源列为 `csukuangfj/k2fsa-zipformer-chinese-english-mixed`，并称其使用“some internal dataset”。两个上游标识不一致；本机包 README 与官方索引均保留在项目的审计记录中。
- `pfluo/k2fsa-zipformer-chinese-english-mixed` 与 `csukuangfj/k2fsa-zipformer-bilingual-zh-en-t` 的 Hugging Face 页面均声明 `apache-2.0`；后者说明它 fork 自前者。上述是上游仓库元数据/模型卡的许可声明，不是独立权属审计，也没有提供内部训练数据的可核验来源或授权明细。因此记录为“模型仓库声明 Apache-2.0；训练数据权利链未独立核验”，不推断为已完成法律许可审批。
- 使用的 sherpa-onnx runtime 与模型权重是不同许可对象。本机锁定 `sherpa-onnx==2.0.1` wheel 含 `sherpa-onnx-2.0.1.dist-info/licenses/LICENSE`，其项目许可证为 Apache-2.0；runtime 许可证不自动覆盖独立预训练权重。
- 采音 Python 包 `sounddevice==0.5.6` 的 PyPI 发布信息声明 MIT；它是 PortAudio bindings。PortAudio 官方 V19 许可同样是 MIT 风格并要求保留版权与许可通知。最终发行审查仍应核对实际链接/随包的 PortAudio 二进制版本及其通知。
- 第一方来源： [sherpa-onnx 官方模型索引](https://github.com/k2-fsa/sherpa/blob/master/docs/source/onnx/pretrained_models/online-transducer/zipformer-transducer-models.rst)、[pfluo 模型页](https://huggingface.co/pfluo/k2fsa-zipformer-chinese-english-mixed/tree/main)、[csukuangfj 转换模型页](https://huggingface.co/csukuangfj/k2fsa-zipformer-bilingual-zh-en-t)、[sherpa-onnx runtime LICENSE](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE)、[sherpa-onnx 2.0.1 PyPI](https://pypi.org/project/sherpa-onnx/2.0.1/)、[sounddevice 0.5.6 PyPI](https://pypi.org/project/sounddevice/0.5.6/)、[PortAudio V19 license](https://portaudio.com/license.html)。

## 新增 Qwen3-ASR ONNX 候选

- 用户于 2026-11-08 提供 `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25`。目录 README 指向 [ModelScope 转换模型目录](https://modelscope.cn/models/zengshuishui/Qwen3-ASR-onnx/files) 与 [Wasser1462/Qwen3-ASR-onnx 转换项目](https://github.com/Wasser1462/Qwen3-ASR-onnx)；本地权重目录没有 `LICENSE`/`NOTICE` 文件。转换项目页面列出的文件仅有 README、脚本和 WAV 样本，没有展示单独许可证。
- [Qwen 官方 Qwen3-ASR 源项目](https://github.com/QwenLM/Qwen3-ASR) 标注 Apache-2.0；这提供上游项目的许可证线索，但不能单独确认第三方导出/量化 ONNX 权重包、其随附音频与 transcript 的再分发条件。
- 此候选仅保留在本机 `backend/.poc-data/models/` 并被 Git 忽略。阶段 0 的本机推理已完成；产品分发仍需确认 ONNX 转换产物和测试语料各自的许可/来源。
- 推理说明：此包由 sherpa-onnx `OfflineRecognizer.from_qwen3_asr` 执行整段识别。Qwen 官方文档说明 streaming inference 当前仅提供给 vLLM backend；本次没有验证流式运行时。许可证核查不能取代实时语音技术验收。

### 2026-11-08 补充：公开许可来源交叉核对

- 官方 Hugging Face `Qwen/Qwen3-ASR-0.6B-hf` 模型页标注 `apache-2.0`；官方 `QwenLM/Qwen3-ASR` 仓库包含 Apache License 2.0 文本。该证据覆盖官方源模型/官方仓库各自的许可声明，不自动覆盖第三方转换代码、导出工件或测试音频。
- 对照 `Wasser1462/Qwen3-ASR-onnx` 当前公开仓库目录，列出的文件中没有 `LICENSE`；README 介绍其 ONNX 导出流程并致谢 Qwen，但没有单独说明该导出仓库或产物的许可证。用户本机包 README 指向的 ModelScope `zengshuishui/Qwen3-ASR-onnx` 文件页本轮无法通过公开网页读取，故不能据此核实下载文件对应 revision、量化/转换信息或权重适用许可。当前仍只能把该转换包作为本机 POC 资产。
- 随包 `test_wavs/README.md` 将音频来源指向 Qwen 官方博客；博客展示样例不等于授予音频复制、再分发或打包许可。本轮未找到该样例音频的独立许可声明，也未逐文件核验本地音频与公开样例的对应关系。
- 依据：[官方 Qwen3-ASR 0.6B 模型页](https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf)、[官方 Qwen3-ASR LICENSE](https://github.com/QwenLM/Qwen3-ASR/blob/main/LICENSE)、[Wasser1462 转换仓库文件列表与 README](https://github.com/Wasser1462/Qwen3-ASR-onnx)、[ModelScope 转换包文件页](https://modelscope.cn/models/zengshuishui/Qwen3-ASR-onnx/files)、[Qwen 官方 ASR 样例页](https://qwen.ai/blog?id=qwen3asr)。本次核查是公开资料记录，不是法律意见。
- 结论状态：官方源模型许可线索已确认；第三方 ONNX 转换代码/工件与样例音频分发许可仍未闭环。阶段 0 POC 使用不代表产品打包或分发获准。

## 阶段影响

- Embedding 候选：模型卡和直接运行库许可初核完成，Python 锁定依赖清单已生成；许可证闭包、真实标注集、资源阈值和产品模型决定仍开放。
- 原中文 ASR 候选：产品分发条款仍未核实，是 0B 发布/分发证据缺口。实际使用的中英 Streaming Zipformer 模型仓库声明 Apache-2.0，但来源标识不一致且内部训练数据权利链未核验。新 Qwen3-ASR 候选可做本机离线英语识别，但转换权重/测试音频的分发许可仍待核，且还未通过实时麦克风验收。
- Qwen3-ASR ONNX 候选：上游 Qwen 项目是 Apache-2.0，但第三方转换权重包/随附测试 WAV 的具体许可未确认；只在本地 POC 使用，不纳入产品打包判断。
- 阶段 0 保持未验收；不得将公开页面标签、访问成功或本机推理通过解释为完整许可审批。
