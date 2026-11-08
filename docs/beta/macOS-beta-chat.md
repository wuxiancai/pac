# macOS 测试版：本机文字对话（B0/B1）

状态：`IN PROGRESS`。首个可运行 macOS SwiftUI 测试版已接入当前受认证 Loopback 服务，并通过本机 Ollama 流式文本 API。

## 当前范围

- SwiftUI 应用由 `poc/macos-audio/scripts/run_beta_app.sh` 构建并启动；后端继续由固定 supervisor 进程管理，退出时经私有管道停止。
- 本机服务只绑定 `127.0.0.1`，使用随机 Bearer token、Host/Origin 检查和健康检查；token 与 supervisor 管理的后端进程同寿命，关窗停止服务后销毁。
- `POST /chat/stream` 固定路由到 Ollama 的 `qwen3.5:0.8b`，只接受 `user`/`assistant` 消息；单条消息上限 16,000 字符、上下文总量 40,000 字符、最多 20 条。未知字段拒绝。
- SwiftUI 页面支持发消息、增量显示本机模型回复和停止当前流。对话只保留在当前 app 进程内存中，关闭后不恢复；UI 明示“不保存对话”。
- 模型未就绪或请求失败时显示本机错误提示，不回退到远端 Provider。未接入云端、记忆、文件导入或麦克风。

## 验证记录

- `swift build --package-path . --product personal-assistant-beta`：通过。
- `swift test --package-path .`：31 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_beta_api.py tests/test_local_service_process_poc.py tests/test_security_poc.py`：11 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q`：158 项通过；`uv run --locked python -m compileall -q pac_poc scripts tests`：通过。
- `scripts/run_beta_app.sh` 已构建并启动应用；UI 显示本机模型已连接。随后在 GUI 输入并发送一条短消息，窗口实际显示用户消息和模型回复。
- 使用真实本机 Ollama 模型对 `/chat/stream` 发送合成短句，HTTP 200，收到 7 个非空增量片段；未记录回复正文。服务经 supervisor stop 正常退出。

## 下一步与限制

- GUI 已确认可以提交消息并显示回答；停止按钮行为和关闭窗口后的后端清理尚未实测。
- 对话不持久化是当前范围选择，不是故障；持久化等用户确认数据保留和加密方案后再做。
- 语音接入作为 B2；开始录音必须由用户在应用内明确操作，音频不落盘，识别失败不切云。
- 当前启动脚本依赖仓库虚拟环境、已安装 Ollama 和本地 `qwen3.5:0.8b` 模型，属于开发测试版，不是独立分发安装器。
