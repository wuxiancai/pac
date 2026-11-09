# macOS 测试版：本机文字对话（B0/B1）

状态：`IN PROGRESS`。首个可运行 macOS SwiftUI 测试版已接入当前受认证 Loopback 服务，并通过本机 Ollama 流式文本 API。

## 当前范围

- SwiftUI 应用由 `poc/macos-audio/scripts/run_beta_app.sh` 构建并启动；后端继续由固定 supervisor 进程管理，退出时经私有管道停止。
- 本机服务只绑定 `127.0.0.1`，使用随机 Bearer token、Host/Origin 检查和健康检查；token 与 supervisor 管理的后端进程同寿命，关窗停止服务后销毁。
- `POST /chat/stream` 默认路由到 Ollama 的 `qwen3.5:0.8b`，并接受 GUI 选择的本地模型或固定云 Provider；只接受 `user`/`assistant` 消息，单条消息上限 16,000 字符、上下文总量 40,000 字符、最多 20 条。未知字段拒绝。
- SwiftUI 页面支持发消息、增量显示回复和停止当前流。对话只保留在当前 app 进程内存中，关闭后不恢复；UI 明示“不保存对话”。
- 文件选择器支持用户主动选择 TXT/Markdown；文件经受限 loopback API 导入进程内存，最多 10 MB/文件，可从附件条目移除。所选文件只可用于本机模型；切换到云端时后端在 Gateway 前拒绝带文件的聊天。PDF 尚未开放。安全边界和测试见 [`file-import.md`](file-import.md)。
- 聊天流响应的 `X-PAC-Run-ID` 会传入 UI；页面显示本轮 run 短 ID 与状态。正常结束/失败后向认证的 `/chat/runs/{run_id}` 查询后端状态；用户停止或切换模型时短暂轮询终态。该状态仅供本机进程内观测，不保存对话，也不表示 Provider 一定停止生成。
- 模型请求失败时显示经过脱敏的提示，不自动回退到其他 Provider。长期记忆仍未接入；B2 语音首个代码切片见 [`macOS-beta-voice.md`](macOS-beta-voice.md)，尚待用户实机录音/识别/朗读。

## 模型设置与云端请求

- 页面右上角齿轮按钮打开“模型设置”。默认来源为本地 Ollama；本地模型名称可填写为 Ollama 中已安装的模型 ID。来源和模型 ID 保存在当前 macOS 用户的 `UserDefaults`，不含密钥。
- 每次发送都从当前选择快照 Provider、模型 ID 和云端授权标记，并显式放入 `/chat/stream` 请求。切换来源、云 Provider 或本地模型名称时，若旧请求仍在生成，会立即取消客户端流并使旧请求回调失效；状态栏更新为新选择，后续消息使用新选择。状态栏显示请求中的 Provider/模型，以便辨认本轮实际路由。Provider 侧是否立即停止生成仍受服务端取消语义限制。
- 云端配置提供千问 `qwen3.8-flash`（中国，按量计费应用 API）、DeepSeek `deepseek-flash`（中国）与 OpenRouter `deepseek/deepseek-v4.1-flash-1017`（Global）。型号和区域固定，不能填写任意端点。2026-11-09 用户确认 D-010：V1 默认千问应用 API，另支持 DeepSeek（中国）和 OpenRouter（Global）；能力证据仍依 POC-02 矩阵逐项验收。
- 云端 API Key 可在设置窗口的 SecureField 保存到 macOS login Keychain：service `com.personal-ai-assistant.phase0.provider`，account 为 `qwen-app`、`deepseek` 或 `openrouter`。界面只显示是否已保存；后端逐次从 Keychain 读取，密钥不进入聊天、本机 API 请求体、环境变量、设置文件或日志。
- 千问应用选项使用普通按量计费 API（`sk-ws-` Key），地址为 `https://maas.qianwenaiapi.com/compatible-mode/v1`，与 Token Plan 个人版的 `sk-sp-` Key 及套餐端点分开。请新建应用 API Key 并保存到 `qwen-app`；不要复用曾在聊天中公开的旧 Key。Token Plan 个人版 Key 仍不用于本自建应用。
- 选择云端来源/Provider 即表示持续授权后续聊天发往该服务商，不再逐条弹出确认框。设置窗口明确显示当前目标、区域和发送行为；切回本地来源即可停止云端出站。后端仍为每个单独请求建立精确 Provider/model/region/purpose/Data Level 的短时 Consent，并在 Keychain 读取前检查 L3 凭据；取消云模式后不会通过其他 Provider fallback。请求按 L2 处理。
- HTTP 401 显示 API Key 认证失败，HTTP 402 显示余额/套餐额度不足。错误不会触发 Provider fallback；云端输出上限为 1,024 tokens。
- 千问 Token Plan 服务端支持文本和 Realtime API，但个人版条款仅允许通过受支持的编程/智能体工具扩展交互调用，明确排除自定义应用后端；因此不在本应用 Provider 列表中直连 `sk-sp-`。GUI 提供适用于自建应用的按量计费 API 选项。详情见 [`qwen-token-plan-integration.md`](qwen-token-plan-integration.md)。

## 验证记录

- 2026-11-09 Swift SSE error 事件回归：fake URLProtocol 返回 HTTP 200 加本机安全错误 SSE event，`LocalAPIClient.streamChat` 抛出 `LocalAPIStreamError`，错误说明与事件一致。Swift 全量 38 passed；Beta target build 通过。此为客户端流解码测试，不代表 GUI 上状态文字已实机呈现。

- 2026-11-09 云端错误映射服务端回归：fake DeepSeek adapter 参数化注入 HTTP 401/402/403/429/503，检查 SSE 只含分类提示、不回显 adapter 错误内容，run 最终状态为 FAILED，adapter 只调用一次且无 fallback。`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked --group dev pytest -q tests/test_beta_api.py -k cloud_provider_errors_are_sanitized_and_never_fallback` → 5 passed；后端全量 238 passed。没有真实云请求或 Keychain 访问。该测试只覆盖 API/SSE；GUI 文案仍需实机确认。
- 2026-11-09 本机 Provider 错误映射服务端回归：fake Ollama adapter 抛出模拟内部异常，SSE 显示检查 Ollama/模型的提示，不回显异常细节；run 记录为 failed，usage/cost 仍为 unknown，无云 fallback。与云错误合并的定向回归 6 passed；后端全量 239 passed。仅在运行中的 GUI 观察到云端会话和后端已连接；没有切换设置、发消息或修改会话，GUI 错误消息实机验收待后续。

- 2026-11-09 本机 API HTTP 错误客户端回归：注入仅供测试的 ephemeral URLSession 配置，以 URLProtocol 返回 HTTP 503 和带敏感标记的错误正文；`streamChat` 只抛出 `.requestFailed(statusCode: 503)`，正文不进入 localizedDescription。生产 initializer 仍创建 ephemeral session，保留 loopback delegate 与禁重定向。`swift test --package-path poc/macos-audio` → 37 项通过；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。本次未对运行中 GUI 做手动错误冒烟，也未发起云请求；HTTP 错误的 UI 呈现仍待实机确认。

- 2026-11-09 run 生命周期 UI 接入：`swift test --package-path poc/macos-audio` → 35 项通过，包含 Beta target 编译及 run 状态解码测试。自动化构建通过；本轮未重启正在运行的 Beta 做 GUI 手动冒烟，因此 run 状态标签/取消后的状态更新仍待下次启动后实机确认。

- 2026-11-09 本机模型流式保活：为避免流式响应长时间无 SSE 数据时客户端空闲超时，`/chat/stream` 现在每 15 秒发 SSE 注释 keep-alive，不转发 thinking 或提示词；客户端断开时会取消并关闭上游迭代器。具体无数据根因尚未确认。设置拒绝非有限/非正值和 bool。验证：`uv run --locked --all-extras --all-groups pytest -q tests/test_beta_api.py tests/test_local_model_gateway.py` → 22 passed；`ruff check pac_poc tests`、`mypy`（相关 3 个文件）、`uv lock --check`、`python3 -m compileall -q pac_poc scripts tests` 均通过。完整 Python `pytest -q` → 193 passed、1 failed：`test_bounded_disk_image_exhaustion_preserves_encrypted_data_and_backup[APFS-128]` 在磁盘耗尽脚本返回 `OSError`，与流式保活无关；另有 1 条既有 Starlette/httpx 弃用警告。早先 50 秒 GUI 观察没有记下 Ollama 进程状态，不能据此认定是 thinking；随后发现桌面绑定到了无仓库环境的 app，已用仓库脚本重启。

- 更正实机解释（2026-11-09）：上次 50 秒观察未核对 Ollama 进程，根因不明。用户已确认启动 Ollama 后 PAC 可以聊天；本轮在仓库启动的 GUI 中确认 `ollama / qwen3.5:0.8b` 已连接，并在干净会话收到 `PAC-LOCAL-READY` 精确短答。随后 Ollama loopback `/api/chat` 默认参数下的合成短句成功（返回长度 21，服务端总耗时约 2.51 秒）；仅作本机诊断的 `think:false` 对照耗时约 0.88 秒，没有记录回复正文。模型是否开启 thinking 不是根因结论。Ollama 必须运行且目标模型已安装；本机请求错误会提示检查 Ollama 和模型。未发起云请求。

- GUI 停流/重发复核：在 Ollama 正常运行下启动约 300 字故事请求，点击停止后 UI 立即显示“已停止本轮生成”；随后立即发出“只回复 PAC-RESEND-OK”，等待 30 秒仍显示生成中且无文本，手动停止。对话当时包含长请求/未完成上下文，因此原因未定，不能判为取消实现故障，也不能判通过。关闭合成测试会话并用仓库脚本重启，现在 app/backend 已连接且对话为空；所有请求均留在本机。

- Ollama 取消/队列对照（本机，2026-11-09）：安装版本 `0.40.15`。通过 httpx 启动一个长 `/api/chat` stream，约 2 秒后关闭 client stream，随后马上发送短句。取消后的短请求完成耗时 46.72 秒；未取消流时默认参数短句基线约 2.42 秒，显式 `think:false` 约 0.88 秒。未记录返回正文。Ollama v0.40.15 官方代码的流式路径使用无缓冲 channel，官方 issue [#17131](https://github.com/ollama/ollama/issues/17131) 描述客户端断开时可能泄漏 handler goroutine 并占住 runner semaphore；现象与本机延迟相符，但版本代码/issue 不能单独证明此次延迟由该缺陷造成。见 [v0.40.15 `server/routes.go`](https://github.com/ollama/ollama/blob/v0.40.15/server/routes.go)。这表明 PAC 发起 URLSession 取消后，即使前端立即复位，也不能保证本机 Ollama 立即可服务下一轮；客户端 keep-alive 只防止等待期间 UI 连接超时。

- 2026-11-09 停止状态提示：本机停止显示“已停止接收回复；Ollama 可能仍在结束本机生成。”，云端停止显示“已停止接收回复；云端服务是否停止生成未知。”这描述客户端观测，不承诺上游已结束。`swift test --package-path poc/macos-audio` → 34 项通过；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。仓库脚本启动新 app 后，以本机合成长请求点击停止，GUI 显示上述本机提示。云 Provider 未调用，云文案未做 GUI 出站冒烟。

- 2026-11-09 模型设置 GUI 只读复核：设置 sheet 显示本地/云端来源；检查云端时显示 OpenRouter 固定模型与区域、Keychain 状态“已保存（openrouter）”、删除入口和持续发送披露。未读取/编辑 SecureField，未点击保存或删除，未发送云请求；检查后恢复本机来源。新构建在本地设置下说明 PAC 后端与 Ollama 分开运行，要求启动 Ollama 并安装所选模型，且 PAC 后端已连接不代表 Ollama 已运行。Swift 34 项与 Beta build 通过；当前运行的 app 保留用户对话，未关闭重启来手动验收新提示，文案待下次仓库脚本启动后确认。

- 2026-11-09 修复模型切换反馈：SwiftUI 模型选择变更会取消在途客户端请求、清除其 request ID 并更新当前 Provider/模型状态；发送时仍以当前设置建立不可变请求快照，完成状态显示本轮实际 Provider/模型。`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；本轮未运行测试、未启动 GUI、未发起云请求。

- `swift build --package-path . --product personal-assistant-beta`：通过。
- `swift test --package-path .`：31 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q tests/test_beta_api.py tests/test_local_service_process_poc.py tests/test_security_poc.py`：11 项通过。
- `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q`：158 项通过（该轮记录，其后新增测试使全量升至 162 项）；`uv run --locked python -m compileall -q pac_poc scripts tests`：通过。
- 千问应用选项改动后：千问相关后端窄回归 26 项通过；Python 全量回归 162 项通过；`swift test --package-path poc/macos-audio` 31 项通过；Beta `.app` 构建成功。运行中 GUI Accessibility 树显示模型 `qwen3.8-flash` 与“模型设置”按钮；设置 sheet 手动操作、Keychain 保存和真实千问 API 请求尚未验证。
- 2026-11-09 用户确认千问应用 API Key 已轮换，曾暴露的 Key 已删除。本轮通过 `scripts/run_beta_app.sh` 启动后 GUI 显示本机服务已连接、当前云模型为 `qwen3.8-flash`；模型设置页对 `qwen-app` 的 Keychain 状态查询显示“未配置”。没有输入、读取 Key 内容或保存 Key，也没有发送云请求。用户需在本机设置页保存新 `sk-ws-` Key 后，才能进行真实 API 验证。
- 后续用户报告已保存新的千问 API，千问可以正常聊天；用户确认大模型间可自由切换，切换后当前聊天使用新选择。此为用户实机确认；先前一次合成请求失败记录保留为历史故障样本，不再描述为当前千问连接状态。
- 用户随后确认已在应用中保存新 API Key。设置页状态显示 `已保存（qwen-app）`。经 GUI 向千问 `qwen3.8-flash` 发出一次固定合成提示 `Reply exactly: PAC-QWEN-SMOKE-20261109`；界面进入云端生成状态后返回“云端凭据不可用或请求失败；已停止发送，不会自动切换 Provider。”目前此脱敏错误不能区分 Keychain 读取失败、网络层错误或 Provider 端失败，不能证明请求到达 Provider；未收到回复/usage/cost，因此费用情况也未知。本轮没有重试。
- 用户随后反馈千问已可正常聊天；这是用户报告，本报告未取得对应成功响应、usage 或 cost 证据。
- 针对该错误诊断缺口，`backend/pac_poc/beta_api.py` 现分别映射 Keychain 不可用、HTTPX 传输错误、明确的 Provider HTTP 状态，以及无法识别/处理错误；消息不包含密钥和上游响应正文。传输错误明确提示服务端是否收到请求/是否计费未知，并要求先查用量再重试。Python 编译检查通过，未运行测试；随后重启 Beta 并确认本机服务连接，未再次出站请求。历史那次错误无法追溯分类。
- 移除聊天逐条云确认弹窗后：`swift test --package-path poc/macos-audio` 31 项通过，Beta target 构建通过；尚未在运行 GUI 中发起消息做无弹窗手动复核。用户选择云端即持续授权，设置页告知发送目标和切回本地的方法。
- `scripts/run_beta_app.sh` 构建并启动更新后的应用；GUI Accessibility 树确认右上角“模型设置”按钮和当前模型状态显示。设置 sheet 本身以及真实云端请求尚未进行手动 GUI 验收。
- 使用真实本机 Ollama 模型对 `/chat/stream` 发送合成短句，HTTP 200，收到 7 个非空增量片段；未记录回复正文。服务经 supervisor stop 正常退出。

## 下一步与限制

- 用户已确认千问 API 可正常聊天，并已验证模型可以自由切换且当前聊天按新选择发送。先前单次合成探测错误仍无法追溯是否到达 Provider/计费；当前不据此判断服务可用性。
- 2026-11-09 收尾复核：在当前 Beta GUI 切换到本机 Ollama，发送合成的长回复请求，确认界面进入“正在使用本地模型生成”，点击“停止”后状态变为“已停止本轮生成”、停止按钮消失、输入框恢复；没有发起云端请求。测试后经启动脚本重启应用，恢复原先 OpenRouter 选择和未发送草稿。Provider 侧是否因此停止生成/计费仍未知。Cmd-Q 时 app/backend 退出清理已有用户验证。费用预算硬拦截未实现，不能据此依赖当前 Beta 控制月度支出。
- 生成请求用 request ID 隔离流片段和收尾状态，避免停止后立即发起的新请求被旧请求回调清除。`swift test --package-path poc/macos-audio` 构建通过，31 项既有 Swift 测试通过；当前尚无专门覆盖 SwiftUI 请求竞态的单元测试。
- 对话不持久化是当前范围选择，不是故障；持久化等用户确认数据保留和加密方案后再做。
- 2026-11-09 用户确认 D-003：不保存对话；安全日志保留 30 天；临时会话/音频缓存于退出或中断时清理；不备份对话。当前 Beta 不写持久安全日志；若之后加入，须仅记录安全事件元数据并实现 30 天清理，排除正文、凭据和音频。模型权重和用户明确保留的模型下载缓存不属于临时会话缓存。
- B2 初始 SwiftUI 录音/本机 ASR/手动 TTS 接入见 [`macOS-beta-voice.md`](macOS-beta-voice.md)。录音只由用户点击按钮启动，音频不落盘，识别失败不切云；真实设备链路仍待手动冒烟。
- 千问 Token Plan Realtime 虽是服务端支持能力，个人版 Key 的官方范围不允许用于本项目自建应用；此处不开放云语音入口。应用云语音需使用适用的 API 计费凭据，详情见 `qwen-token-plan-integration.md`。
- 当前启动脚本依赖仓库虚拟环境；所选本地模型须已安装于 Ollama。属于开发测试版，不是独立分发安装器。
