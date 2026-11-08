# 阶段 0 POC：本地流式 ASR（工作包 0B）

状态：`IN_PROGRESS`。此报告记录本机候选实现和测量，不代表阶段 0 或 V1 验收通过。

## 范围

- 只在本机运行 sherpa-onnx Streaming ASR，不请求云端服务。
- 验证分帧输入可产生多个可修订的 partial，语句端点产生 final。
- 验证采样率和帧序号不符时明确拒绝，不静默丢帧或切换云端。
- 使用系统本地合成的中文语音生成测试 WAV；没有录制私人麦克风音频。
- 新增明确按回车后才启动的本机默认麦克风 CLI；采集时音频只进入有界内存队列，溢出/输入错误时停止并清缓冲。
- 使用 AVSpeechSynthesizer 本机播放，并验证立即打断控制。
- 本包尚未验证 SwiftUI 音频采集、本机服务认证、AEC、重复实机质量/准确率或目标性能阈值。按规格书 §13，SwiftUI 采集/AEC 属阶段 3，不作为阶段 0 本工作包的关闭条件。用户将当前阶段的真人语音目标限定为功能冒烟，转写质量留待后续模型选择和优化。

## 本机环境

- 设备快照（2026-11-07）：MacBook Air `MacBookAir10,1`、Apple M1（8 核）、统一内存 16 GiB；此快照不单独认定为产品主力设备。
- macOS：26.5.1（build 25F80）。
- Xcode：26.6（build 17F113）；Swift：6.3.3（arm64）。
- 项目 uv Python：3.12.13。
- 可用空间：检查时数据卷剩余约 18 GiB；属于时点数据。
- 音频：系统提供 Tingting 中文合成语音；检查时内建麦克风和内建扬声器均为 48 kHz。外部设备名称未记录。
- sherpa-onnx：2.0.1（arm64 CPU wheel）。
- sounddevice：0.5.6（macOS arm64 wheel）；默认输入设备的 16 kHz、单声道、PCM16 配置检查通过，未启动采集流。
- streaming 模型候选：`sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30`，仅存于忽略的 `backend/.poc-data/`；用户曾实机反馈该中文专用模型可录音识别中文，但不覆盖英文。
- 新增多语言候选：用户提供的 `sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25`，约 972 MB，已移至忽略的 `backend/.poc-data/models/`。目录包含 Qwen3-ASR ONNX decoder/encoder/conv frontend 与 tokenizer。它通过 `OfflineRecognizer.from_qwen3_asr` 做整段离线解码；本次并未验证流式/麦克风接入，也未替换原 streaming 模型。

## 结果

- **2026-11-08 用户主动麦克风功能复测**：运行双语 Streaming Zipformer CLI 30 秒，观察到持续 partial 和一个 final，采集流程完成。用户说明当前阶段只要求链路功能正常；识别文本相对其朗读的参考内容出现明显错词/缩写误识，按用户指示作为后续模型选择/质量优化项，不阻断本轮功能冒烟。该次没有保存音频；未做 CER、延迟或重复性统计。`cd backend` 因终端已在 `backend` 目录而报错，后续脚本仍正常运行。

- 初始 ASR 事件契约测试：4 项通过（2026-11-07）。
- Python 全量测试：11 项通过；包括麦克风缓冲、PCM 转换、回调 PCM 帧长度、非交互环境拒绝采集和直接脚本入口导入回归。
- 2026-11-08 双语 CER 与多 final 聚合修正后，局部评测测试 8 项通过；Python 全量回归 129 项通过（`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security --extra phase0-embedding --group dev pytest -q`），Swift Testing 27 项通过（`swift test`）。
- Swift TTS 控制器单元测试：3 项通过；Swift 包构建通过。
- AVSpeechSynthesizer 本机播放后按回车中断，返回 `interrupted=true speaking=false`。
- `uv lock --check` 通过；sounddevice 默认输入设备检查支持 16 kHz、单声道、PCM16。
- 本地模型加载：通过。
- 16 kHz、单声道、PCM16 WAV 分为 200 ms 帧输入：通过。
- 本地中文合成音频期间观察到多个增量 partial，序列号持续前进；静音尾段触发 final。
- 测试文本“你好，今天天气很好。我想测试本地实时语音识别。”的最终识别为“你好今天天气很好我想测试本地实时语音识别”。这是单条合成样本观察，不构成准确率结论。
- 新增显式 JSON manifest 的本机合成语音评估脚本 `scripts/evaluate_synthetic_asr_poc.py`。它只读取 manifest 明确列出的音频，音频路径限制在 manifest 同目录；只输出字符错误率、事件数等统计，不输出转写正文，也不保存 hypothesis/transcript。
- 固定 Tingting 本机合成 8 条本机合成中文句，逐条新建 Streaming ASR recognizer，每条追加 3,000 ms 静音尾段；8/8 final，59 个 partial，字符级加权 `weighted CER 0.0`（76 个规范化参考字符）。本结果仅表示该 8 条合成中文音频在该本机模型/端点参数下匹配，不是真人麦克风准确率、真实语料泛化或英语测试。该次历史测量之后新增 Qwen3-ASR 离线英语样本评估，见 2026-11-08 记录。
- 本轮重复测量不包含 concurrent LLM；真实麦克风端到端延迟和独立语料的重复统计尚未测。
- 新增固定同步屏障的本机 ASR + Ollama 模型并发观察。对同一 6.94 秒合成 WAV 与 `qwen3.5:0.8b` 一次本机合成请求，在真实重叠期间处理 35 帧，ASR wall 0.785 秒、帧 P50 21.78 ms、P95 52.17 ms、最大 75.45 ms，15 partial / 1 final，ASR worker thread CPU 0.626 秒。本机模型请求 wall 20.326 秒，与 ASR 重叠 0.785 秒。
- 以 1 秒间隔采样 Python ASR 进程和 Ollama serve/runner 进程，本次观察到进程 RSS 合计峰值 702,267,392 bytes、合计 CPU 时间差约 10.95 秒；不是全系统资源统计。GPU 未测。进程采样、单样本、同步请求和调度抖动都会影响观测；P95 抖动高于独立 ASR 的单次观察，不是产品性能验收或稳定分布。
- 并发 probe 不输出 transcript 或模型正文，只输出指标和正文长度；此处是 LLM 生成而非完整 Agent，工具未执行，网络目标固定为本机 loopback。
- 新增可重复的离线资源测量命令 `scripts/measure_local_asr_poc.py`；它只读取用户明确传入的 WAV、只输出统计指标，不输出识别文本或另存音频。
- 对已有本机合成样本单次实测：处理音频 6.94 秒（含 1.6 秒端点静音）、35 帧；ASR 阶段 wall time 0.397 秒、RTF 0.057；模型加载 1.901 秒；进程峰值 RSS 461,209,600 bytes；帧处理延迟 P50 16.34 ms、P95 20.78 ms、最大 25.79 ms；观察到 15 个 partial、1 个 final。以上为单机单样本单次观测，且峰值 RSS 是脚本进程峰值，不是 ASR 子组件增量；不构成麦克风实时链路、稳定性或性能承诺。
- 同一条 6.94 秒合成 WAV 连续运行 3 次离线测量，每次独立加载模型、处理 35 帧，均产生 15 个 partial 和 1 个 final。观察范围：帧 P50 16.01–16.51 ms、帧 P95 17.22–31.78 ms、最大帧耗时 20.31–62.90 ms、RTF 0.0527–0.0665、模型加载 1.57–1.84 秒、脚本进程峰值 RSS 462,159,872–471,318,528 bytes。第 1 次出现较高 P95/max，因此保留范围而不挑选单一值。这是同一合成样本的 3 次观察，不是独立语料样本，不能推断真人语音、麦克风实时性或产品性能验收。
- 麦克风 CLI 要求交互式终端，运行后还需用户按回车才会开始最多20秒采集；本次未按下启动键，未录制麦克风音频。
- 2026-11-08 用户提供 Qwen3-ASR 0.6B INT8 ONNX 候选及随附 WAV/参考文本；模型与样本移入忽略目录，Git 不跟踪它们。用固定版本 sherpa-onnx 2.0.1、CPU、4 threads、auto language、max-total-len 4096、max-new-tokens 1024 做一次本机离线整段评测，入口为 `scripts/evaluate_qwen3_asr_poc.py`。模型加载 2.025 s，进程 observed peak RSS 4,472,487,936 bytes。五个随附测试音频的指标如下（标点/空白规范化后的字符错误率）：

  | 样本 | 语言/内容 | 音频秒数 | 解码秒数 | RTF | CER |
  |---|---|---:|---:|---:|---:|
  | `raokouling.wav` | 中文绕口令 | 20.76 | 6.211 | 0.2992 | 0.0500 |
  | `qiqiu1.wav` | 中文长音频 | 50.96 | 17.210 | 0.3377 | 0.1222 |
  | `f1_noise.wav` | 英语噪声对话 | 19.02 | 3.022 | 0.1589 | 0.0840 |
  | `noise1-en.wav` | 英语长噪声对话 | 88.19 | 71.381 | 0.8094 | 0.1743 |
  | `codeswitch.wav` | 中英法西混说 | 6.23 | 0.997 | 0.1600 | 0.2600 |

  五条的加权 CER 为 0.1564。音频与 reference 来自随包测试目录；它们不是独立留出语料或真人麦克风录音。不同运行的资源峰值/解码延迟受 `max_total_len`、OS 缓存和进程情况影响；这是一轮观察，不代表稳定性能分布。
- 三个模型文件 SHA-256：`conv_frontend.onnx` `d22dc4423e0940e49884e903d2ea2f7e5567c14fc1aed97e4e26d6b8f208ef9e`；`encoder.int8.onnx` `60748d3e6744a57c9c91e1b17424a6c2990567e8adceb0783940c03ed98fa9d9`；`decoder.int8.onnx` `4f6885be5959ae26af3089d38ee7972c5fafbeeb1cf8d5e76eab6d8b61ca5771`。
- 2026-11-08 为验证实时中英路径，另下载 sherpa-onnx 官方发布的 `sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20` 至忽略目录 `backend/.poc-data/models/`。官方模型页将其列为中英双语 Streaming Zipformer，并给出相同发布包下载地址；包内 README 声明 Apache-2.0，来源为 `csukuangfj/k2fsa-zipformer-chinese-english-mixed`。当前模型文件 SHA-256：encoder INT8 `8fa764187a261844f859d7143ebaa563af5d10adfece4c18a8f414c88cba2a9b`；decoder FP32 `2e3b5ec371f8899ee6acd829fd753ba45772df57a91bdf37cde3136354e7db7d`；joiner INT8 `1ed689c5ed19dbaa725d9d191bb4822b5f4855a39e1ffd28cbc1f340d25b2ee0`；tokens `a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3`。模型页面：[sherpa-onnx 双语流式 Zipformer](https://k2-fsa.github.io/sherpa/onnx/pretrained_models/online-transducer/zipformer-transducer-models.html)。
- 该双语 Streaming 模型用现有 200 ms 分帧适配器评测 8 条 Tingting 中文合成句、1 条 Samantha 英语合成句、1 条中英混说合成句；附加 3,000 ms 静音尾段。10/10 产生 final，82 个 partial；大小写/标点/空白归一化后的 weighted CER 为 0.0254（197 个参考字符、5 个字符错误）。8 条中文与混说各自 CER 为 0；英语 CER 为 0.0633。只是小型系统合成音频的流式接口冒烟，不是独立语料、真人口音、麦克风实时或产品准确率验收。
- 本轮修复 `pac_poc/asr_evaluation.py`：CER 预处理现对文本执行 Unicode `casefold()`，避免模型常见的大写英语输出被全部计作替换错误；另确保多段流式 final 会拼接后一起评分。新增回归覆盖大小写不敏感以及跨多个 final 累计。
- 最初以 max-total-len 1024 跑 88 秒 `noise1-en.wav` 时，运行时明确警告输入上下文被截断，该结果已排除；将上下文提高到 4096 后重测。默认脚本使用 4096/1024 以覆盖随包长音频。

## 复现

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv sync --locked
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q
mkdir -p .poc-data/audio
say -v Tingting -o .poc-data/audio/mandarin.aiff '你好，今天天气很好。我想测试本地实时语音识别。'
afconvert -f WAVE -d LEI16@16000 -c 1 .poc-data/audio/mandarin.aiff .poc-data/audio/mandarin-16k.wav
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/run_local_asr_poc.py \
  .poc-data/audio/mandarin-16k.wav \
  .poc-data/models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/evaluate_synthetic_asr_poc.py \
  .poc-data/audio/asr-synthetic-a3ecd94d/manifest.json \
  .poc-data/models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/evaluate_synthetic_asr_poc.py \
  .poc-data/audio/bilingual-manifest.json \
  .poc-data/models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/measure_local_asr_poc.py \
  .poc-data/audio/mandarin-16k.wav \
  .poc-data/models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --extra phase0-security python scripts/evaluate_qwen3_asr_poc.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/measure_concurrent_asr_llm_poc.py \
  .poc-data/audio/mandarin-16k.wav \
  .poc-data/models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/run_live_microphone_poc.py \
  .poc-data/models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30 --seconds 20
cd ../poc/macos-audio
swift test
swift run tts-interrupt-poc
```

麦克风脚本必须在本机交互式终端运行；显示本地隐私提示后按回车才开始采集。按 Ctrl-C 可停止。它不保存音频文件或文本。

首次运行前，按 sherpa-onnx 官方模型说明下载 `sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30.tar.bz2` 到 `backend/.poc-data/models/` 并解压。模型权重与测试音频不提交 Git。

## 尚未解决

- 2026-11-08 实机停止冒烟：用户启动双语 Streaming Zipformer 麦克风 CLI 后，观察到“正在本机识别”；停止前没有 partial/final 输出，按 Ctrl-C 后 CLI 打印“用户停止了本机采集；未补造 final。”并正常回到 shell。用户随后澄清当时麦克风未打开；该次只作为静音期间手动停止路径证据，不计为语音识别通过。
- 自动回归现以模拟 `sounddevice` callback 和故意失败/中断的 decoder 验证：普通异常向上传递，KeyboardInterrupt 显示用户停止提示；两种情况下输入流上下文均关闭且有界缓冲清空。该结果不覆盖真实设备驱动故障或 Ctrl-C 的硬件行为；已有一次真实设备 Ctrl-C 停止证据；真实设备驱动异常仍待测。
- 2026-11-08 首次实机运行的历史观察：产生多个增量 partial 和两个 final；混合中英内容有错词。用户后来将当前真人语音标准限定为功能冒烟、把模型识别质量留待后续，因此此观察不计 CER，也不作为本轮功能验证的阻断项。开麦后的后续实机复测也已观察到中英 partial/final；当前补证项为真实设备驱动异常和重复功能稳定性；SwiftUI 集成按规格书属于阶段 3。
- 双语 streaming 候选已产生中英及混说的文件分帧 partial/final；用户已补三次 CLI 实机功能冒烟，并指定识别质量留待后续模型选择。真实麦克风 Ctrl-C 停止已有一次证据；之后开麦实测又观察到中文和英文 partial/final。识别词句存在偏差，按用户决定留待后续模型优化；驱动异常和额外重复功能稳定性仍未覆盖；SwiftUI 链路按规格书属于阶段 3。合成语音分数不能替代真实麦克风功能冒烟。
- Qwen3-ASR 候选已在五条随包音频上完成离线中/英/混说检查；尚无独立留出中英语料。其 ONNX 离线整段路径不能证明实时流式延迟、partial/final、打断、SwiftUI 麦克风处理或长时运行能力。Qwen 官方当前说明流式推理需 vLLM backend；本机现有 sherpa-onnx API 测试使用 `OfflineRecognizer`，因此不能把 RTF<1 写成实时流式验收。
- sherpa-onnx 官方 Python API 样例将此类模型通过 `OfflineRecognizer.from_qwen3_asr` 整段解码；参见 [官方 Qwen3-ASR 文件解码样例](https://github.com/k2-fsa/sherpa-onnx/blob/master/python-api-examples/offline-qwen3-asr-decode-files.py)。Qwen 官方说明 Qwen3-ASR 的 streaming inference 当前只在 vLLM backend 提供，详见 [Qwen3-ASR 官方文档](https://github.com/QwenLM/Qwen3-ASR#streaming-inference)。
- 当前 8 条合成中文集只有一轮，CER 不能代表真人麦克风或真实用户话语分布；需要更广语料与多轮实机验证，阈值待产品负责人确认。
- ASR + LLM 并发目前只有一条合成音频/本机模型观察；需要重复轮次、负载时段、GPU 和冷/热启动分开测量，才能评估资源与性能。
- 当前为本机 CLI POC；规格书将 SwiftUI 采集/播放与 WebSocket 闭环列入阶段 3。阶段 0 仍需将 ASR/TTS 稳定链路证据及现有资源测量归档。
- 新 Qwen3-ASR ONNX 候选的模型来源为 ModelScope 第三方转换包，模型目录没有 LICENSE 文件；Qwen 官方项目标注 Apache-2.0，但转换包及随附测试音频的分发许可/来源仍需单独核实。设备内存观察峰值约 4.47 GB；需要更多样本和并发负载后评估资源预算。
- 本中文 ASR 权重的公开上游仓库要求接受访问条件，公开页面未展示许可条款；具体证据与待核验范围见 [`phase0-model-license-review.md`](phase0-model-license-review.md)。
- 其他阶段 0 工作包状态见 [`phase0-traceability.md`](phase0-traceability.md)。

## 基线约束

ASR、TTS、LLM 继续独立配置。此 POC 不实现云端 fallback；本地识别错误向调用方显式失败。ASR partial 只作为临时事件，不写消息或记忆，不触发工具。V1 仍只有一个总助理；无后台任务、外部连接器、外部写操作或任意文件访问。
