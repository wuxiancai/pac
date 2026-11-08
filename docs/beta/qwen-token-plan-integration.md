# 千问 Token Plan 接入备忘

最后核对：2026-11-08（Asia/Shanghai）

本文给后续文本模型和实时语音接入提供协议、地址、Key 和实现状态记录。官方支持/计费能力与本项目是否已实现分开标注。

## 接入结论

- Token Plan 支持 `sk-sp-` 专属 API Key，也支持文本模型和 `qwen-audio-3.0-realtime-plus` 实时语音对话。
- 文本与实时语音走不同协议：文本使用 OpenAI-compatible HTTP Chat Completions；实时语音使用 Realtime WebSocket。文本 adapter 不能直接拿来传音频。
- 实时语音 Token Plan 端点：`wss://token-plan.maas.qianwenaiapi.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus`。
- 官方实时语音示例由 Agent 工具交互式创建/运行客户端；实时 API 的 Token Plan 支持情况已在官方协议矩阵中列明。接入必须由用户主动开始语音会话；不得将 Key 放入常驻后台、批处理或日志。使用范围以当前 Token Plan 个人版条款为准。
- 本项目当前 Beta **尚未接入** Qwen 文本或实时语音。文本 Token Plan 有一次历史真实请求成功，但使用的是旧北京域名；当前文本 adapter 已改为官方品牌域名，新域名尚未重新真实探测。实时语音只有官方协议资料核对，没有本地代码或真实设备验证。

## 固定配置

| 能力 | 模型 | 协议 | 地址 | 状态 |
|---|---|---|---|---|
| 文本对话 | `qwen3.8-flash`（按套餐可用型号） | OpenAI-compatible HTTP | `https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1`；Chat Completions 路径为 `/chat/completions` | CLI adapter 已配置；旧域名有一次真实请求证据，新地址尚未实测；未接入 Beta 对话 UI |
| 实时语音对话 | `qwen-audio-3.0-realtime-plus` | Realtime WebSocket | `wss://token-plan.maas.qianwenaiapi.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus` | 文档核验；尚未实现或实测 |
| 非实时语音识别 | `qwen-audio-3.0-asr-flash` | 独立 DashScope HTTP 接口 | `/api/v1/services/aigc/multimodal-generation/generation` | 尚未实现；不是实时语音会话端点 |
| 语音合成 | `qwen-audio-3.0-tts-plus` | 独立 DashScope HTTP 接口 | `/api/v1/services/audio/tts/SpeechSynthesizer` | 尚未实现；不是实时语音会话端点 |

Token Plan 专属 API Key 存在 macOS login Keychain：service `com.personal-ai-assistant.phase0.provider`、account `qwen`。只在授权请求的内存中读取；不要复制进仓库、聊天、命令行参数、配置文件或日志。前缀不为 `sk-sp-` 时拒绝发送。新建 Key 后，须确认服务区域/套餐匹配；不得静默切换按量计费 Key。

## 实时语音会话流程

未来实现时按下面顺序接线，先做短时交互式 POC，再并入 Beta UI：

1. 用户明确点击“开始云端实时语音”；UI 在采集前显示模型、Token Plan 和音频将发送至千问服务，随后才启动麦克风。
2. 从 Keychain 读取 `qwen` 凭据，仅在内存创建 WebSocket `Authorization: Bearer <key>` 握手。URL 仅包含固定模型 ID；不接受用户输入任意 Host/URL。
3. 配置实时 session：`modalities` 为 audio/text，PCM 输入/输出；官方示例使用单声道 16 kHz、int16 输入和 24 kHz、int16 输出，`server_vad` 端点检测。
4. 麦克风 PCM 分帧后以 `input_audio_buffer.append` 事件和 Base64 发送。原始帧只放有界内存缓冲，不写音频文件、不写日志。
5. 处理输入转写完成、`response.audio.delta`、`response.audio_transcript.delta` / `.done` 与 `error` 事件；音频增量送本机播放队列，文本按事件显示。模型响应音频可能被扬声器重新采集，官方建议使用耳机。
6. 用户停止或遇到错误时，停止采集、关闭 WebSocket、清空输入/播放队列并释放播放器；不自动重连，不回退到云 ASR/TTS 或其他 Provider。实际 Credits 以 Token Plan 控制台为准。

官方示例用 Python `websockets`、`sounddevice` 和 `certifi`，将 Key 从环境变量读取供 Agent 工具运行。本项目应沿用 Keychain 凭据边界，不照搬把密钥放环境变量的方式；Swift 原生 WebSocket 或本机受控会话服务的选型，留在 B2/B4 实际开发时决定。

## 当前进度和后续验收

- 已完成：Token Plan 文本 HTTP 地址更正到品牌域名；套餐专属 Key 前缀检查；真实文本一次成功（历史旧域名）；官方实时 WebSocket Endpoint、模型、事件结构和音频规格记录。
- 未完成：新文本域名逐次确认探测；实时语音 session 的连接、音频收发、partial/final/播放、停止清理和错误分类；UI Consent/麦克风授权；资源/延迟和 Credits 观察。
- 真实请求仍须逐次显示目标、用途、数据级别和发送内容/音频范围并取得用户明确 Consent。任何一次文字授权不覆盖麦克风/音频请求。

## 官方资料

- [Token Plan 接入实时语音对话模型](https://platform.qianwenai.com/docs/token-plan/best-practices/realtime-voice)
- [Token Plan 接入概览与各能力端点](https://platform.qianwenai.com/docs/token-plan/best-practices/integration-overview)
- [Realtime API 协议与模型支持矩阵](https://platform.qianwenai.com/docs/api-reference/realtime-api/overview)
- [Token Plan 概述](https://platform.qianwenai.com/docs/token-plan/overview)
- [OpenAI-compatible 文本客户端配置](https://platform.qianwenai.com/docs/developer-guides/clients-and-developer-tools/chatbox)
