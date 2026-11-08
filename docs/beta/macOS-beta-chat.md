# macOS 测试版：本机文字对话（B0/B1）

状态：`IN PROGRESS`。首个可运行 macOS SwiftUI 测试版已接入当前受认证 Loopback 服务，并通过本机 Ollama 流式文本 API。

## 当前范围

- SwiftUI 应用由 `poc/macos-audio/scripts/run_beta_app.sh` 构建并启动；后端继续由固定 supervisor 进程管理，退出时经私有管道停止。
- 本机服务只绑定 `127.0.0.1`，使用随机 Bearer token、Host/Origin 检查和健康检查；token 与 supervisor 管理的后端进程同寿命，关窗停止服务后销毁。
- `POST /chat/stream` 默认路由到 Ollama 的 `qwen3.5:0.8b`，并接受 GUI 选择的本地模型或固定云 Provider；只接受 `user`/`assistant` 消息，单条消息上限 16,000 字符、上下文总量 40,000 字符、最多 20 条。未知字段拒绝。
- SwiftUI 页面支持发消息、增量显示回复和停止当前流。对话只保留在当前 app 进程内存中，关闭后不恢复；UI 明示“不保存对话”。
- 模型请求失败时显示经过脱敏的提示，不自动回退到其他 Provider。记忆、文件导入和麦克风仍未接入。

## 模型设置与云端请求

- 页面右上角齿轮按钮打开“模型设置”。默认来源为本地 Ollama；本地模型名称可填写为 Ollama 中已安装的模型 ID。来源和模型 ID 保存在当前 macOS 用户的 `UserDefaults`，不含密钥。
- 云端配置提供千问 `qwen3.8-flash`（中国，按量计费应用 API）、DeepSeek `deepseek-flash`（中国）与 OpenRouter `deepseek/deepseek-v4.1-flash-1017`（Global）。型号和区域固定，不能填写任意端点。默认云服务商为千问；D-010 仍为待决，不代表正式 V1 Provider 选型。
- 云端 API Key 可在设置窗口的 SecureField 保存到 macOS login Keychain：service `com.personal-ai-assistant.phase0.provider`，account 为 `qwen-app`、`deepseek` 或 `openrouter`。界面只显示是否已保存；后端逐次从 Keychain 读取，密钥不进入聊天、本机 API 请求体、环境变量、设置文件或日志。
- 千问应用选项使用普通按量计费 API（`sk-ws-` Key），地址为 `https://maas.qianwenaiapi.com/compatible-mode/v1`，与 Token Plan 个人版的 `sk-sp-` Key 及套餐端点分开。请新建应用 API Key 并保存到 `qwen-app`；不要复用曾在聊天中公开的旧 Key。Token Plan 个人版 Key 仍不用于本自建应用。
- 选择云端来源/Provider 即表示持续授权后续聊天发往该服务商，不再逐条弹出确认框。设置窗口明确显示当前目标、区域和发送行为；切回本地来源即可停止云端出站。后端仍为每个单独请求建立精确 Provider/model/region/purpose/Data Level 的短时 Consent，并在 Keychain 读取前检查 L3 凭据；取消云模式后不会通过其他 Provider fallback。请求按 L2 处理。
- HTTP 401 显示 API Key 认证失败，HTTP 402 显示余额/套餐额度不足。错误不会触发 Provider fallback；云端输出上限为 1,024 tokens。
- 千问 Token Plan 服务端支持文本和 Realtime API，但个人版条款仅允许通过受支持的编程/智能体工具扩展交互调用，明确排除自定义应用后端；因此不在本应用 Provider 列表中直连 `sk-sp-`。GUI 提供适用于自建应用的按量计费 API 选项。详情见 [`qwen-token-plan-integration.md`](qwen-token-plan-integration.md)。

## 验证记录

- `swift build --package-path . --product personal-assistant-beta`：通过。
- `swift test --package-path .`：31 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_beta_api.py tests/test_local_service_process_poc.py tests/test_security_poc.py`：11 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q`：158 项通过（该轮记录，其后新增测试使全量升至 162 项）；`uv run --locked python -m compileall -q pac_poc scripts tests`：通过。
- 千问应用选项改动后：千问相关后端窄回归 26 项通过；Python 全量回归 162 项通过；`swift test --package-path poc/macos-audio` 31 项通过；Beta `.app` 构建成功。运行中 GUI Accessibility 树显示模型 `qwen3.8-flash` 与“模型设置”按钮；设置 sheet 手动操作、Keychain 保存和真实千问 API 请求尚未验证。
- 移除聊天逐条云确认弹窗后：`swift test --package-path poc/macos-audio` 31 项通过，Beta target 构建通过；尚未在运行 GUI 中发起消息做无弹窗手动复核。用户选择云端即持续授权，设置页告知发送目标和切回本地的方法。
- `scripts/run_beta_app.sh` 构建并启动更新后的应用；GUI Accessibility 树确认右上角“模型设置”按钮和当前模型状态显示。设置 sheet 本身以及真实云端请求尚未进行手动 GUI 验收。
- 使用真实本机 Ollama 模型对 `/chat/stream` 发送合成短句，HTTP 200，收到 7 个非空增量片段；未记录回复正文。服务经 supervisor stop 正常退出。

## 下一步与限制

- GUI 已确认可以提交消息并显示回答，也观察到模型设置按钮；设置 sheet 选择/保存路径、停止按钮行为和关闭窗口后的后端清理仍待手动复核。
- 生成请求用 request ID 隔离流片段和收尾状态，避免停止后立即发起的新请求被旧请求回调清除。`swift test --package-path poc/macos-audio` 构建通过，31 项既有 Swift 测试通过；当前尚无专门覆盖 SwiftUI 请求竞态的单元测试。
- 对话不持久化是当前范围选择，不是故障；持久化等用户确认数据保留和加密方案后再做。
- 语音接入作为 B2；开始录音必须由用户在应用内明确操作，音频不落盘，识别失败不切云。
- 千问 Token Plan Realtime 虽是服务端支持能力，个人版 Key 的官方范围不允许用于本项目自建应用；此处不开放云语音入口。应用云语音需使用适用的 API 计费凭据，详情见 `qwen-token-plan-integration.md`。
- 当前启动脚本依赖仓库虚拟环境；所选本地模型须已安装于 Ollama。属于开发测试版，不是独立分发安装器。
