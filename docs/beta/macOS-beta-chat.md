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
- 云端首批配置提供 DeepSeek `deepseek-flash`（中国）与 OpenRouter `deepseek/deepseek-v4.1-flash-1017`（Global）。区域和型号固定，不能填写任意端点。D-010 仍为待决，不代表正式 V1 Provider 选型。
- 云端 API Key 可在设置窗口的 SecureField 保存到 macOS login Keychain：service `com.personal-ai-assistant.phase0.provider`，account 为 `deepseek` 或 `openrouter`。界面只显示是否已保存；后端逐次从 Keychain 读取，密钥不进入聊天、本机 API 请求体、环境变量、设置文件或日志。
- 每次发送云端请求前，GUI 展示将发送的完整对话、服务商、型号和区域。用户点击“同意并发送这一次”后，后端只为该请求创建精确匹配的短时 Consent；取消时不读 Keychain、不发请求。请求按 L2 处理；检测到常见 API Key、Bearer 凭据或私钥标记时，在 Keychain 读取和网络出站前拒绝。
- HTTP 401 显示 API Key 认证失败，HTTP 402 显示余额/套餐额度不足。错误不会触发 Provider fallback；云端输出上限为 1,024 tokens。
- 千问 Token Plan 服务端支持 Realtime API，但个人版 Key 条款限定于编程/智能体工具内的交互使用，不适用于本项目自建应用，因此 GUI 不提供个人版 Token Plan 路由。如要加入千问应用内模型，需先取得适用于自定义应用的凭据并补相应验证。详情见 [`qwen-token-plan-integration.md`](qwen-token-plan-integration.md)。

## 验证记录

- `swift build --package-path . --product personal-assistant-beta`：通过。
- `swift test --package-path .`：31 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_beta_api.py tests/test_local_service_process_poc.py tests/test_security_poc.py`：11 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q`：158 项通过；`uv run --locked python -m compileall -q pac_poc scripts tests`：通过。
- 模型设置改动后：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；`swift test --package-path poc/macos-audio` 31 项通过；Python 全量回归 159 项通过；`git diff --check` 通过。
- `scripts/run_beta_app.sh` 构建并启动更新后的应用；GUI Accessibility 树确认右上角“模型设置”按钮和当前模型状态显示。设置 sheet 本身以及真实云端请求尚未进行手动 GUI 验收。
- 使用真实本机 Ollama 模型对 `/chat/stream` 发送合成短句，HTTP 200，收到 7 个非空增量片段；未记录回复正文。服务经 supervisor stop 正常退出。

## 下一步与限制

- GUI 已确认可以提交消息并显示回答，也观察到模型设置按钮；设置 sheet 选择/保存路径、停止按钮行为和关闭窗口后的后端清理仍待手动复核。
- 生成请求用 request ID 隔离流片段和收尾状态，避免停止后立即发起的新请求被旧请求回调清除。`swift test --package-path poc/macos-audio` 构建通过，31 项既有 Swift 测试通过；当前尚无专门覆盖 SwiftUI 请求竞态的单元测试。
- 对话不持久化是当前范围选择，不是故障；持久化等用户确认数据保留和加密方案后再做。
- 语音接入作为 B2；开始录音必须由用户在应用内明确操作，音频不落盘，识别失败不切云。
- 千问 Token Plan Realtime 虽是服务端支持能力，个人版 Key 的官方范围不允许用于本项目自建应用；此处不开放云语音入口。应用云语音需使用适用的 API 计费凭据，详情见 `qwen-token-plan-integration.md`。
- 当前启动脚本依赖仓库虚拟环境；所选本地模型须已安装于 Ollama。属于开发测试版，不是独立分发安装器。
