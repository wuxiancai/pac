# 千问 API 与 Token Plan 接入说明

最后核对：2026-11-08（Asia/Shanghai）

本文记录千问按量计费 API 与 Token Plan 的协议、地址、Key 和项目实现状态。不同 Key 和计费方式分开记录。

## 接入结论

- Token Plan 支持 `sk-sp-` 专属 API Key，也支持文本模型和 `qwen-audio-3.0-realtime-plus` 实时语音对话。
- 自建应用可使用千问按量计费 API 的 `sk-ws-` Key 和标准 OpenAI 兼容端点。Beta 设置中的“千问（应用 API）”使用该路线，不使用 Token Plan 个人版 Key/额度。
- 文本与实时语音走不同协议：文本使用 OpenAI-compatible HTTP Chat Completions；实时语音使用 Realtime WebSocket。文本 adapter 不能直接拿来传音频。
- 实时语音 Token Plan 端点：`wss://token-plan.maas.qianwenaiapi.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus`。
- 官方实时语音示例可由 Agent 工具的扩展机制交互式调用；Token Plan 支持矩阵也列出 Realtime API。**这表示服务端能力可用，不代表本项目的自建应用可使用个人版 Token Plan Key。**当前官方个人版条款把使用范围限定在编程/智能体工具内交互使用，并明确排除自定义应用后端和非交互批量调用；因此不得把该 Key 接入本项目 SwiftUI/FastAPI 测试版。若要在本应用交付云实时语音，需改用适用于自定义应用的千问 API 计费/凭据，或采用官方允许的 Agent 工具扩展路线。任何获准路线都须由用户主动开始会话；不得将 Key 放入常驻后台、批处理或日志。
- Beta 已添加千问按量计费文本路由：`qwen3.8-flash`、北京区，Keychain account `qwen-app`，端点为普通千问 OpenAI 兼容 API。该应用路由已有 mock/默认拒绝保护，尚未做真实出站。Token Plan 文本另有一次历史真实请求成功（旧北京域名）；当前 Token Plan 域名尚未重新实测，且个人版 Key 不用于自建 Beta。实时语音服务端支持已核验，但 Beta 尚未实现或实测。

## 固定配置

| 能力 | 模型 | 协议 | 地址 | 状态 |
|---|---|---|---|---|
| 文本对话（自建应用） | `qwen3.8-flash` | OpenAI-compatible HTTP，按量计费 | `https://maas.qianwenaiapi.com/compatible-mode/v1/chat/completions` | Beta GUI 有固定路由，Keychain account `qwen-app`，要求独立 `sk-ws-` Key；有 mock/Consent 覆盖，未真实出站 |
| 文本对话（Token Plan POC） | `qwen3.8-flash`（按套餐可用型号） | OpenAI-compatible HTTP，Token Plan | `https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1/chat/completions` | CLI adapter 已配置；旧域名有一次真实请求证据，新地址尚未实测；个人版 Key 不接入本自建 Beta |
| 实时语音对话 | `qwen-audio-3.0-realtime-plus` | Realtime WebSocket | `wss://token-plan.maas.qianwenaiapi.com/api-ws/v1/realtime?model=qwen-audio-3.0-realtime-plus` | 服务端支持已核验；本项目自建测试版不得使用个人版 Token Plan Key；尚未实现或实测 |
| 非实时语音识别 | `qwen-audio-3.0-asr-flash` | 独立 DashScope HTTP 接口 | `/api/v1/services/aigc/multimodal-generation/generation` | 尚未实现；不是实时语音会话端点 |
| 语音合成 | `qwen-audio-3.0-tts-plus` | 独立 DashScope HTTP 接口 | `/api/v1/services/audio/tts/SpeechSynthesizer` | 尚未实现；不是实时语音会话端点 |

Token Plan 专属 API Key 存在 macOS login Keychain：service `com.personal-ai-assistant.phase0.provider`、account `qwen`。只用于官方允许的交互式工具 POC；个人版条款不允许将该 Key 用于本项目自建应用。

Beta 千问按量计费应用 Key 使用同一 Keychain service、account `qwen-app`，要求 `sk-ws-` 前缀；API endpoint 固定为 `maas.qianwenaiapi.com`。请在千问平台新建应用 API Key，绝不复用曾公开贴入聊天的 Key。启用云端模型后，后续聊天内容会直接发送至当前 Provider；应用路由不回退到 Token Plan Key 或其他 Provider。

## 实时语音会话流程

若未来改用适用于自定义应用的凭据，按下面顺序接线，先做短时交互式 POC，再并入 Beta UI。个人版 Token Plan Key 不用于此自建应用流程：

1. 用户明确点击“开始云端实时语音”；UI 在采集前显示模型、Token Plan 和音频将发送至千问服务，随后才启动麦克风。
2. 从 Keychain 读取 `qwen` 凭据，仅在内存创建 WebSocket `Authorization: Bearer <key>` 握手。URL 仅包含固定模型 ID；不接受用户输入任意 Host/URL。
3. 配置实时 session：`modalities` 为 audio/text，PCM 输入/输出；官方示例使用单声道 16 kHz、int16 输入和 24 kHz、int16 输出，`server_vad` 端点检测。
4. 麦克风 PCM 分帧后以 `input_audio_buffer.append` 事件和 Base64 发送。原始帧只放有界内存缓冲，不写音频文件、不写日志。
5. 处理输入转写完成、`response.audio.delta`、`response.audio_transcript.delta` / `.done` 与 `error` 事件；音频增量送本机播放队列，文本按事件显示。模型响应音频可能被扬声器重新采集，官方建议使用耳机。
6. 用户停止或遇到错误时，停止采集、关闭 WebSocket、清空输入/播放队列并释放播放器；不自动重连，不回退到云 ASR/TTS 或其他 Provider。实际 Credits 以 Token Plan 控制台为准。

官方示例用 Python `websockets`、`sounddevice` 和 `certifi`，将 Key 从环境变量读取供 Agent 工具运行。本项目若采用适用于自定义应用的凭据，应沿用 Keychain 凭据边界，不照搬把密钥放环境变量的方式；Swift 原生 WebSocket 或本机受控会话服务的选型，留在对应工作包实际开发时决定。

## 当前进度和后续验收

- 已完成：Beta GUI 可选择千问按量计费应用文本路由；固定 endpoint/model/Keychain account 和 `sk-ws-` 检查；云端 Provider 启用作为持续用户授权，每个后端请求仍受固定目标 Policy、L3 检查和无自动 fallback 约束。仅有 mock/策略验证，没有真实 API 请求。
- Token Plan 未完成：当前官方品牌域名的单次 Consent 真实文本验证；Token Plan 个人版 Key 不能接入自建 Beta。实时语音尚未实现，待采用适用于自定义应用的凭据并按交互音频流程另行开发和验证。
- 千问新应用 Key 的认证和流式响应尚未真实测试；待用户在 GUI Keychain 输入新建的 `sk-ws-` 应用 Key，并逐次确认具体合成测试内容后验证。
- Token Plan 个人版目前明确禁止通过自定义应用后端调用。要在本产品内使用，须千问官方提供允许此类自建应用接入的套餐/许可，或实现通过其明确支持的编程/智能体工具扩展的独立交互集成。任何音频采集仍须由用户显式开始；文字云端授权不自动授权麦克风。

## 官方资料

- [千问 OpenAI 兼容接口](https://platform.qianwenai.com/docs/api-reference/toolkitframework/openai-compatible/overview)
- [获取 API Key（区分 `sk-sp-` 与通用 API Key）](https://platform.qianwenai.com/docs/api-reference/preparation/api-key)
- [Token Plan 个人版使用范围](https://platform.qianwenai.com/docs/token-plan/personal/token-plan-personal-overview)
- [Token Plan 接入实时语音对话模型](https://platform.qianwenai.com/docs/token-plan/best-practices/realtime-voice)
- [Token Plan 接入概览与各能力端点](https://platform.qianwenai.com/docs/token-plan/best-practices/integration-overview)
- [Realtime API 协议与模型支持矩阵](https://platform.qianwenai.com/docs/api-reference/realtime-api/overview)
- [Token Plan 概述](https://platform.qianwenai.com/docs/token-plan/overview)
- [OpenAI-compatible 文本客户端配置](https://platform.qianwenai.com/docs/developer-guides/clients-and-developer-tools/chatbox)
