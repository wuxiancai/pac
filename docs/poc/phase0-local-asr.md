# 阶段 0 POC：本地流式 ASR（工作包 0B）

状态：`IN_PROGRESS`。此报告记录一次本机候选实现验证，不代表阶段 0 或 V1 验收通过。

## 范围

- 只在本机运行 sherpa-onnx Streaming ASR，不请求云端服务。
- 验证分帧输入可产生多个可修订的 partial，语句端点产生 final。
- 验证采样率和帧序号不符时明确拒绝，不静默丢帧或切换云端。
- 使用系统本地合成的中文语音生成测试 WAV；没有录制私人麦克风音频。
- 新增明确按回车后才启动的本机默认麦克风 CLI；采集时音频只进入有界内存队列，溢出/输入错误时停止并清缓冲。
- 使用 AVSpeechSynthesizer 本机播放，并验证立即打断控制。
- 本包尚未验证 SwiftUI 音频采集、本机服务认证、AEC、实际麦克风实时识别质量、ASR准确率或目标性能阈值。

## 本机环境

- 设备：Apple M1，统一内存 16 GiB。
- macOS：26.5.1（build 25F80）。
- Xcode：26.6；Swift：6.3.3（arm64）。
- 可用系统卷空间：采集时约 18 GiB。
- Python：POC 使用 uv 管理的 Python 3.12；系统 Python 3.9 不用于项目。
- 音频：系统提供 Tingting 中文合成语音；设备枚举见本机采集记录。
- sherpa-onnx：2.0.1（arm64 CPU wheel）。
- sounddevice：0.5.6（macOS arm64 wheel）；默认输入设备的 16 kHz、单声道、PCM16 配置检查通过，未启动采集流。
- 模型候选：`sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30`，仅存于忽略的 `backend/.poc-data/`。
- 用户实机反馈：当前中文专用模型可以录音并识别中文，无法识别英文是因为选用的模型只覆盖中文；英语覆盖取决于后续多语言模型，不属于当前代码缺陷，也不作为当前阶段的实现阻塞。用户计划后续自行补下载多语言模型。本报告不声称英语识别已验证。

## 结果

- 初始 ASR 事件契约测试：4 项通过（2026-11-07）。
- Python 全量测试：11 项通过；包括麦克风缓冲、PCM 转换、回调 PCM 帧长度、非交互环境拒绝采集和直接脚本入口导入回归。
- Swift TTS 控制器单元测试：3 项通过；Swift 包构建通过。
- AVSpeechSynthesizer 本机播放后按回车中断，返回 `interrupted=true speaking=false`。
- `uv lock --check` 通过；sounddevice 默认输入设备检查支持 16 kHz、单声道、PCM16。
- 本地模型加载：通过。
- 16 kHz、单声道、PCM16 WAV 分为 200 ms 帧输入：通过。
- 本地中文合成音频期间观察到多个增量 partial，序列号持续前进；静音尾段触发 final。
- 测试文本“你好，今天天气很好。我想测试本地实时语音识别。”的最终识别为“你好今天天气很好我想测试本地实时语音识别”。这是单条合成样本观察，不构成准确率结论。
- 原独立 ASR 单样本测量不包含 concurrent LLM；真实麦克风端到端延迟、固定集准确率及重复轮次尚未测。
- 新增固定同步屏障的本机 ASR + Ollama 模型并发观察。对同一 6.94 秒合成 WAV 与 `qwen3.5:0.8b` 一次本机合成请求，在真实重叠期间处理 35 帧，ASR wall 0.785 秒、帧 P50 21.78 ms、P95 52.17 ms、最大 75.45 ms，15 partial / 1 final，ASR worker thread CPU 0.626 秒。本机模型请求 wall 20.326 秒，与 ASR 重叠 0.785 秒。
- 以 1 秒间隔采样 Python ASR 进程和 Ollama serve/runner 进程，本次观察到进程 RSS 合计峰值 702,267,392 bytes、合计 CPU 时间差约 10.95 秒；不是全系统资源统计。GPU 未测。进程采样、单样本、同步请求和调度抖动都会影响观测；P95 抖动高于独立 ASR 的单次观察，不是产品性能验收或稳定分布。
- 并发 probe 不输出 transcript 或模型正文，只输出指标和正文长度；此处是 LLM 生成而非完整 Agent，工具未执行，网络目标固定为本机 loopback。
- 新增可重复的离线资源测量命令 `scripts/measure_local_asr_poc.py`；它只读取用户明确传入的 WAV、只输出统计指标，不输出识别文本或另存音频。
- 对已有本机合成样本单次实测：处理音频 6.94 秒（含 1.6 秒端点静音）、35 帧；ASR 阶段 wall time 0.397 秒、RTF 0.057；模型加载 1.901 秒；进程峰值 RSS 461,209,600 bytes；帧处理延迟 P50 16.34 ms、P95 20.78 ms、最大 25.79 ms；观察到 15 个 partial、1 个 final。以上为单机单样本单次观测，且峰值 RSS 是脚本进程峰值，不是 ASR 子组件增量；不构成麦克风实时链路、稳定性或性能承诺。
- 麦克风 CLI 要求交互式终端，运行后还需用户按回车才会开始最多20秒采集；本次未按下启动键，未录制麦克风音频。

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
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/measure_local_asr_poc.py \
  .poc-data/audio/mandarin-16k.wav \
  .poc-data/models/sherpa-onnx-streaming-zipformer-zh-int8-2025-06-30
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

- 需要由用户明确启动真实麦克风测试，验证 partial/final、VAD、背压、停止和异常后的缓冲清理。
- 用户后续补齐多语言模型后，可按需用中英混合固定样本测识别质量；这不阻塞当前代码开发。真实麦克风端到端重复测量和 P50/P95 阈值仍待产品负责人确认。
- ASR + LLM 并发目前只有一条合成音频/本机模型观察；需要重复轮次、负载时段、GPU 和冷/热启动分开测量，才能评估资源与性能。
- 需要与 FastAPI、SwiftUI 音频采集及独立 TTS 配置集成验证；当前为本机 CLI POC。
- 此模型的许可、分发方式和用户设备内存压力仍需单独记录。
- 静态加密、Keychain、Consent/Policy、云端 ASR、Gateway、记忆和备份 POC 均未开始。

## 基线约束

ASR、TTS、LLM 继续独立配置。此 POC 不实现云端 fallback；本地识别错误向调用方显式失败。ASR partial 只作为临时事件，不写消息或记忆，不触发工具。V1 仍只有一个总助理；无后台任务、外部连接器、外部写操作或任意文件访问。
