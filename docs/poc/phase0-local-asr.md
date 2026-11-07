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
- 未采集 P50/P95、内存/CPU、端到端麦克风延迟；不据此作性能承诺。
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
- 需要中英混合固定样本集与多轮重复，测识别质量及 P50/P95；阈值由产品负责人确认。
- 需要与 FastAPI、SwiftUI 音频采集及独立 TTS 配置集成验证；当前为本机 CLI POC。
- 此模型的许可、分发方式和用户设备内存压力仍需单独记录。
- 静态加密、Keychain、Consent/Policy、云端 ASR、Gateway、记忆和备份 POC 均未开始。

## 基线约束

ASR、TTS、LLM 继续独立配置。此 POC 不实现云端 fallback；本地识别错误向调用方显式失败。ASR partial 只作为临时事件，不写消息或记忆，不触发工具。V1 仍只有一个总助理；无后台任务、外部连接器、外部写操作或任意文件访问。
