# macOS 测试版：本机语音输入与朗读（B2）

状态：`IN PROGRESS`。原先停止录音后一次性识别已扩展为本机实时流式识别：录音期间显示临时 partial，停止后 final 才写入草稿；生成文字回复期间可点击“打断并语音输入”。用户已实机确认 partial、停止后 final 入草稿、取消清空 partial、打断生成并开始采集，以及录音中 Cmd-Q 后 app/backend 退出且重启无残留。

## 实现范围

- 录音只由聊天页的“语音输入”按钮启动。点击后才请求 macOS 麦克风权限；应用启动时不请求、不采集。
- Swift `AVAudioEngine` 在内存中采集并转换为 16 kHz 单声道 PCM16LE。最多缓存 30 秒（960,000 字节）；“取消并丢弃”清空缓冲，应用关闭时停止并丢弃正在录制的缓冲。
- 麦克风回调把转换后的 PCM 按 200 毫秒帧经带随机 Bearer token 的 loopback WebSocket `/voice/stream` 送到同机 FastAPI。一次性 `/voice/transcribe` 兼容入口也按请求流逐块累计，超过配置 PCM 上限即拒绝，不依赖 Content-Length 才能限长。协议固定 16 kHz、单声道、PCM16LE，并带单调帧序号；帧串行发送、队列有界、服务端限制单帧与 30 秒总量，同一时刻只允许一个识别会话；WebSocket 断连/取消若发生在阻塞式 ASR 调用期间，会等待该线程调用结束后再执行 abort 和释放会话锁，避免并行清理或新会话与旧识别器竞争。识别器使用本机 sherpa-onnx 双语 Streaming Zipformer；音频只在内存和 loopback 传输，不写文件、不出云。
- 录音时 ASR partial 只临时显示在输入区旁，不进入消息或草稿；端点 final 暂存在当前语音会话，用户点“停止并识别”后才合并到草稿。不会自动发送，发送仍由用户单独操作，并遵循当时模型设置的 Provider。识别错误/队列溢出会丢弃未完成转写，不尝试云 ASR。
- 文字模型正在生成时，点“打断并语音输入”先取消当前文字流，再开始本机采集和实时识别。该交互式按键打断不等于全双工声学插话。
- 被打断的 assistant 部分回复保留在界面供查看，但会从下一次模型请求上下文排除，也不能作为“完整回复”启动本机朗读。
- 最新完整 assistant 回复旁提供“本机朗读”和“停止本机朗读”按钮，基于 AVSpeechSynthesizer，需用户手动点播；不会自动播放。
- Beta `.app` Info.plist 已设置 `NSMicrophoneUsageDescription`，说明采集触发方式、30 秒上限、本机处理和不上传边界。

## 当前验证

- **2026-11-09 一次性语音请求限长与取消清理**：`/voice/transcribe` 现通过 ASGI 请求流分块读取，测试无 Content-Length 的 chunked 请求在超过 30 秒字节上限时返回 413，且不调用识别器；批量同步 ASR 同样经取消安全 worker 执行，取消期间会持有单会话锁直至识别线程结束。后端全量 251 项通过，1 条既有 Starlette/httpx 弃用警告。

- **2026-11-09 取消期间 ASR 线程清理**：请求协程被取消时，`asyncio.to_thread` 内的同步 ASR 调用不能被强制中止；现在先等待该调用结束，再执行 abort 与锁释放。新增线程阻塞期间取消的回归，验证清理不会越过仍在运行的 worker。后端全量 250 项通过，1 条既有 Starlette/httpx 弃用警告；此自动化测试不替代真实麦克风驱动故障注入。

- **2026-11-09 快速重连根因及修复**：用户 GUI 报第一次停止后 socket 断开，第二次服务端 busy（partial n=2、停止→final n=0）。在真实 Uvicorn WebSocket + 项目本机 ASR 模型上复现停止路径 `AttributeError: LocalStreamingASR has no attribute reset`：`LocalVoiceTranscriber.end_stream()` 和 `abort_stream()` 都错误地调用包装器上不存在的 `reset()`，且 WebSocket `finally` 在 abort 抛错时跳过锁释放，造成该会话永久占锁。现改为调用底层 recognizer 的 `reset()` 并保证清除 stream 引用；服务端 finally 无论清理是否异常都释放 asyncio 锁。修复后同一真实 Uvicorn + 本机 ASR 模型、真实音频文件 PCM 分帧、连续 3 轮均收到 partial/final/ended。Apple `URLSessionWebSocketTask` + 真实 Uvicorn + 项目 sherpa-onnx ASR + 仓库 PCM WAV 整链连续 3 轮通过（partial/final/ended 均收到）；用户随后确认 GUI 实时语音故障已修复；尚未收到可复核的 D-013 P95 面板数值。
- D-013 本机测量诊断已加入可选模式：从仓库根目录运行 `PAC_BETA_PERF_DIAGNOSTICS=1 poc/macos-audio/scripts/run_beta_app.sh`，聊天窗口底部会显示三项数值。诊断仅在当前进程内保存时间样本，不保存音频或转写：Beta App 初始化至本机服务就绪；PCM 帧组装就绪至对应 partial 更新 SwiftUI 状态；点击“停止并识别”至 final 草稿更新。partial 指标不含 200 ms 帧组装之前的采集时间，也不测屏幕实际绘制完成；须保留定义，不把它直接外推成完整用户感知延迟。诊断关闭时不显示或累计这些分布。
- **2026-11-09 用户提供的 D-013 GUI 样本**：启动值共 20 个。此前 17 个范围 500–700 ms；用户补充的三张启动面板截图读数为 678.5、618.4、651.1 ms。20 次启动的 nearest-rank P95=700 ms，低于 5 秒门槛，既定启动样本数已完成。根因已查明：启动耗时以秒存储，面板遗漏乘以 1,000，却标注为毫秒；已修正显示换算。较早两张截图的 0.7 为第 17 个样本，同一运行另有 partial n=7、P95=32.5 ms 和停止→final n=1、92.0 ms。partial 共 22 组窗口摘要（1 组 n=9、20 组 n=10、1 组 n=7），合计 216 次更新；各组 P95 32.2–41.5 ms。面板使用 nearest-rank `ceil(n×0.95)`，每组样本数均小于 20，因此组内 P95 为该组最大值，所有已采样 partial 更新均不超过 41.5 ms，低于 500 ms 门槛。停止→final 共 21 个单样本；按同一 nearest-rank 算法合并后 P95=97.9 ms，最大 99.9 ms，低于 2 秒门槛。诊断样本仅统计时长，不保存音频或转写。
- 较早一轮“0.9s-0.11s”报告存在端点/小数歧义，不用于精确分布；之后提供了 20 个诊断面板启动值的有效记录并关闭启动采样缺口。
- 复核发现后端在 WebSocket `/voice/stream` 发送 `ended` 后才释放单例 ASR 锁，存在客户端收到完成事件后立即重连撞上旧锁的竞态。现已改为先结束/清理 ASR 流、释放锁，再发送 `ended`；新增同一客户端会话结束后立即再次连接的回归。后端 15 项窄回归及 Python 全量 176 项通过；GUI 上仍需用户用新构建复测快速再次录音。

- 2026-11-09 首次实时语音无响应的根因：Beta 后端仅安装 Uvicorn，没有任何 WebSocket 协议依赖；HTTP 聊天正常，但实时语音握手失败。`backend/pyproject.toml` 与 `uv.lock` 已锁定增加 `websockets==17.4`。本机 Python 3.12 环境检查 `uv run --locked python -c 'from fastapi import FastAPI; from uvicorn.config import Config; config = Config(FastAPI()); config.load(); print(config.ws_protocol_class.__name__)'` 输出 `WebSocketsSansIOProtocol`。已重启 Beta，GUI 确认新实时语音控件显示且本机服务已连接；尚未重试麦克风/语音 WebSocket。
- 用户随后报告再次点击语音输入后，录音时已能在控件右侧看到所说内容的转写。这是用户实机观察；本仓库没有对应捕获/转写数据，停止后的 final 草稿和打断链路仍未验证。
- 新增后端自动回归：认证 WebSocket 握手、协议格式、200 ms PCM 帧序号、partial→final→ended 顺序、坏 token 拒绝、帧序号错误拒绝和连接清理；另覆盖 ASR `finish()` 对 endpoint final 与 endpoint 缺失时的 partial→final 收尾。
- 2026-11-09 用户确认 D-004：音频最多保留 30 秒（960,000 字节），取消、异常、断连和退出都立即清空未完成音频。新增自动回归确认服务端接受前 30 秒并拒绝超限帧、WebSocket 断连调用 ASR abort 清理；SwiftUI GUI 的取消/退出路径仍待实机复核。
- 2026-11-09 继续开发：中断中的 assistant 部分回复仍显示，但不再进入下一次发送上下文，也不允许被当作完整回复朗读。`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；未运行测试。该上下文处理改动在刚构建的二进制中，需重启应用后生效。
- `swift build --package-path poc/macos-audio --product personal-assistant-beta`：实时语音客户端与 Beta target 构建通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc`（工作目录 `backend/`）：通过。
- 实时语音首次实现时没有启动麦克风；后续依赖修复重启应用后，用户手动确认 partial 可见。停止后的 final/草稿、取消丢弃、30 秒上限和文字生成打断仍未验证；本轮未运行测试或再次开启麦克风。
- `swift build --package-path poc/macos-audio --product personal-assistant-beta`：通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc`（工作目录 `backend/`）：通过。
- `poc/macos-audio/scripts/run_beta_app.sh`：构建并启动成功；GUI Accessibility 树显示“语音输入”按钮和提示“点击后才开始麦克风采集；音频最多保留在内存 30 秒”。Info.plist 的 `NSMicrophoneUsageDescription` 已读回确认。
- 2026-11-09 用户确认 ADR-021 的 V1 边界：本机点击触发实时 ASR，语音按钮可打断文字生成，final 放入草稿；不做 AEC、自动声学插话或云 Realtime。之后用户实机确认停止后 final 入草稿、取消丢弃 partial、语音打断生成并开始采集、录音中 Cmd-Q 退出清理四项均成功。D-013 Beta GUI 样本已低于性能门槛；真实驱动异常仍未验证。
- 本轮没有点击“语音输入”，没有申请权限、打开麦克风或采集音频；没有对录音/ASR endpoint/TTS 播放做运行时验证。没有运行测试。

## 用户手动冒烟步骤

**当前首要复测**：先按 Cmd-Q 退出旧 App，再从仓库根目录运行 `PAC_BETA_PERF_DIAGNOSTICS=1 ./poc/macos-audio/scripts/run_beta_app.sh`。确认新窗口显示“本机服务已连接”；做两轮“语音输入→说短句→停止并识别”，每轮确认 final 进入草稿且第二轮能开始。完成前先不要采集 20 次性能样本。若仍失败，记录状态栏完整错误文本和诊断面板数值，不发送任何转写。

1. 在聊天页点“语音输入”，按系统提示允许麦克风；确认按钮进入录音状态。
2. 说一条不含敏感信息的短句（partial 已由用户确认可见），点“停止并识别”。确认 final 进入输入草稿，不写进聊天历史。
3. 检查目标 Provider 后再决定是否发送。**本轮最后观察到的模型选择是 OpenRouter（Global）**；若希望本地闭环，先在“模型设置”切到本机 Ollama；若要发往千问，选择千问并确认后续聊天持续发送的提示。
4. 收到完整 assistant 回复后点回复旁的扬声器按钮验证本机朗读；需要时点停止按钮。

关闭录音但不识别可点“取消并丢弃”。首次系统权限拒绝后，可在 macOS 系统设置的隐私与安全性/麦克风中为应用开启权限，再重试。

## 未完成项

- 用户实机确认系统权限和录音时 partial 可见，并验证 final/草稿、取消清空 partial、语音打断文字生成；录音中 Cmd-Q 后应用和后端退出、重启无残留转写或录音。最新快速二次语音仍失败，有限重试已构建但待 GUI 复测；30 秒上限已有后端自动回归。真实设备驱动异常、TTS 可听见/可中断仍需实机复核。
- 当前实时识别仅覆盖本机 ASR；没有云端 Realtime、自动 VAD/AEC 声学插话、与 TTS 全双工混音或锁屏/休眠行为。这些不属于用户确认的 V1 ADR-021 边界；D-013 当前 Beta 路径性能样本已低于目标；真实音频驱动异常注入、其他设备/系统验证仍未覆盖。
- 测试版依赖仓库内 `.poc-data/models/` 的本地模型文件；没有模型时接口返回本机模型不可用，不会回退到云。
- POC 中双语 Streaming Zipformer 的来源/训练数据权利链仍未核清，详见 `../poc/phase0-model-license-review.md`；本工作仅作为单机测试版接入，不能据此宣称正式分发许可已解决。
- D-013 GUI 延迟样本均低于门槛。启动计时单位显示错误已修复：秒值现在乘以 1,000 后标为毫秒；20 个启动值范围 500–700 ms，nearest-rank P95=700 ms。partial 共 216 个更新、22 个窗口摘要的 P95 为 32.2–41.5 ms；停止→final 共 21 个样本，pooled P95=97.9 ms、最大 99.9 ms。诊断仅保留进程内时长样本，退出即清空。
