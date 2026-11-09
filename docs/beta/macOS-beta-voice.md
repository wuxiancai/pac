# macOS 测试版：本机语音输入与朗读（B2）

状态：`IN PROGRESS`。原先停止录音后一次性识别已扩展为本机实时流式识别：录音期间显示临时 partial，停止后 final 才写入草稿；生成文字回复期间可点击“打断并语音输入”。用户已确认能在录音时看到实时转写文字；停止后 final、取消和打断生成的完整链路仍待手动复核。

## 实现范围

- 录音只由聊天页的“语音输入”按钮启动。点击后才请求 macOS 麦克风权限；应用启动时不请求、不采集。
- Swift `AVAudioEngine` 在内存中采集并转换为 16 kHz 单声道 PCM16LE。最多缓存 30 秒（960,000 字节）；“取消并丢弃”清空缓冲，应用关闭时停止并丢弃正在录制的缓冲。
- 麦克风回调把转换后的 PCM 按 200 毫秒帧经带随机 Bearer token 的 loopback WebSocket `/voice/stream` 送到同机 FastAPI。协议固定 16 kHz、单声道、PCM16LE，并带单调帧序号；帧串行发送、队列有界、服务端限制单帧与 30 秒总量，同一时刻只允许一个识别会话。识别器使用本机 sherpa-onnx 双语 Streaming Zipformer；音频只在内存和 loopback 传输，不写文件、不出云。
- 录音时 ASR partial 只临时显示在输入区旁，不进入消息或草稿；端点 final 暂存在当前语音会话，用户点“停止并识别”后才合并到草稿。不会自动发送，发送仍由用户单独操作，并遵循当时模型设置的 Provider。识别错误/队列溢出会丢弃未完成转写，不尝试云 ASR。
- 文字模型正在生成时，点“打断并语音输入”先取消当前文字流，再开始本机采集和实时识别。该交互式按键打断不等于全双工声学插话。
- 被打断的 assistant 部分回复保留在界面供查看，但会从下一次模型请求上下文排除，也不能作为“完整回复”启动本机朗读。
- 最新完整 assistant 回复旁提供“本机朗读”和“停止本机朗读”按钮，基于 AVSpeechSynthesizer，需用户手动点播；不会自动播放。
- Beta `.app` Info.plist 已设置 `NSMicrophoneUsageDescription`，说明采集触发方式、30 秒上限、本机处理和不上传边界。

## 当前验证

- 2026-11-09 首次实时语音无响应的根因：Beta 后端仅安装 Uvicorn，没有任何 WebSocket 协议依赖；HTTP 聊天正常，但实时语音握手失败。`backend/pyproject.toml` 与 `uv.lock` 已锁定增加 `websockets==17.4`。本机 Python 3.12 环境检查 `uv run --locked python -c 'from fastapi import FastAPI; from uvicorn.config import Config; config = Config(FastAPI()); config.load(); print(config.ws_protocol_class.__name__)'` 输出 `WebSocketsSansIOProtocol`。已重启 Beta，GUI 确认新实时语音控件显示且本机服务已连接；尚未重试麦克风/语音 WebSocket。
- 用户随后报告再次点击语音输入后，录音时已能在控件右侧看到所说内容的转写。这是用户实机观察；本仓库没有对应捕获/转写数据，停止后的 final 草稿和打断链路仍未验证。
- 新增后端自动回归：认证 WebSocket 握手、协议格式、200 ms PCM 帧序号、partial→final→ended 顺序、坏 token 拒绝、帧序号错误拒绝和连接清理；另覆盖 ASR `finish()` 对 endpoint final 与 endpoint 缺失时的 partial→final 收尾。
- 2026-11-09 继续开发：中断中的 assistant 部分回复仍显示，但不再进入下一次发送上下文，也不允许被当作完整回复朗读。`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；未运行测试。该上下文处理改动在刚构建的二进制中，需重启应用后生效。
- `swift build --package-path poc/macos-audio --product personal-assistant-beta`：实时语音客户端与 Beta target 构建通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc`（工作目录 `backend/`）：通过。
- 实时语音首次实现时没有启动麦克风；后续依赖修复重启应用后，用户手动确认 partial 可见。停止后的 final/草稿、取消丢弃、30 秒上限和文字生成打断仍未验证；本轮未运行测试或再次开启麦克风。
- `swift build --package-path poc/macos-audio --product personal-assistant-beta`：通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc`（工作目录 `backend/`）：通过。
- `poc/macos-audio/scripts/run_beta_app.sh`：构建并启动成功；GUI Accessibility 树显示“语音输入”按钮和提示“点击后才开始麦克风采集；音频最多保留在内存 30 秒”。Info.plist 的 `NSMicrophoneUsageDescription` 已读回确认。
- 本轮没有点击“语音输入”，没有申请权限、打开麦克风或采集音频；没有对录音/ASR endpoint/TTS 播放做运行时验证。没有运行测试。

## 用户手动冒烟步骤

1. 在聊天页点“语音输入”，按系统提示允许麦克风；确认按钮进入录音状态。
2. 说一条不含敏感信息的短句（partial 已由用户确认可见），点“停止并识别”。确认 final 进入输入草稿，不写进聊天历史。
3. 检查目标 Provider 后再决定是否发送。**本轮最后观察到的模型选择是 OpenRouter（Global）**；若希望本地闭环，先在“模型设置”切到本机 Ollama；若要发往千问，选择千问并确认后续聊天持续发送的提示。
4. 收到完整 assistant 回复后点回复旁的扬声器按钮验证本机朗读；需要时点停止按钮。

关闭录音但不识别可点“取消并丢弃”。首次系统权限拒绝后，可在 macOS 系统设置的隐私与安全性/麦克风中为应用开启权限，再重试。

## 未完成项

- 用户实机确认系统权限和录音时 partial 可见；仍需复核 final/草稿、取消/30 秒上限、打断文字生成和 TTS 可听见/可中断。
- 当前实时识别仅覆盖本机 ASR；没有云端 Realtime、自动 VAD/AEC 声学插话、与 TTS 全双工混音或锁屏/休眠行为。上述规格阶段 3 能力和 ADR-021 的完整协议/AEC 决策仍未完成。
- 测试版依赖仓库内 `.poc-data/models/` 的本地模型文件；没有模型时接口返回本机模型不可用，不会回退到云。
- POC 中双语 Streaming Zipformer 的来源/训练数据权利链仍未核清，详见 `../poc/phase0-model-license-review.md`；本工作仅作为单机测试版接入，不能据此宣称正式分发许可已解决。
