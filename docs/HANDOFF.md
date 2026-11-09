## 2026-11-09：阶段 3 Uvicorn WebSocket 消息上限

- 实时语音路由在应用层会拒绝大于 12,800 字节的 PCM，但此前 Uvicorn 使用默认 16 MiB WebSocket 消息上限，单帧在应用拒绝前仍可被服务器完整接收。现将服务端 `ws_max_size` 设为 12,804 字节，容纳 4 字节序号和协议最大 12,800 字节 PCM。
- 新增服务器配置回归；同时重跑实时 WebSocket 和无 Content-Length 的一次性语音上限用例。3 个定向用例通过；Ruff/mypy 通过；后端全量 252 passed，1 条既有 Starlette/httpx 弃用警告。
- 更新 `docs/beta/macOS-beta-voice.md`、`docs/poc/phase0-traceability.md`、`docs/TASKS.md` 和 `docs/PROJECT_CONTEXT.md`。未启动麦克风、未操作 GUI/Keychain、未发云请求。

## 2026-11-09：阶段 3 一次性语音 API 有界读取

- `/voice/transcribe` 先前用 `request.body()` 完整缓存后再检查最大 30 秒，未提供 Content-Length 的请求可在检查前占用无界内存。现改为遍历 ASGI request stream，累计字节超限立即返回 413；拒绝负 Content-Length。
- 批量 `transcribe_pcm16le` 也改用取消安全 worker，保证调用线程结束前异步会话锁不会释放。
- 回归以无 Content-Length 的 HTTPX 异步分块请求验证 32,000 字节合法数据可识别、超出 2 字节时 413 且识别器只收到合法请求。定向 2 passed；Ruff/mypy 通过；后端全量 251 passed，1 条既有 Starlette/httpx 弃用警告。
- 更新 `docs/beta/macOS-beta-voice.md`、`docs/poc/phase0-traceability.md`、`docs/TASKS.md` 和 `docs/PROJECT_CONTEXT.md`。未启动麦克风、未操作 GUI/Keychain、未发云请求。

## 2026-11-09：阶段 3 语音 WebSocket 取消等待 ASR worker

- 语音识别通过 `asyncio.to_thread` 调用同步 ASR。协程取消并不会中止已运行的线程，旧逻辑可能在该线程还在使用 recognizer 时执行 abort 并释放会话锁。现在 `_run_voice_worker` 对线程工作做 shield；捕获取消后等待 worker 结束，再传播取消，由 finally 执行 abort/释放锁。begin、frame、end 和 abort 调用均走此边界。
- 新增回归：阻塞 worker 运行中取消请求任务，确认任务在释放线程前仍未完成，释放后再以 CancelledError 结束。
- 验证：`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q tests/test_beta_api.py` → 28 passed；Ruff、mypy 通过；后端全量 → 250 passed，1 条既有 Starlette/httpx 弃用警告。
- 更新 `docs/beta/macOS-beta-voice.md`、`docs/TASKS.md` 和 `docs/PROJECT_CONTEXT.md`。没有启动麦克风或操作 GUI，未读 Keychain、未发云请求。

## 2026-11-09：阶段 2 UsageLedger 数值边界校验

- Ledger 写入现拒绝 NaN/无穷时间戳、布尔/非整数/负毫秒延迟，以及布尔、负数或非有限 `audio_seconds`，保持 Usage API 的时间和时长字段为有效 JSON 数值或 `null`。不改变 token/cost 语义、进程内保留或预算状态。
- 回归覆盖时间戳 NaN/Infinity、布尔延迟，以及音频时长 NaN/Infinity/负值/布尔值。
- 验证：`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q tests/test_usage.py` → 11 passed；Ruff、mypy 通过；后端全量 → 249 passed，1 条既有 Starlette/httpx 弃用警告。
- 更新 `docs/beta/orchestrator-framework.md`、`docs/PROJECT_CONTEXT.md` 和 `docs/TASKS.md`。未操作 GUI、未访问 Keychain、未发起云请求。

## 2026-11-09：验证 macOS PDF worker 启动前虚拟内存限额

- 针对 Python 进程启动后设置 rlimit 失败，额外使用 `/bin/sh` 在 `exec` worker 前执行 `ulimit -v`，分别测试 768 MiB、1 GiB、1.5 GiB。当前 macOS 均返回 `cannot modify limit: Invalid argument`，未启动 worker。
- 此结果排除了当前设备上简单改为 shell 启动器的方案；不代表所有 macOS 版本都相同，也没有证明其他隔离机制不可行。PDF 仍禁用。
- 更新 `docs/beta/file-import.md`、`docs/TASKS.md` 和 `docs/PROJECT_CONTEXT.md`，保留 D-012 门禁和缺少恶意语料/压力验证的状态。
- 这是只读系统限额探测；未解析用户 PDF、未访问 Keychain、未发起网络请求。

# 2026-11-09：透传 Provider 缓存命中 token

- 根据阿里云 Model Studio 与 DeepSeek 官方文档补齐原始用量字段：OpenAI-compatible `usage.prompt_tokens_details.cached_tokens`、DeepSeek `usage.prompt_cache_hit_tokens`。Gateway 在数值为非负整数且不超过已知 prompt 总数时才保留；UsageLedger 做一致性校验；认证 `/usage` 返回该字段，Swift client 解码并在用量面板显示。没有按价目表推算费用，也没有启用 D-005 预算门。
- 资料核对：Qwen 官方资料说明 cached token 字段及地区/cache 定价；DeepSeek 官方资料说明 cache hit/miss 与峰谷定价；OpenRouter 说明 `usage.cost` 为 USD 推理费用，credit 购买另收平台费。来源链接和预算实现缺口已写入 `docs/beta/orchestrator-framework.md` 与 `docs/poc/phase0-traceability.md`。
- 验证：定向 8 passed；Ruff、mypy 通过；后端全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 242 passed，1 条既有 Starlette/httpx 弃用警告；`swift test --package-path poc/macos-audio` → 40 passed；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。未发起 Provider API 请求、未读取 Keychain、未操作 GUI。
- D-005 未完成：估价依据/版本和更新、外币归一、未知值 fail-closed、跨进程累计、并发与自然月边界仍需闭环。

# 2026-11-09：校正用量报告中的过期说明

- 审阅阶段 2 编排报告时发现 Usage 首段仍称流式 Provider 不透传 token，与下方已记录的 Ollama/OpenAI-compatible 最终帧 token 透传及 OpenRouter 实际 USD 处理相矛盾。
- 已把首段更正为当前代码状态：仅实际返回的 token 计数和 OpenRouter 合法 `usage.cost` 可进入 ledger；缺失值仍 unknown/null；真实 Beta 型号 E2E、跨 Provider 人民币费用归一和 D-005 硬拦截仍未完成。下一步描述也区分 mock 协议回归与供应商真实证据。
- 本段仅修正文档，未运行测试；依据为当前实现及既有测试证据。没有云请求、Keychain 读取或 GUI 会话改动。

# 2026-11-09：补齐聊天 HTTP 断连生命周期回归

- 新增 ASGI 层聊天断连回归，真实调用 `/chat/stream`，在上游 adapter 阻塞期间模拟 `http.disconnect`。验证上游异步流被关闭、run 查询终态为 `cancelled`，UsageLedger 对应记录也为 `cancelled`。
- 验证：在 `backend/` 执行定向用例 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_beta_api.py::test_chat_http_disconnect_marks_run_cancelled_and_closes_upstream` → 1 passed；后端全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 240 passed，1 条既有 Starlette/httpx 弃用警告；`UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check tests/test_beta_api.py` 通过。
- GUI 手动取消/断连仍待干净 Beta 会话复核；本回归未访问云 Provider、Keychain、麦克风，也未增加持久化。
- 下一步继续 B1 可自动验证项和 B5/TASKS 中可本地闭环工作；云 API usage/cost E2E 与 UI 呈现仍保留对应门槛。

# 2026-11-09：将 PDF POC 自动回归纳入 CI

- 检查发现 GitHub Actions 安装 `phase0-security` 和 `phase0-embedding`，但没有安装 `phase4-pdf-poc`；因此 `tests/test_pdf_import_poc.py` 会因 `pytest.importorskip("pypdf")` 整个跳过，CI 未覆盖已存在的 PDF 隔离解析回归。
- `.github/workflows/ci.yml` 现显式安装 `phase4-pdf-poc`。`docs/beta/file-import.md` 和 `docs/TASKS.md` 已记录：CI 会执行 POC 测试，但 PDF 仍禁用，硬内存隔离、恶意 PDF 语料及真实压力/超时测试缺口不变。
- 验证：在 `backend/` 执行 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase4-pdf-poc --group dev pytest -q tests/test_pdf_import_poc.py` → 5 passed；`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 239 passed，1 条既有 Starlette/httpx 弃用警告。远端 GitHub Actions 尚未运行当前提交。
- 下一步继续处理阶段 2 可本地闭环工作；B1 的 UI 错误呈现仍需干净 Beta 会话手动验收，B5 的 GUI 文件选择/移除/聊天引用也待手动冒烟。PDF 不能因这些自动测试通过而启用。

# 2026-11-09：阶段 0 收尾并启动阶段 1

## 阶段 4 B5 Swift 文件导入请求契约回归（2026-11-09）

- `LocalAPIClientTests` 增加 URLProtocol fixture，验证导入请求为认证 POST 到 loopback `/imports/text?filename=notes.md`，请求只传 basename 和文件内容，不传原始路径；成功响应正确解码为 `LocalImportedTextFile`。
- 另验证 PDF 后缀和超出 10 MiB 的文件均在 URLProtocol 收到请求前被客户端拒绝。客户端并不自行解析 PDF，正式导入白名单和 GUI 保持 TXT/Markdown。
- 验证：`swift test --package-path poc/macos-audio` → 40 passed；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；`git diff --check` 通过。此为请求层自动化证据，不代表 GUI 文件选择/移除/聊天引用手动冒烟已通过；当前运行 GUI 未被改动。
- 下一步在干净 Beta 测试会话验证 UI 文件选择、移除和仅本机模型使用；PDF 仍需解决 macOS 硬内存隔离和恶意样本压力门。

## 阶段 2 B1 Swift SSE 错误事件解码回归（2026-11-09）

- Swift 客户端新增 URLProtocol 流 fixture，返回 HTTP 200 的 SSE `error` 事件；确认 `streamChat` 转成 `LocalAPIStreamError`，localizedDescription 保留服务端已经脱敏的 Ollama 提示，便于 UI 展示。
- 验证：`swift test --package-path poc/macos-audio` → 38 passed；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；`git diff --check` 通过。未触碰当前运行 GUI 会话。
- 客户端错误解码链路已自动覆盖；状态文字在 Beta 界面里的实机可见性仍需在不打扰现有云端会话的测试窗口确认。

## 阶段 2 B1 本机模型错误映射 API 回归（2026-11-09）

- 新增 fake local adapter 错误回归：本机 stream 抛出模拟内部异常时，SSE 返回 Ollama 操作提示且不回显内部异常；UsageLedger 将 run 记为 failed，token 和费用保持 unknown；adapter 调用一次，不切云端。
- 验证：本机错误 + 云 Provider 错误映射定向 6 passed；Ruff 和 mypy 通过；后端全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 239 passed，1 条既有 Starlette/httpx 弃用警告。
- GUI 目前是用户正在使用的 OpenRouter 会话；仅检查到服务连接正常，未切换设置、发送消息或改动会话。应用层错误提示的 GUI 实机验收仍待之后合适的干净测试会话。

## 阶段 2 B1 云 Provider 错误映射 API 回归（2026-11-09）

- `backend/tests/test_beta_api.py` 新增 fake adapter 参数化回归，覆盖 HTTP 401/402/403/429/503；每种响应均检查 SSE 使用经分类的安全提示、不回显 adapter 错误正文、run 状态最终为 FAILED，且所选 adapter 只调用一次（没有 fallback）。
- 验证：定向 `tests/test_beta_api.py -k cloud_provider_errors_are_sanitized_and_never_fallback` → 5 passed；后端全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 238 passed，1 条既有 Starlette/httpx 弃用警告；Ruff、mypy、`git diff --check` 通过。全部为 fake adapter，无云请求、无 Keychain 读取。
- 仍需实机确认错误消息在 GUI 中的呈现；这里的 API 测试不替代 GUI 验收。下一段继续 B1 本机错误 UI 或 B5 文件导入冒烟主线。

## 阶段 2 B1 HTTP 错误正文脱敏回归（2026-11-09）

- Swift `LocalAPIClient` 增加内部测试用 `URLSessionConfiguration` 注入 initializer；生产入口仍创建 ephemeral session，使用 loopback-only delegate 并拒绝重定向。
- URLProtocol fixture 模拟本机 `/chat/stream` HTTP 503，响应正文含敏感标记；验证客户端仅抛 `.requestFailed(statusCode: 503)`，不暴露正文。
- 验证：`swift test --package-path poc/macos-audio` → 37 passed；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。未做 GUI 手动错误冒烟、未发云请求。UI 错误呈现及云 API 错误 UI 仍待实机/授权内验证。
- 下一步继续 B1 错误路径与 B5 TXT/Markdown 导入 GUI 冒烟；本轮现有 GUI 窗口/状态自动化检查超时，尚无该 GUI 检查的可用结果。

## 阶段 4 PDF 安全解析 POC（2026-11-09）

- 加入仅供 POC 使用的可选依赖 `pypdf==7.0.0`；默认 Beta 依赖和文件导入 UI/API 均未启用 PDF。
- 新增隔离子进程解析入口，限制输入 10 MiB、墙钟 5 秒、CPU 软/硬限额 4/5 秒、页数 100、提取文本 200,000 字符，并设置 pypdf 对象数量、流解压输出/工作量、页树深度/条目等边界。超时会终止子进程。
- POC 测试：覆盖有效 PDF、输入超限、无效内容、页树超限，以及父进程将子进程超时转换为安全拒绝（模拟）共 5 项；窄回归 5 passed，Ruff 通过。增加超时用例后的完整后端回归 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 233 passed，1 条既有 Starlette/httpx 弃用警告；`git diff --check` 通过。
- 后续做了 macOS 本机限额可行性探测：尝试对 `RLIMIT_AS`、`RLIMIT_DATA`、`RLIMIT_RSS` 设置 512 MiB 均失败，错误为 `ValueError: current limit exceeds maximum limit`；CPU rlimit 可设置，但内存硬限额仍无可用实现。恶意 PDF 样本、CPU/墙钟压力测试及对象数/解压炸弹专项用例也未完成。
- 依据 D-012，PDF 继续禁用；本 POC 不构成启用或产品保证。后续须采用可在目标 macOS 上验证的进程内存隔离方案，再补恶意语料和压力用例。详见 `docs/beta/file-import.md`。
- 后续：补齐可在 macOS 验证的内存与恶意样本测试，再评估是否将解析器接入导入路径。其间继续推进不依赖 PDF 的主线。详见 `docs/beta/file-import.md`。

## 阶段 2 OpenRouter 流式实际费用透传（2026-11-09）

- `ProviderStreamChunk` 扩展可选费用值/币种。只有固定 OpenRouter 适配器从最终 usage 帧收到有限、非负 `usage.cost` 时，账本才保存 actual USD；其他 Provider 不推价。聊天 SSE 客户端仍只接收文本 delta。
- OpenRouter 官方 [Chat Completions](https://openrouter.ai/docs/api/api-reference/chat/create-a-chat-completion) 文档将 `usage.cost` 列为 usage 字段，[支持资料](https://openrouter.ai/support)说明费用依据 Provider 使用量计算。相关流式映射仅由 mock 覆盖，未向当前 Beta 精确型号发送真实云请求。无字段/流中断时仍 UNKNOWN；无汇率换算、未开启人民币预算拦截。
- 验证：阶段窄回归 57 passed，Ruff/mypy 通过；全量 Python `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 228 passed，1 条既有 Starlette/httpx 弃用警告。
- 下一步：全量回归完成后记录结果并提交；继续处理 D-005 的 provider 费用覆盖和 CNY 归一缺口，不以单一 Provider 的 USD 字段代替预算门验收。

## 阶段 2 精确型号能力清单接入（2026-11-09）

- 新增随包 `beta_model_capabilities.json`，按现有 POC 精确登记本机 `qwen3.5:0.8b`、DeepSeek `deepseek-flash`、OpenRouter `deepseek/deepseek-v4.1-flash-1017` 的文本/流式证据。工具能力样本有限，状态为 LIMITED；千问应用 API 型号和其他未收录型号保持 UNKNOWN。
- 默认 Beta composition root 装配并注入该 registry；认证 `GET /model-capabilities?provider_id=...&model_id=...` 查询状态与证据。没有启用新工具能力，基本聊天行为未变。JSON 已包含于 wheel package data。
- 验证：能力/API 窄回归 39 passed；Ruff、mypy 通过；wheel 内容检查确认清单已打包；全量 Python 228 passed，1 条既有 Starlette/httpx 弃用警告。无云请求、无 Keychain 读取。
- 下一步继续阶段 2 主线；正常 Beta 启动时顺带验收用量面板和 capability 查询。真实云 usage、费用预算依各自验证门槛继续追踪。

## 阶段 2 Provider token usage 透传（2026-11-09）

- Gateway 新增 `ProviderStreamChunk`，适配器可将文本增量与最终帧的 input/output token 分开返回；聊天 SSE 仍仅发送文本 delta。Ollama 读取完成帧的 `prompt_eval_count`/`eval_count`；固定云 Provider 请求带 `stream_options.include_usage=true` 并解析 OpenAI-compatible usage 帧。
- 已核对 [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[阿里云 Model Studio streaming](https://help.aliyun.com/en/model-studio/stream)、[OpenRouter Chat Completions](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request?explorer=true) 官方协议文档。未发云请求或读 Keychain；精确 Beta 型号实际兼容性仍需按触发条件核对。中断/缺帧时 usage 保持 UNKNOWN，费用保持 UNKNOWN/null，不估算，不实现预算门。
- 验证：Python 窄回归 56 passed；Ruff 与相关 mypy 通过；全量 Python `pytest -q` → 226 passed，1 条既有 Starlette/httpx 弃用警告。Usage UI Swift 36 项和 Beta build 已于前一提交验证。
- 下一段继续处理单助理/usage 主线；正常 GUI 启动时顺带验收用量面板。预算门须先得到精确 Provider 费用来源、币种归一与缺失 usage 规则；D-005 的决策和安全前提不因 token 透传而改变。

## 阶段 2 macOS 用量面板（2026-11-09）

- macOS Beta 新增“用量”面板，调用认证 loopback `GET /usage` 显示本进程最近的 Provider/model、区域、状态、耗时、token 和费用状态。只有服务端实际/估算记录才显示数值；未知继续显示为空/未知，不估算。
- 用量 ledger 仍限进程内，应用退出清空；面板只读，不发模型请求、不访问 Keychain。没有增加持久化或预算逻辑。
- 验证：`swift test --package-path poc/macos-audio` → 36 项通过；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功。新增 decoder regression 覆盖 UNKNOWN/null 响应。GUI 面板手动冒烟待下次正常启动确认。
- 下一段：结合正常 Beta 启动检查空记录、未知值呈现和认证失败状态；之后继续阶段 2 的真实 usage 语义工作，但须逐 Provider 核实来源并在未授权时不发云请求。阶段状态和延期条件见 `docs/TASKS.md`、`docs/beta/orchestrator-framework.md`。

## 阶段 2 Usage 首段（2026-11-09）

- 新增进程内 `UsageLedger` 与认证 `GET /usage?limit=50`，每个 chat run 完成/失败/取消时记录路由、region/purpose/data level、run 状态和耗时；记录最多 512 条，退出清空，不保留对话、回复、Key 或音频。额度 1–100 可选。
- 当前流式 Provider 适配器没有向统一接口交付用量/费用 metadata，故 token 与费用为 null、usage/cost 状态为 `unknown`；没有估算费用、账单承诺或预算拦截。后续须先逐 Provider 核对实际 usage 来源、币种和缺失行为，再推进 D-005 硬预算。
- 验证（`backend/`）：`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_usage.py tests/test_beta_api.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_local_model_gateway.py` → 46 passed，1 条既有 Starlette/httpx 弃用警告；Ruff 和 mypy 通过。未发云请求、不读 Keychain、不采集麦克风；未做 GUI 手工冒烟。
- 阶段总数：规格书定义阶段 0–6，共 7 个；阶段 0 Beta 范围、阶段 1 当前决策允许的底座已完成，当前继续阶段 2。阶段路线详见 `docs/TASKS.md`。

## 能力报告装配入口（2026-11-09）

- 为精确型号能力报告新增严格 schema version 1 JSON 装配器：校验 manifest/report/entry 字段、枚举、正整数 context limit、精确型号唯一性；有能力声明的报告需有时间戳和证据引用；省略能力保持 UNKNOWN，不根据 Provider 或型号名称推断。
- 装配入口尚未接入 Beta 默认运行时，没有新增实际启用的模型能力。只有核对具体 Provider/model 的本地证据后，才应显式创建 registry 并注入 Orchestrator。
- 验证（`backend/`）：`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_model_capability_registry_poc.py tests/test_orchestrator.py tests/test_beta_api.py tests/test_local_model_gateway.py` → 43 passed，1 条既有 Starlette/httpx 弃用警告；Ruff 和 mypy 通过。未发云请求、不读 Keychain、不启用新能力。代码说明见 `docs/beta/orchestrator-framework.md`。
- 下一步：以确切 POC 证据形成少量可装配报告，再决定注入的运行时范围；GUI run 状态及 TXT/Markdown 选择/移除手动冒烟待下次正常启动顺带确认。

## 本机文本文件导入首段（2026-11-09）

- 完成 TXT/Markdown 首个可用导入闭环：macOS 用户文件选择、security-scoped read、限定 10 MiB 有界读取；后端检查扩展名/无路径文件名/严格 UTF-8/NUL/大小，内容只放进容量受限的进程内 Registry，提供用户删除接口。
- 聊天引用只传进程内 import UUID；上下文 builder 将资料作为不可信 JSON 参考内容并添加固定 system 指引。导入资料只用于本机模型，API 在 Gateway 前拒绝所有带资料的云请求。支持最多 4 个文件、累计暂存最多 20 MiB，按编排后所有消息的 `content` 字符总数计算 40,000 字符上限，不自动截断。
- PDF 仍禁用，继续完成解析器资源限制 POC 后再启用；GUI 文件选择/移除手动冒烟待下次启动。没有持久化、目录扫描或原文件路径传输。详见 `docs/beta/file-import.md`。
- 验证：导入相关 Python 窄回归 45 passed，编排相关 Python 窄回归 34 passed，Ruff/mypy 通过；`swift test --package-path poc/macos-audio` 35 passed 且 Beta target 编译通过。仅一条既有 Starlette/httpx 弃用警告。未读 Keychain、无云请求、无麦克风采集。
- 下一步继续核心功能框架；GUI 冒烟待应用下次常规启动时顺带确认，PDF 安全解析独立推进，已知 Ollama 偶发现象继续留在回修清单。

## macOS run 状态反馈（2026-11-09）

- Swift 客户端现在读取 `X-PAC-Run-ID`，将 run ID/状态作为独立流事件交给 Beta UI；聊天页显示 run 短 ID 和本机生命周期状态。正常结束/失败后调用认证的 `GET /chat/runs/{run_id}`；用户停止或切换模型后短暂轮询后端终态。
- `swift test --package-path poc/macos-audio` → 35 项通过，Beta target 编译通过。增加 run 状态枚举解码测试。没有重启 GUI 做手动冒烟；状态标签、停止后回传仍需下次启动实机确认。未发云请求、未读取 Keychain、未采集麦克风。
- 下一步继续完善核心框架/用户功能；下次允许 GUI 手动检查时，顺手验收状态标签和取消终态。已知非阻塞问题仍登记，不回到局部排查。

## 总助理能力校验接缝（2026-11-09）

- 将 `ModelCapabilityRegistry` 接入 `MainAssistantOrchestrator`。请求可声明必需能力；编排层按精确 Provider/model 检查支持证据，UNKNOWN/UNSUPPORTED/LIMITED 在 Gateway 创建请求前拒绝。覆盖自选未知型号被拦截且不调用 Gateway、精确证据型号可通过。
- 当前 Beta 基础文本流不声明额外能力，因此不改变本机模型配置与现有云路由；工具和多模态尚未启用，也没有被本次接缝误报为支持。
- 验证：窄回归 31 passed；Ruff 与 mypy 通过；一条既有 Starlette/httpx 弃用警告。无云请求、无 Keychain 读取、无麦克风采集。详见 `docs/beta/orchestrator-framework.md`。
- 下一步将已证实能力逐项装配进运行时，再把 run 状态接到 GUI 进度/取消反馈；保持主线优先策略，偶发的 B1/Ollama 取消后延迟问题仍在非阻塞回修队列。

## 框架主线与开发节奏（2026-11-09）

- 用户明确要求后续优先完成整体框架和主要功能；对不影响闭环的小问题记入待回修项，主线成形后集中处理。已将规则写入根目录 `AGENTS.md`、`docs/TASKS.md`。核心功能/安全/隐私/授权阻断仍优先处理；偶发现象先记录证据，不臆断代码根因。
- 本轮实现 `RunRegistry`：每次聊天有 run ID 和 CREATED/RUNNING/COMPLETED/FAILED/CANCELLED 状态；`X-PAC-Run-ID`、SSE done 事件与认证 `GET /chat/runs/{run_id}` 可查询生命周期。状态元数据限于进程内、有界、不含对话正文。
- 验证：窄回归 26 passed；Ruff 和 mypy 通过；一条既有 Starlette/httpx 弃用警告。无云请求、无 Keychain 读取、无麦克风采集。记录见 `docs/beta/orchestrator-framework.md`。
- 非阻塞回修：Ollama 取消长流后紧接请求变慢，根因未证实；现有停止文案已如实说明。已登记在 `TASKS.md`，整体主线完成后再决定是否集中排查。
- 下一步继续补主助理能力/上下文策略和用户可用功能骨架；不要以偶发网络或模型表现中断主线。

## 单助理编排框架起步（2026-11-09）

- 用户要求先把框架开发出来。本轮在现有本机 Beta `/chat/stream` 上抽出 `MainAssistantOrchestrator`、`ConversationTurn` 和可替换 `ContextBuilder`；当前只启用 `main_assistant`，默认上下文仅透传本轮明确消息。API 继续承担认证、云 Consent/Policy、SSE 和 UI 错误映射，不改变现有本地/云路由行为。
- 增加编排框架说明 `docs/beta/orchestrator-framework.md`，并在 `TASKS.md` 增列后续框架工作包。没有加入 Agent 团队、任意工具、长期记忆、后台续跑或持久化。
- 验证：`backend/` 下窄回归 `tests/test_orchestrator.py tests/test_beta_api.py tests/test_local_model_gateway.py` → 24 passed；Ruff 检查通过；mypy 检查通过。仅有既有 Starlette/httpx 弃用警告。未发云请求、未读 Keychain、未采集麦克风。
- 下一步继续完善单助理运行边界和模型能力约束，然后逐步扩展框架接缝；暂不回头排查 Ollama 上游取消细节。开始前检查 Git 状态，勿覆盖用户当前运行 GUI 或会话。

## B1 本机流式保活继续开发（2026-11-09）

- 本轮只读复核模型设置：云端说明完整显示 Provider、模型、区域及持续发送行为；OpenRouter 状态显示“已保存”，未读取 Key 内容。检查后恢复本机来源，未发云请求，也未覆盖当前聊天。
- 本机设置帮助现明确说明 PAC 后端与 Ollama 是两个独立进程；须启动 Ollama 并安装所选模型，“PAC 服务已连接”不代表 Ollama 已运行。`swift test --package-path poc/macos-audio` → 34 passed；Beta build 成功。当前运行 GUI 保留用户本地对话，未为显示新帮助文字而关闭；新文案将在下次从仓库脚本启动后生效，尚未 GUI 验收。
- 之前一次 GUI 等待 50 秒无回复时没有记录 Ollama 服务状态，因此不能判定是服务未启动还是模型延迟；SSE keep-alive 的自动回归有效，真实 thinking 原因尚未单独确认。Ollama 服务须在本机运行且所选模型已安装；后台本机错误提示会指引检查这两项。用户本轮已打开 Ollama 并确认 PAC 本地模型可以聊天。
- 本机 `/chat/stream` 每 15 秒输出 SSE 注释 keep-alive，不暴露 thinking 或提示词；断开时会取消待取的上游 delta 并关闭 iterator。
- 回归：`tests/test_beta_api.py tests/test_local_model_gateway.py` 22 passed；Ruff、mypy（相关 3 文件）、`uv lock --check`、compileall 通过。Python 全量 193 passed，1 failed：`test_bounded_disk_image_exhaustion_preserves_encrypted_data_and_backup[APFS-128]` 受磁盘耗尽脚本 OSError 失败，与本次代码无关；1 条 Starlette/httpx deprecation warning。
- 实机复核：从 `poc/macos-audio/scripts/run_beta_app.sh` 启动后，GUI 显示本机服务已连接、模型 `ollama / qwen3.5:0.8b`。干净会话中的短句得到精确回复；同时本机 Ollama 默认参数 `/api/chat` 合成短句返回完成，耗时约 2.51 秒；显式 `think:false` 对照约 0.88 秒，未记录回复正文。用户也确认打开 Ollama 后 PAC 本地模型可以聊天。
- 停流/重发：长故事请求开始生成后点停止，UI 立即显示“已停止本轮生成”；随后立即发短句，30 秒内仍显示生成中、没有文本，手动停止。该对话含长请求及未完成上下文，尚不能区分 Ollama 旧生成清理、上下文思考或模型延迟。请求停止期间 UI 未超时；这不能证明供应商/模型进程已经停止计算。
- Ollama 直连接受控取消对照：通过 httpx 取消一个长 `/api/chat` 流（约 2 秒后断开），立即提交新的短请求；后者耗时 46.72 秒才完成。此前同机默认参数的短请求约 2.42 秒，显式 `think:false` 短请求约 0.88 秒。`ollama --version` 为 0.40.15。检查该版本官方 `server/routes.go`，流式生产 goroutine 通过无缓冲 channel 向响应 handler 发送；Ollama 官方 issue #17131 描述 client disconnect 可能使 Chat 流式 handler goroutine/runner semaphore slot 被占用，与观察到的取消后排队延迟相符，但不能证明本机该次请求由这个缺陷导致。见 [v0.40.15 routes.go](https://github.com/ollama/ollama/blob/v0.40.15/server/routes.go) 和 [Ollama issue #17131](https://github.com/ollama/ollama/issues/17131)。
- PAC 停止状态文案已更新：本机选择显示“已停止接收回复；Ollama 可能仍在结束本机生成。”；云端选择显示“已停止接收回复；云端服务是否停止生成未知。”该文案避免把客户端取消误报成上游已停止。Swift `swift test --package-path poc/macos-audio` → 34 项通过；Beta target build 通过；仓库脚本重启后以长请求实际点停止，GUI Accessibility 显示本机提示文案。没有发云请求，云端文案仅由构建代码覆盖，尚未在云 Provider GUI 路径实测。
- 上一轮合成测试结束后，从仓库脚本重新启动 Beta；本轮打开时用户已有本地对话，未关闭或覆盖。下一步是按 Ollama 版本/上游修复状态确定可用运行要求或恢复策略；再完成可本地验证的错误路径与云 API 错误 UI 的授权内验收。新 Ollama 依赖说明已构建，待下次启动后 GUI 确认；B1 暂不关闭。
- 一次桌面自动化重绑定短暂显示“无法找到本机运行环境”，原因是启动了没有 `PAC_POC_PYTHON`/`PAC_POC_BACKEND` 的 app 实例；已将其关闭并用仓库脚本正常重启，现无启动错误。
- B0 最终完成：SwiftUI 主窗口从 `WindowGroup` 改为单实例 `Window`，使最后/唯一窗口关闭即退出，符合单会话 Beta 生命周期；启动错误及 GUI 重试已以本机 fixture 实测，fixture 已删除；真实后端连接后关闭唯一窗口，确认 app/backend 均无进程残留。Swift Beta build 成功，`swift test --package-path poc/macos-audio` 34 passed。
- 上述 keep-alive 实现已在提交 `fa721e1`；本次仅更正实机根因判断与验证记录。继续 B1；B0 已关闭。交接前检查 diff 并提交。

## B0 继续开发（2026-11-09）

- 启动失败后新增“重试连接”按钮，并按 runtime 缺失、进程启动失败、握手超时/无效等情况显示中文恢复提示；重复点击期间禁用按钮。用户仍可从脚本重新启动来修复虚拟环境/仓库配置问题。
- 检查窗口消失时的异步 shutdown 与 supervisor.start 并发：若启动任务尚未完成，原先 shutdown 可能先看到空 process 而返回。现 `LocalBackendSupervisor` 对 start/stop/isRunning 加生命周期锁，串行化进程状态访问。新增真实子进程回归：服务进程在启动握手前延迟时触发 stop，stop 等待启动登记后再关闭，最后确认无存活子进程。
- 验证：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功；`swift test --package-path poc/macos-audio` → 34 passed。一次初始并发测试未通过是因为锁修改未应用，随后修正锁并以进程 marker 确定测试时序，最终回归通过。
- 初次关窗结果显示 WindowGroup 会再次呈现窗口。Apple 文档确认 `WindowGroup` 支持多个窗口且最后窗口关闭后应用继续运行，而 SwiftUI `Window` 是单实例窗口，关闭后应用退出（[Window](https://developer.apple.com/documentation/swiftui/window)、[WindowGroup](https://developer.apple.com/documentation/swiftui/windowgroup)）。Beta 是单用户、单会话且不保存对话，因此主场景改为 `Window("个人 AI 助理测试版", id: "main")`，关闭即退出，避免多个窗口共享一个后端/聊天模型。
- 最终复核：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功；`swift test --package-path poc/macos-audio` → 34 passed。仓库启动脚本启动真实本机服务后，GUI 显示“本机服务已连接”；点唯一窗口的关闭按钮后应用退出；进程检查确认 Beta 和 `pac_poc.local_service` 均无残留。B0 完成。GUI 重试仍用 loopback-only fixture，未发送聊天、访问 Keychain、启动麦克风或连接云 Provider；fixture 已删除。
- 后续进入 B1：本机文字对话与模型设置仍为 IN PROGRESS，下一步核对停流后立即重发、Provider/模型快照与错误路径覆盖，并同步本机验证证据；费用预算硬拦截、Provider 侧停止/计费语义按既有决策保持未实现/未验证。

## 阶段 1 最终复核（2026-11-09）

- 当前 `HEAD` 为 `5f6fe24 feat(stage1): complete stateless engineering foundation`，工作区进入时干净。阶段 1 当前决策允许的无持久化工程底座已完成；数据库/schema/migration/会话持久化/静态加密与 metadata-only 30 天审计仍按 D-003/D-007 未实现并延期，不作为阶段 1 通过项。
- 当前提交验证：`cd backend && uv run --locked --all-extras --all-groups ruff check pac_poc tests` 通过；同环境 `mypy` 无错误；`pytest -q` → 192 passed、1 条既有 Starlette/httpx 弃用警告；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功；`swift test --package-path poc/macos-audio` → 33 passed；`python3 -m compileall -q pac_poc scripts tests`、`uv lock --check` 和 `git ls-files -z | xargs -0 uv run --project backend --locked detect-secrets-hook --baseline .secrets.baseline` 均通过。
- 首次使用 `UV_OFFLINE=1` 跑 Ruff 时因缓存缺少 `onnxruntime==1.31.1` wheel 未启动；改为正常锁定依赖执行后通过。此为环境依赖缓存限制，不是代码失败。
- 阶段 1 收尾后，下一步按 `docs/TASKS.md` 的 B0/B1/B2 队列继续；本次未运行远端 CI。提交本轮文档更正后，交接点为阶段 1 DONE（当前决策范围），阶段 0 完整 V1/正式发布仍有延期证据。

### 阶段 1 更新：Keychain 写入/删除认证 gate

- Beta 模型设置改用 `CredentialManagementService` 保存/删除云 Provider Key；两种修改均要求系统设备认证（Touch ID 或设备密码），取消/失败时不改 Keychain。只读 configured 状态仍不回显密钥。
- 设置页新增“删除已保存的 Key”入口；输入中的密钥在保存成功后清空，写入和删除使用统一进行中状态防止重复点击。
- Swift 单测覆盖 auth gate 的授权前置和拒绝时不落钥匙串；完成本机 Swift build/test 后记录结果。真人 GUI 设备认证路径还需手动冒烟。

### 阶段 1 更新：严格配置类型

- `BetaAPISettings` 现拒绝 bool/字符串/非整数容量、超过 Beta 上限的值、非整秒 PCM 容量、错误模型目录类型和无效超时；`LocalServiceSettings` 对超时也执行数值类型、有限性和正值检查。
- 这避免 Python 将 `True` 隐式当作整数容量/超时，或让小数容量悄然参与协议限制。仅做静态编译与差异检查，未运行测试。

### 阶段 1 收尾：质量门禁与当前范围完成

- 锁定开发工具 `ruff`、`mypy`、`detect-secrets`；CI 新增 Python lint、应用底座类型检查、全仓 tracked file secret-hook 和 `uv lock --check`。
- secret scan 当前 baseline 经审查后为 0 项；测试中的假 Key 使用低熵占位符，Keychain 错误枚举改为 `emptyCredential`，避免被误识别为泄漏。
- Ruff（`pac_poc tests`）、mypy、compileall、`uv lock --check`、secret hook 均通过。最终 Python 全量（D-007 security extra + dev）192 passed，1 条既有 Starlette/httpx deprecation warning；Swift Beta build 成功、33 tests passed。
- 一次与 Swift 构建并行的 Python 测试中，Swift↔FastAPI 子进程测试偶发退出码 1；独立重跑该测试通过，随后串行 Python 全量 192 passed。当前决策范围内阶段 1 无持久化底座标记完成；DB/migration/encryption、持久审计及其他功能按 D-003/D-007 和矩阵触发点延期，未标成通过。

### 阶段 1 更新：统一 HTTP 错误契约

- API 失败响应现统一包含兼容字段 `detail`，以及稳定的 `error.code`、`error.trace_id`；trace ID 同时通过 `X-Trace-ID` 回传，包含认证中间件提前拒绝的请求。
- Pydantic 请求校验失败改为通用消息，不回显错误输入值，避免在 body 含提示词或凭据时将其带回响应。
- 该错误契约切片完成时尚未有明确依赖对象；本轮已补 `BetaAPIDependencies` 工厂入口和最小 liveness health。持久化未实现，且仍按 D-007 暂缓。

### 阶段 1 更新：应用依赖入口与最小 health

- 新增 `BetaAPIDependencies` 和 `create_beta_app()`，把会话、Gateway、凭据、Provider adapter、语音转写器集中为显式注入项；保留 `create_beta_api(...)` 兼容入口，现有启动器与调用点不需要迁移。
- `/health` 仍需本机认证，只返回 `status`、应用版本和进程 uptime；不读取 Keychain/Provider、不检查或创建数据库，也不采集音频。Swift 客户端只解码 `status`，额外字段保持兼容。
- 更新既有 health 断言；本轮仅做静态编译和差异检查，未运行测试。

### 阶段 1 更新：进程启动配置注入

- 将服务入口拆为 `main()` 与可注入的 `run_local_service(settings, app_factory)`；新增不可变 `LocalServiceSettings`，集中控制启动 ready 和优雅关闭 join 超时，非有限或非正值拒绝。
- 默认仍使用 5 秒超时、随机 loopback 端口、短期进程令牌和原 Beta API factory；不读取新增环境变量，不改变网络暴露范围或 Keychain 来源。
- 更新子进程 health 断言以兼容新增版本与 uptime 字段；本轮仅做静态编译与差异检查，未运行测试。

### 阶段 1 更新：集中 API 运行配置

- 新增不可变 `BetaAPISettings`，集中上下文字符上限、PCM 缓冲上限、语音流锁等待时长及语音模型目录；在应用组合依赖中注入，`create_beta_api` 兼容入口也可显式传入。
- 启动时拒绝超出 Beta 既定上下文/30 秒音频上限、不能整秒换算的 PCM 容量、非有限/非正锁等待时间和非绝对模型目录；音频超限提示按配置秒数生成。默认值维持既有协议边界，未新增环境变量或持久化设置。
- 本轮仅做静态编译和差异检查，未运行测试。

- 用户确认：剩余小功能可以后续补齐，当前文档应明确标为未实现；阶段 0 若已结束则开始阶段 1。
- 阶段 0 Beta 范围收尾标记为已结束，并保留原始 §13 的 `PARTIAL/OPEN` 与每项触发条件；不宣称完整 V1/发布 POC 全部通过。
- 阶段 1 按 D-007 从无持久化工程基础开始。数据库、schema/migration、会话保存、静态加密、预算硬拦截、持久审计和文件导入均未实现。
- 首个实现是本机 Loopback API 的 UUID trace ID 生成/校验/回传；有效 UUID 透传，无效或缺失时由服务端生成。Python 全量回归 184 passed，compileall、uv lock --check 和 git diff --check 通过。
- 工作区进入本轮时干净；分支 `main`，领先 `origin/main` 66 个提交。未推送。

### 2026-11-09：完成 Beta 范围阶段 0 收尾评审

- 当前提交回归：Python 183 passed，Swift 33 passed；`uv lock --check`、`python -m compileall`、阶段追踪报告契约测试 9 passed。既有 Starlette/httpx deprecation warning 1 条。
- 当前 Beta GUI 实测：切换到本机 Ollama，开始合成长回复流式生成后点击“停止”，状态显示“已停止本轮生成”，发送按钮/语音按钮恢复；未发送云请求。随后重启 Beta，恢复原先 OpenRouter 选择及原有未发送草稿。
- Beta 范围阶段 0 收尾评审 PASS；原始 §13 全量 POC 仍未验收，矩阵 `PARTIAL/OPEN` 保留。已按能力启用、最低系统声明、持久化、预算承诺、模型/发行物分发等条件逐项记录后续触发点。
- 注意：Beta 当前没有 80 元提醒/100 元云 API 月预算硬拦截；Provider 客户端取消不证明服务端停止生成或计费。不得对用户宣称这些保护已启用。

### 2026-11-09：阶段 0 收尾门槛与时间盒

- 按用户已确认的 C-007，明确区分“Beta 范围阶段 0 收尾评审”和“原始 §13 全量 POC 收尾”。目标在 1–2 个集中工作轮次内完成前者，不再让未启用功能/正式分发证据无限期阻塞 Beta。
- 收尾必须重跑 Python/Swift 回归，复核当前 Beta 的文字/模型切换、本机语音、Consent 安全路径，并给每个剩余 PARTIAL/OPEN 项写明具体触发条件。延期项继续保持 PARTIAL/OPEN，不冒充 PASS。
- 原始全量 POC 中的 macOS 14 实机、Provider 侧停止/费用、模型训练/转换工件权利链和正式发行物许可等外部证据无固定日期，按功能启用或分发前补齐。
- 当前仍未签收 Beta 范围收尾；下一步是跑当前提交 Swift/Python 全量回归并逐条核对矩阵，之后根据实际剩余项修复或明确延期。

### 2026-11-09：补充 Consent 并发请求撤销回归

- 新增同一精确 Consent 下两个并发挂起 generate 的 fake adapter 场景；撤销后两个请求均收到取消。未发起真实 Provider 请求。
- 验证：Consent/Provider/Security 窄回归 50 passed；Python 全量 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 183 passed，1 条既有 Starlette/httpx deprecation warning。
- 阶段 0 仍未验收；真实 Provider 侧取消/费用、审计持久化/UI、macOS 14 runtime、远端 CI 和许可/发行闭环仍开放。

### 2026-11-09：实现 Consent 撤销时的在途请求最佳努力取消

- 按规格书 FR-SEC-003，实现 Consent 撤销时先将精确授权标记为 REVOKED、在锁内拒绝后续注册，然后向该授权登记的 asyncio task 发出线程安全取消；所有 Gateway 请求结束路径解除登记，流式请求 cancellation/finally 会关闭 adapter async iterator。
- 新增 fake adapter 回归：挂起的 generate 被取消；挂起的 stream 被取消且 iterator cleanup 被调用；撤销后的新请求继续在 adapter 前拒绝。未发送真实 Provider 请求。最佳努力取消不能撤回已发送的数据，也不证明 Provider 端停止生成或停止计费。
- 验证：`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_consent_aware_gateway.py tests/test_remote_providers_poc.py tests/test_security_poc.py` → 49 passed；全量 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` → 182 passed，1 条既有 Starlette/httpx deprecation warning。
- POC-05 的在途取消子项已由本机 fake adapter 覆盖；持久审计、Consent UI、实际远端拒绝/取消证据和 Provider 侧费用语义仍开放。阶段 0 未完成。

### 2026-11-09：扩充本机 ASR+LLM 并发性能样本

- 在既有 7 轮的基础上，固定 `bilingual-mandarin-16k.wav` + `qwen3.5:0.8b` 新增 13 轮本机同步屏障 probe；13/13 产生 final、10 partial，模型响应非空且确认 ASR/LLM 实际重叠。
- 新 13 轮结果：ASR wall/重叠 0.244–0.893 秒；运行级帧 P95=15.05–78.43 ms，n=13 的 P95=78.43 ms；单帧最大 25.25–121.72 ms；模型加载 0.609–1.456 秒；Python+Ollama RSS 峰值约 686–855 MB；LLM wall 4.98–45.95 秒。逐轮原始指标见 `docs/poc/phase0-concurrent-asr-llm-samples-2026-11-09.csv`。
- 离线本机运行、无麦克风/云出站、无正文/转写记录且不执行工具。样本仍为同一合成 WAV 的 LLM probe，不代表 Agent 或产品负载；POC-01 性能保持 `PARTIAL`，GPU 和真实负载/阈值未覆盖。
- 验证命令：`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked python scripts/measure_concurrent_asr_llm_poc.py .poc-data/audio/bilingual-mandarin-16k.wav .poc-data/models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 --llm-model qwen3.5:0.8b`，连续运行 13 次，全部 `status=completed`。

### 2026-11-09：阶段 0 性能采样关闭并缩小 Beta 依赖审查范围

- D-013 Beta GUI 采样已完成：启动 20 次/P95=700 ms；partial 216 次/各窗口 P95≤41.5 ms；停止→final 21 次/pooled P95=97.9 ms。相应追踪行标为 `PASS（本机 Beta 样本）`，其范围限制已写入矩阵。
- 验证：`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_phase0_traceability_report.py`（`backend/`）→ 9 passed；`git diff --check` 通过。此次为文档/追踪更新，未改代码。
- 0G 本地核对 `backend/pyproject.toml` 后确认基础 Beta 依赖闭包为 23 个锁定包；本机对应的 22 个 wheel 含 LICENSE 文件，`sherpa-onnx-core` metadata 声明 Apache-2.0。FastEmbed/ONNX Runtime/Pillow 和 SQLAlchemy/Alembic/SQLCipher 属于可选 POC extras。`run_beta_app.sh` 使用共享 `.venv`，因此实际环境可包含额外包；当前没有固定的分发 runtime 或完整 NOTICE 清单。已把范围结论补入 `phase0-model-license-review.md` 和追踪矩阵，0G 许可状态维持未闭环。
- 下一步应继续处理可本机复核的阶段 0 项；任何 Provider 出站仍需该次请求精确 Consent/Policy。训练数据权利链、第三方 Qwen 转换工件/测试音频许可、macOS 14 实机与远端 CI 等不能由本机静态检查代替。

### 2026-11-09：完成 D-013 Beta GUI 性能采样

- 用户补充三次启动面板截图，读数为 678.5、618.4、651.1 ms。结合此前 17 次记录，启动样本共 20 个，范围 500–700 ms，nearest-rank P95=700 ms（≤5 秒）。
- GUI partial 共 216 次更新、22 个窗口（各窗口 n=7/9/10），各窗口 P95 为 32.2–41.5 ms；停止→final 共 21 个样本，pooled P95=97.9 ms、最大 99.9 ms。三项均低于 D-013 门槛；诊断不保存音频或转写。追踪矩阵将此特定 Beta 测量行标为 PASS，不外推至并发负载、其他机器或完整用户感知延迟。
- 已更新 `docs/beta/macOS-beta-voice.md`、`docs/poc/phase0-local-asr.md`、阶段 0 矩阵、任务清单和项目上下文。D-013 采样不再需要用户手动参与。
- 阶段 0 继续未验收。下一个可推进的本地任务是补强 0G 发行许可审计，尤其核对 Python 原生 wheel notices 与实际 beta 打包清单；云 Provider 真实请求仍严格遵守 Consent/Policy，不做无授权探测。

### 2026-11-09：核对本机语音模型文件身份

- 0B/0G 许可与来源审计继续推进。使用本机 `shasum -a 256` 对本机两个 ASR 包比对公开权重文件页：双语 Zipformer 的 encoder/decoder/joiner 三个文件与 `csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20` SHA-256 完全一致；Qwen3-ASR 的 conv frontend/encoder/decoder 三个文件与 `csukuangfj2/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25` 固定 revision `68818b2313fe77bd06f6a7c5068ff3ef59d02b8a` 完全一致。详见 `docs/poc/phase0-model-license-review.md`。
- 这证实本机权重对应的公开模型仓库与具体版本，并不等同于权属审批。双语模型训练数据来源/权利链、Qwen 第三方 ONNX 转换代码/工件许可及测试 WAV 许可仍未闭环；对应追踪矩阵保持 PARTIAL。此轮仅更新文档，无代码测试；`git diff --check` 通过，变更已复核并提交为 `4c30476 docs: verify local ASR model provenance`。
- （后续状态已于本文件最上方更新）当时尚差 3 个启动样本；用户已补充截图，现共 20 个，D-013 GUI 采样关闭。

### 2026-11-09：修复 D-013 启动性能面板单位并核对样本

- 用户提供 16 个启动值：0.5–0.7；两张截图确认面板单位写的是 ms。根因已在 SwiftUI 读数处找到：`startupLatency` 内部保存秒，但显示格式化时没有乘以 1,000；partial/final 的 P95 路径已正确转换。现已改为启动读数乘以 1,000 后显示 ms，因此 17 个现有值（含截图对应的新增一轮）解释为 500–700 ms，nearest-rank P95=700 ms，低于 5 秒目标。
- 截图中的同一诊断运行显示 partial n=7、P95 32.5 ms，停止→final n=1、92.0 ms。汇总为 partial 22 个窗口/216 次更新（最高窗口 P95 41.5 ms），停止→final 21 个值/pooled P95 97.9 ms/最大 99.9 ms，均低于目标。用户确认不需要补截图。
- 原 GUI 采样计划要求 20 次启动；目前 17 次，手动还需 Cmd-Q 后重启并记 3 个启动值即可，不用再做语音采样。追踪矩阵与 Beta 语音记录已更新；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功，`swift test --package-path poc/macos-audio` 33 项通过，`git diff --check` 通过。本次修复已提交，剩余手动步骤为再采集 3 个启动值。
- 阶段 0 仍不能整体标记完成：追踪矩阵尚有远端 CI、macOS 14 实机/安装、Provider 能力/费用/区域与稳定性、Consent 持久审计、模型与发行许可、真实设备驱动异常等独立缺口；按 C-007 逐项保留 PARTIAL/OPEN，继续推进不依赖当前 Beta 的证据工作。
### 2026-11-09：修复实时语音停止时 ASR reset 错误与会话锁泄漏

- 用户确认修复后实时语音已恢复，现将 B2 的重连阻塞解除；该反馈未附性能面板数值。下一项按阶段 0 矩阵推进 D-013 GUI 性能采样。

- 根因已复现：`LocalVoiceTranscriber.end_stream()` 与 `abort_stream()` 调用不存在的 `LocalStreamingASR.reset()`，在真实 ASR stop 路径抛 `AttributeError`。异常清理也调用同一错误方法，WebSocket handler 的 `finally` 因清理再次抛错而未运行锁释放语句，导致第一轮 socket 中断、后续连接一直 busy。
- 修复：结束/取消时改为重置底层 recognizer，并在 `finally` 中清除当前 stream；WebSocket handler 的 finally 再加一层 finally，保证 ASR 清理无论成功失败都释放 asyncio 锁。
- 复现/验证：修复前真实 Uvicorn WebSocket + 仓库本机 ASR 模型 + 固定 PCM WAV 在 end 时返回 1011；独立调用确认 `AttributeError`。修复后 Apple `URLSessionWebSocketTask` 直接连接真实 Uvicorn、使用项目 sherpa-onnx 模型和仓库 PCM WAV，连续 3 轮均收到 partial、final、ended。用户随后确认 GUI 实时语音故障已修复；本次没有提供性能面板样本。
- 本轮新增回归覆盖 LocalVoiceTranscriber 的 end reset、abort 清理与重新开始；Python 全量 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q` → 180 passed，1 条既有 Starlette/httpx 弃用警告。此前反复修改未能解决，是因为测试只用 Starlette TestClient 和假的 transcriber，未执行真实 `LocalVoiceTranscriber.end_stream()`；并且 supervisor 将后端 stderr 丢弃，缺少运行期异常日志。
- 全量 Python 回归已完成：180 passed，1 条既有 Starlette/httpx 弃用警告；`compileall`、`uv lock --check`、`git diff --check` 通过。下一步完成 D-013 GUI 性能采样：20 个启动值、至少 20 个 partial 与至少 20 个停止→final 样本。修复后的快速重录已由用户确认通过。

### 2026-11-09：排查实时语音停止后 socket 断开

- 用户截图显示第一次录音停止时报 `The operation couldn’t be completed. Socket is not connected.`，partial n=2、停止→final n=0；第二次录音被服务端拒绝为 ASR 忙。该证据确认客户端停止时 socket 已断开且服务端会话锁未释放，但尚未揭示最初断连根因。
- 后端 WebSocket 现捕获未预期 ASR 异常，只把异常类型发送给客户端（不含错误正文、音频或转写），随后关闭连接；既有 `finally` 会 abort ASR 流并释放锁。新增异常事件与锁释放回归；保留 abort 后立即重连回归。
- 验证：语音窄回归 18 项通过；`backend/` 下 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q` → 179 passed，1 条既有 Starlette/httpx 弃用警告。Swift 33 项在本轮前已通过；本轮未改 Swift。
- 下一步：用户 Cmd-Q 退出旧 app，运行 `PAC_BETA_PERF_DIAGNOSTICS=1 ./poc/macos-audio/scripts/run_beta_app.sh` 重建并启动；验证语音→停止并识别后 final 入草稿，再立即第二次录音并停止。若失败，回报状态栏完整错误文字和诊断样本数；不要继续性能采样直到重复录音链路恢复。

### 2026-11-09：接入 B2 本机语音首个切片

- 用户反馈千问已可正常聊天；本仓库没有该次成功响应或 usage 证据。按测试版队列开始 B2。
- 新增 Swift `LocalMicrophoneCapture`：只在按钮调用时请求系统麦克风权限，AVAudioEngine 转为 16 kHz 单声道 PCM16LE，最多保留 30 秒；取消/关窗丢弃，停止后经认证 loopback `POST /voice/transcribe` 发给本机 sherpa-onnx 双语 Streaming Zipformer。识别文本只进入草稿，用户还需单独按发送；无自动云 ASR。assistant 完整回复提供手动本机朗读和停止按钮。Beta Info.plist 增加麦克风用途说明。
- 新增 `backend/pac_poc/voice_transcription.py` 和本机 endpoint；请求体强制 octet-stream、PCM16LE、≤960,000 bytes，模型 lazy-load，原音频不写盘/日志。缺模型或 ASR 错误会显式失败，不切换云端。
- 验证：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功；`backend/` 下 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc` 成功；`scripts/run_beta_app.sh` 构建启动成功；读回 Info.plist 权限文案；GUI Accessibility 树确认“语音输入”按钮可见。没有点击录音按钮，未请求麦克风权限/采集/朗读，未运行测试。
- 新增 `docs/beta/macOS-beta-voice.md`，更新 `PROJECT_CONTEXT.md`、`TASKS.md` 和 B1 聊天报告。当前 app 模型选择为 OpenRouter（Global）；转写仅在草稿，任何发送前需用户检查并选择目标。
- 下一步需用户在应用点击“语音输入”，按系统提示授权并说一条不含敏感信息的短句；停止后确认草稿转写，再手动朗读 assistant 回复。真实录音质量、停止/取消与 TTS 尚未验证。双语模型来源/训练数据权利链仍待核，当前仅单机 Beta 使用。

### 2026-11-09：千问 Beta 合成请求失败待诊断

- 用户确认新千问 API Key 已在测试版保存。模型设置页显示 `已保存（qwen-app）`，GUI 当前选择千问应用 API、中国区、`qwen3.8-flash`。
- 按交接承诺发送一次固定合成提示 `Reply exactly: PAC-QWEN-SMOKE-20261109`。界面进入云生成后返回“云端凭据不可用或请求失败；已停止发送，不会自动切换 Provider。”错误处理当前会折叠 Keychain 读取失败/传输异常等情况；无回复、Provider 接收证明、usage 或 cost，因此不能判断请求是否到达千问或是否计费。没有重试，避免重复调用。
- `backend/pac_poc/beta_api.py` 已改为区分 Keychain 不可用、HTTPX 传输错误、明确 HTTP 状态及无法识别响应，并保持不显示密钥/上游正文；Python `compileall` 通过，未运行测试，未重试云请求。随后退出旧应用进程并用启动脚本重启，GUI 再次显示本机服务已连接。报告已更新 `docs/beta/macOS-beta-chat.md` 和 `docs/TASKS.md`。
- 下一步：用户先查看千问控制台是否记录本次合成请求/用量；确认后再决定是否以新版错误提示重试。之后补相应回归覆盖。窗口关闭清理和停止行为仍待 GUI 冒烟。

### 2026-11-09：复核千问 Key 状态并推进 B0/B1 手动冒烟

- 用户确认千问应用 API Key 已轮换，暴露的旧 Key 已删除。运行 `poc/macos-audio/scripts/run_beta_app.sh` 后 SwiftUI 页面显示本机服务已连接，当前模型仍为千问 `qwen3.8-flash`；设置页通过 Keychain 状态接口显示 `qwen-app` “未配置”。没有输入、读取 Key 内容或保存 Key，也没有发起真实云请求。
- B0 复核：启动脚本构建成功；一次 GUI 检查遇到本机服务启动失败提示，干净重启后连接成功；Cmd-Q 后 `ps` 检查未见测试版 app 或 `pac_poc.local_service` 残留。因本轮没有单独验证关闭窗口的生命周期，不关闭 B0。
- 直接启动固定后端模块的握手诊断成功，输出中省略 token，并通过关闭 stdin 收到退出码 0。真实千问调用仍取决于用户先在设置页保存新 `sk-ws-` Key；保存凭据必须由用户亲自在应用内完成。
- 更新 `docs/TASKS.md`、`docs/beta/macOS-beta-chat.md`。下一步：用户在测试版“模型设置”中输入并保存新千问应用 API Key（本机 Keychain）；随后再逐次授权并执行合成云请求。B0 窗口关闭清理、B1 停止行为仍需 GUI 冒烟。用户已确认旧暴露 Key 删除，解除此前遗留的撤销状态疑问。

### 2026-11-09：收紧 Consent 操作与来源范围

- Consent grant 增加必填的 `action_scopes` 与 `source_scopes`，并记录 ACTIVE/REVOKED 生命周期；撤销后保留 REVOKED 状态。Gateway 按实际调用入口派生 generate、stream 或 tool-proposal 操作，远端请求缺来源或操作不匹配时在 Adapter 调用前拒绝。Beta GUI 的云请求授权限定到 `beta-gui-chat` 来源及 stream 操作；Provider POC 探测调用已提供明确来源和对应动作授权。
- 报告与追踪矩阵已更新：授权精确匹配现覆盖 Provider、模型、区域、用途、数据级别、操作和来源；产品级审计持久化、Consent UI、在途请求撤销语义与真实出站门禁证据仍未完成，不提升阶段状态。
- 验证：`backend/` 下窄回归 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_consent_aware_gateway.py tests/test_remote_providers_poc.py tests/test_security_poc.py` → 47 passed；全量 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q` → 170 passed；`git diff --check` 通过。
- 本轮未读取 Keychain、未发起网络/云请求、未采集麦克风音频。B0/B1 的 GUI 设置与退出清理手动冒烟仍待用户操作；旧的聊天暴露 `sk-ws-` key 是否已撤销也无闭环记录，需在千问控制台确认。阶段 0 后续从 B0/B1 手动闭环继续。

### 2026-11-09：校正文档与仓库实际状态的不一致

- 只读复核发现三处权威文档陈述已过期：①全量 Python 回归实际为 **162 项通过**，而 `PROJECT_CONTEXT.md` 与追踪矩阵仍记 154 项；②仓库**已推送**且 `main` 与 `origin/main` 同为 `51b9ab9`、无未推送提交，文档仍写"未推送"；③GitHub Actions `Phase 0 checks` **已在 `main` 真实成功运行两次**（run `42489738004` 对应 `51b9ab9`，日志 `162 passed`、Swift `31 tests passed`；另 run `42475879541` 成功），文档仍写"尚未执行/真实 CI 状态仍未验证"。`docs/beta/macOS-beta-chat.md` 验证记录内还并存 158 与 162 两个数字。
- 已更正 `PROJECT_CONTEXT.md`、`docs/poc/phase0-traceability.md`（工程基线/CI 行）、`docs/TASKS.md`（把 GitHub Actions 实际运行移出延期清单）、`README.md`（CI 段补充已真实运行；关窗停止后端的表述改为与 `onDisappear` → `supervisor.stop()` 实现一致并保留"残留进程待实机冒烟"）、`docs/beta/macOS-beta-chat.md`（标注 158 为该轮记录）。
- 本文件内 2026-11-08 各条历史交接（含 154/158、"未执行推送或远端 CI"）在当时是准确的，按日志性质保留原文，不作追溯改写。
- 追踪矩阵工程基线/CI 行仍保持 `PARTIAL`：push 触发的 CI 已验证，但 PR 触发路径尚未经历；是否改判 `PASS` 属阶段验收决定，未由实现者自行变更。
- 本次实测命令：`backend/` 下 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q` → 162 passed；`swift test --package-path poc/macos-audio` → 31 项通过；`uv lock --check`、`compileall` 通过；`uv.lock` SHA-256 仍为 `b201746b…`，SBOM 证据锚点未失效。本轮只读复核与文档更正，未改动任何代码、未发起云请求、未采集音频、未读取 Keychain。
- 顺带记录一项仍未闭环的安全事项：`docs/poc/phase0-remote-provider.md` 提到用户曾在聊天中贴出一把 `sk-ws-` 临时 key，建议"在控制台撤销"，但后续记录只确认了新 key 已存入 Keychain，**旧 key 是否已撤销至今无闭环记录**，应按已泄露处理并由用户在控制台确认。

### 2026-11-08：移除逐消息云端确认弹窗并澄清 Token Plan 边界

- 用户明确反馈选择了云模型后每条消息再弹窗影响体验。聊天发送不再显示确认 sheet；模型设置解释选中云端 Provider 即持续授权后续消息直接发送，切回本地即可停止云出站。后端仍按具体 Provider/model/region/data level 建立单请求 Policy grant，保留 L3 凭据拦截、Keychain、固定目标和禁用 fallback。
- 用户再次要求把千问 Token Plan 加入大模型选项。复核千问官方个人版当前条款：`sk-sp-` 仅可在官方支持的编程/智能体工具扩展机制中交互使用，明确禁止自定义应用后端。因此不把 Token Plan Key 直连本应用 Provider；应用内千问仍提供 `sk-ws-` 按量 API。若以后取得适用于自建应用的官方许可，或改为官方支持的工具扩展集成，再评估加入。
- 官方资料：[Token Plan 个人版使用范围](https://platform.qianwenai.com/docs/token-plan/personal/token-plan-personal-overview)、[千问 API Key 类型](https://platform.qianwenai.com/docs/api-reference/preparation/api-key)。
- 验证：`swift test --package-path poc/macos-audio` 31 项通过；`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功；`git diff --check` 通过。新版 app 已重启，GUI Accessibility 树显示云模式将直接把聊天内容发送给所选服务商；没有发送聊天消息，因此没有产生云请求，也没有读取 Keychain。

### 2026-11-08：将千问应用 API 加入模型设置选项

- 云端服务商列表新增并默认选择千问 `qwen3.8-flash` 应用 API，固定普通 OpenAI 兼容端点 `https://maas.qianwenaiapi.com/compatible-mode/v1`、中国区域、Keychain account `qwen-app`。
- 该路由使用千问按量计费应用 API 的新 `sk-ws-` Key；Keychain adapter 会拒绝 `sk-sp-` Token Plan 个人版 Key，保存 UI 也校验 key 前缀。提醒用户不要复用先前在聊天中公开过的旧 Key。Token Plan 个人版不用于本自建应用。
- 保留 DeepSeek/OpenRouter 配置。所有云请求继续逐次展示完整对话并确认；无 Consent、L3 凭据命中均在 Keychain 读取/网络出站前拒绝，无自动 failover。
- 官方确认依据：[OpenAI 兼容接口](https://platform.qianwenai.com/docs/api-reference/toolkitframework/openai-compatible/overview)、[API Key 类型](https://platform.qianwenai.com/docs/api-reference/preparation/api-key)、[Token Plan 个人版范围](https://platform.qianwenai.com/docs/token-plan/personal/token-plan-personal-overview)。项目配置和运行条件见 `docs/beta/qwen-token-plan-integration.md` 与 `docs/beta/macOS-beta-chat.md`。
- 验证：千问相关后端窄回归 26 项通过；Python 全量回归 162 项通过；`swift test --package-path poc/macos-audio` 31 项通过；Beta `.app` 构建成功；Accessibility 树确认运行中的 GUI 状态为 `qwen3.8-flash` 且“模型设置”按钮可见；启动脚本语法和 `git diff --check` 通过。未读取 Keychain 中的 Qwen key、未打开设置 sheet 手动操作、未发送云请求。
- 下一步：用户在设置中保存新建的千问按量计费 `sk-ws-` 应用 Key 后，可逐次确认合成请求以实测认证和流式；设置入口已加入。不得复用曾贴入聊天的旧 Key。

### 2026-11-08：增加本地/云端模型设置 GUI

- SwiftUI 聊天页新增“模型设置”齿轮按钮；默认本地 Ollama，可编辑本地模型 ID。云端暂提供固定 DeepSeek `deepseek-flash` / 中国与 OpenRouter `deepseek/deepseek-v4.1-flash-1017` / Global。
- 设置面板可将云 API Key 保存到 login Keychain 的既有 service/account；界面只显示是否已保存。每次云发送前弹窗展示完整对话、Provider、模型和区域；用户逐次确认后才创建一次精确 Consent。Keychain 缺失、401、402 有脱敏提示，不自动 failover。检测到常见 `sk-`、Bearer 或私钥标记时在读取 Keychain 和网络出站前拒绝。
- 千问 Token Plan 个人版 Key 不列为应用 Provider：服务端虽支持文本和实时语音，个人版范围限定于编程/智能体工具交互，不适用于本自建应用。需取得适用于自定义应用的凭据后再加入千问。
- 本地来源和模型 ID 保存在 UserDefaults；启动脚本不再硬编码要求 `qwen3.5:0.8b`，所选模型需已在 Ollama 安装。具体设置说明见 `docs/beta/macOS-beta-chat.md`。
- 验证：Python 全量 `pytest -q` 159 passed；Swift `swift test --package-path poc/macos-audio` 31 passed；应用 target build 通过；Accessibility 树确认设置按钮显示；`git diff --check` 通过。设置 sheet 手动操作和真实云端请求尚未验证，未发送云请求。
- 下一步：手动打开设置 sheet 复核控件与 Keychain 状态；随后完成 B0/B1 停止与关窗清理实机复核，再推进 B2 本机语音。

### 2026-11-08：修复本机对话停止后的请求状态竞态并核对千问实时语音范围

- SwiftUI 本机聊天给每轮生成分配 request ID；取消后清除当前 ID，流片段和结束/错误回调仅在 ID 仍匹配时更新 UI，避免旧请求收尾清掉新请求状态。
- 验证：`swift test --package-path poc/macos-audio` 构建成功，31 项 Swift 测试通过；该请求竞态尚无专门单元测试，GUI 停止与立即重发仍需手动冒烟。
- 核对千问官方当前 Token Plan 个人版条款：服务端支持 Realtime WebSocket，但个人版 Key 仅供编程/智能体工具内交互，排除自定义应用后端。本项目自建 Beta 不接该 Key；如要应用内云语音，需适用自定义应用的凭据或官方允许的 Agent 扩展方式。已更新 `docs/beta/qwen-token-plan-integration.md`、DECISIONS、TASKS 和 PROJECT_CONTEXT。当前没有发起云请求或采集音频。
- 下一步：按 Beta 队列完成 B0 关窗服务清理、B1 停止/立即重发 GUI 复核，再进入 B2 本机语音应用闭环；不要把 Token Plan 个人版 Key 接到自建应用。

### 2026-11-08：补齐千问 Token Plan 实时语音接入说明

- 用户指出 Token Plan 也支持实时语音。已核对官方 Token Plan 实时语音页和 Realtime API 支持矩阵：`qwen-audio-3.0-realtime-plus` 支持 Token Plan，通过独立 WebSocket 地址；不是 OpenAI Chat Completions，也不是现有本地 ASR/TTS 链路。
- 新增 `docs/beta/qwen-token-plan-integration.md`，记录文本/实时语音/非实时 ASR/TTS 的独立地址和协议、Keychain 约束、PCM/事件流程、Consent、实现状态与逐项验收。同步更新 DECISIONS、TASKS、PROJECT_CONTEXT、Provider 报告、追踪矩阵和 README 索引。
- 目前只是文档和产品排程更新；Beta 应用尚未接入 Qwen 实时语音，未启用麦克风或发起新云请求。

### 2026-11-08：千问 Token Plan Base URL 纠正

- 用户提供官方截图，指出 Token Plan 的 OpenAI 兼容 Base URL 为 `https://token-plan.maas.qianwenaiapi.com/compatible-mode/v1`。此前 adapter 仍用旧北京 `maas.aliyuncs.com` 域名，现已切换到截图/千问AI平台文档中的品牌域名，固定模型和 `sk-sp-` Keychain 检查不变。
- 澄清使用范围：协议兼容确实允许在支持的 AI/Agent 工具中接入，官方明确列出 OpenClaw；Token Plan 个人版范围也明确排除自动化脚本和自定义应用后端。我们当前自建 FastAPI beta 属自定义应用后端，所以 Base URL 改正不自动意味着可将该 Key 放入 beta 后端。官方链接见 `DECISIONS.md` 与 Provider 报告。
- 历史 Qwen 真实请求曾通过旧区域域名成功；尚未对新品牌域名另行出站。

### 2026-11-08：测试版本机服务会话时长修正

- 发现复用 POC 默认会令本机 API token 五分钟后过期，长时间打开测试版会导致聊天 401。Beta 服务改为 token 仅在 supervisor 管理的进程存活期间有效；随机 token 不落盘，owner pipe 关闭即停止服务并销毁 token。POC 其他调用继续保留短时过期默认值。
- `tests/test_beta_api.py`、`test_local_service_process_poc.py`、`test_security_poc.py`：11 项通过；`git diff --check` 通过。
- 后续仍需 GUI 停止按钮和关窗服务清理验证。

### 2026-11-08：B0/B1 测试版本机文字对话首个垂直切片

- 新增 macOS SwiftUI app target 与 `scripts/build_beta_app.sh` / `scripts/run_beta_app.sh`。应用通过固定 supervisor 启动本机服务，窗口显示连接状态；当前模型为本机 Ollama `qwen3.5:0.8b`。
- 后端新增受 Bearer token/loopback 保护的 `/chat/stream`，消息尺寸、条数和字段均有边界；SwiftUI 输入/流式展示/停止功能接线完成。会话仅保存在进程内存，关窗不保存。
- 验证：Swift build 通过；Swift 31 项通过；后端窄回归 11 项、全量 Python 158 项通过；compileall 通过。启动真实 app 后显示模型已连接；另以本机真实 Ollama 对合成短句发起 API 冒烟，HTTP 200、7 个非空增量，未记录正文，服务正常停止。
- 报告见 `docs/beta/macOS-beta-chat.md`。GUI 实际发消息并显示模型回复已观察通过；未完成：停止按钮、关窗后服务清理确认；后续接 B2 本地语音。云模型、持久化与未来功能不挡当前文字闭环。

### 2026-11-08：测试版优先范围调整（C-007）

- 用户明确：前期只在 macOS 单用户使用，先交付能用的测试版；未来功能先留扩展点，待实际开发该功能时再验证。
- 记录 C-007：阶段 0 未闭环事项不再整体阻塞测试版，但不得将延期项标成已验证。安全底线（本机优先、远端逐次 Consent、Keychain、默认拒绝）继续生效。
- 测试版按 B0 应用骨架、B1 本机文字对话、B2 本地语音闭环推进；会话持久化等因加密/保留决策延期，云模型需合规后端凭据，Token Plan 不接产品后端。
- 下一步从现有 supervisor/loopback POC 建可运行应用入口，再实现文字对话 API 和 UI。阶段 0 追踪矩阵保留原始证据/缺口，改为完整 V1/正式发布追踪。

### 2026-11-08：Qwen Token Plan 真实文本探测

- 用户在 `backend/` 运行 `scripts/probe_remote_provider_poc.py qwen` 并输入本次确认短语。一次真实非流式 L1 合成文本请求成功，响应精确匹配 `phase0-probe-ack`；模型 `qwen3.8-flash`，usage prompt/completion/total=73/50/123。服务未返回下游 Provider、实际区域或费用。
- 证据仅覆盖一次文本请求；stream/tools/JSON/error/cancel/重复稳定性以及千问语音接口仍未实测。Token Plan 仅交互式 POC，不得接入产品后端。
- 此前停在 Consent 提示的本机 CLI session 已消失（工具报告 Unknown process id）；该 session 未发送请求。
- 已更新 Provider 报告、追踪矩阵、任务和项目上下文；阶段 0 仍未验收。

### 2026-11-08：千问 Token Plan 默认测试路径

- 用户指定后续云模型默认优先千问 Token Plan；D-011 阶段 0 候选方向定为千问/北京，但 D-010 的 V1 Provider 最终组合仍延期。文本默认测试型号暂取截图所列 `qwen3.8-flash`。
- 新增固定北京 chat-completions adapter、Keychain `qwen` 账户 allowlist、单次 Consent 探测与 capability/deny-check 入口。前缀不是 `sk-sp-` 时在发 HTTP 前拒绝；MockTransport 已覆盖正确端点/模型/keychain 路径和按量付费 key 的拒绝。
- 用户贴出的临时 key 没有被使用或保存；它以 `sk-ws-` 开头，而 Token Plan 官方说明套餐专属 key 为 `sk-sp-`，`sk-ws-` 属于按量付费 API Key 类型。需在控制台撤销这把暴露的 key，另建 `sk-sp-` 并只存 Keychain（service `com.personal-ai-assistant.phase0.provider`、account `qwen`）。
- Token Plan 语音接口并非 chat-compatible：非实时 ASR `qwen-audio-3.0-asr-flash`、TTS `qwen-audio-3.0-tts-plus`、实时语音对话 `qwen-audio-3.0-realtime-plus` 需各自协议适配。文本 adapter 已有 mock，但没有真实出站；任何真实请求还需单项精确确认。
- 窄验证：`pytest -q tests/test_remote_providers_poc.py tests/test_phase0_traceability_report.py`，29 passed。阶段 0 仍未验收；更新 DECISIONS、TASKS、PROJECT_CONTEXT、Provider POC 报告和追踪矩阵。
- （本段结论已由文首“千问 Token Plan Base URL 纠正”更新）当时因只查到旧版阿里云文档，记录为不能用于后端；现按千问AI平台当前文档保留具体边界：OpenClaw 等交互式 Agent 工具允许接入，自定义应用后端不在支持范围。
- 用户已选择“交互式 POC（sk-sp-）”；目前真实探测前置仍是撤销已暴露 key、创建新的 Token Plan 专属 key 并保存到 login Keychain 的 service `com.personal-ai-assistant.phase0.provider` / account `qwen`。key 不应回传聊天。真实请求须在 CLI 显示 payload 后单独输入 `ALLOW QWEN`；本轮没有发出云请求。

### 2026-11-08：0B 第二组合成负载并发资源复测

- 用本机 `bilingual-mandarin-16k.wav`、官方双语 Streaming Zipformer 与 Ollama `qwen3.5:0.8b` 运行三轮同步屏障观察；每轮 28 帧、10 partial/1 final，模型返回非空，ASR 与 LLM 确认重叠 0.243–0.254 秒。
- ASR wall 0.243–0.254 秒，帧 P50 11.45–14.08 ms、P95 15.86–16.47 ms、max 19.89–28.55 ms；LLM wall 14.05–38.97 秒。1 秒采样下 Python+Ollama 峰值 RSS 671,645,696–775,536,640 bytes，CPU 时间差 1.27–21.65 秒。未记录正文，GPU 未测；样本为合成音频，不构成独立语料或产品性能验收。
- 报告、PROJECT_CONTEXT、TASKS 和追踪矩阵已同步更新。阶段 0 仍未验收；后续仍需独立语料、长时/不同负载指标、设备故障补证及用户延期/不可得项处理。

### 2026-11-08：0G Python arm64 wheel 原生依赖审计

- 检查 `.venv` 反向依赖树、当前已安装 wheel 和 Mach-O `otool -L`。`fastembed` 引入 ONNX Runtime 与 Pillow；运行环境另含 sherpa-onnx、sounddevice/PortAudio、SQLCipher 原生扩展。
- Pillow wheel 自带 CycloneDX 组件 SBOM，19 个组件中包括 LGPL-2.1-or-later FriBidi、GPL-3.0-or-later libimagequant、FTL FreeType 等；SQLCipher 扩展静态链接的运行时报告 `4.12.0 community`，需遵守 Zetetic attribution；PortAudio 与 sherpa wheel 内嵌 ONNX Runtime 也各有独立许可/notice 对象。详细对象和来源写入 `phase0-model-license-review.md`。
- 该项明确了 54 包锁文件 SBOM 不足以代表原生发行通知闭包。用户选择暂不配置/操作 Git 远端；复核时发现工作树已有 `origin`，未执行推送或远端 CI。ModelScope 工件许可资料当前不可得（用户暂时拿不到）。阶段 0 仍未验收。

### 2026-11-08：0H APFS 满卷备份复制恢复

- 扩展 `run_sqlcipher_enospc_poc.py`，在仓库 `.poc-data` 下的 128 MiB APFS 临时映像中先留存旧加密备份，再扩展源库并填满目标卷，真实执行新备份直到 SQLCipher 返回 `database or disk is full`。释放填充文件后，源库的基线与 12 条新记录可检索，旧备份可用旧密钥检索；两边 `integrity_check=ok`，失败 staging 已清理。
- SQLCipher binding 未提供 `sqlite_errorcode`，仅有标准错误文本；`is_disk_full_error` 现识别 SQLCipher exception 的精确 SQLite 满盘文本，并有回归覆盖。
- 窄恢复回归 `pytest -q tests/test_sqlcipher_enospc_poc.py tests/test_sqlcipher_compat_poc.py`：29 项通过；全量 Python 回归 154 项通过、compileall 和 `uv lock --check` 通过；Swift 31 项通过；追踪文档测试 9 项通过，`git diff --check` 通过。
- 更新 `phase0-failure-recovery.md`、`phase0-enospc-recovery.md`、`TASKS.md` 和追踪矩阵。系统卷/外接介质、断电/文件系统故障、WAL 产品策略仍未覆盖。

### 2026-11-08：阶段 0 本机全量回归复核

- 在 `backend/` 运行 `UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q`、`uv run --locked python -m compileall -q pac_poc scripts tests` 与 `uv lock --check`：Python 154 项通过，compileall 与锁文件检查通过。
- 在 `poc/macos-audio/` 运行 `swift test`：31 项通过。`git diff --check` 通过。
- 将上下文、任务清单和追踪矩阵的旧 Python 151/Swift 29 结果更新为当前结果。GitHub Actions 实际运行仍受仓库未配置 remote 阻塞。

### 2026-11-08：0B/0G Qwen3-ASR 许可来源交叉核对

- 官方 `Qwen/Qwen3-ASR-0.6B-hf` 模型页和 `QwenLM/Qwen3-ASR` LICENSE 均给出 Apache-2.0 许可线索；该许可不能直接推定覆盖第三方 ONNX 导出仓库、ModelScope 工件或随包音频。
- `Wasser1462/Qwen3-ASR-onnx` 当前公开目录没有可见 LICENSE；ModelScope 文件页本轮不可访问，无法核实实际下载 revision/工件条款。随包 WAV README 指向 Qwen 博客，但未给出音频再分发许可。报告已分别记为官方上游许可已知、第三方产物/音频许可未闭环。
- 更新 `phase0-model-license-review.md`、`TASKS.md` 和阶段追踪矩阵。阶段 0 仍未验收；下一步继续核对实际 Swift/macOS 发行物及原生依赖，并保留真实标注语料、D-014 与模型权利链缺口。
- 公开来源：[Qwen 模型页](https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf)、[Qwen 官方 LICENSE](https://github.com/QwenLM/Qwen3-ASR/blob/main/LICENSE)、[转换仓库](https://github.com/Wasser1462/Qwen3-ASR-onnx)、[ModelScope 文件页](https://modelscope.cn/models/zengshuishui/Qwen3-ASR-onnx/files)、[Qwen 样例页](https://qwen.ai/blog?id=qwen3asr)。

### 2026-11-08：0G 当前 macOS POC 依赖边界审查

- `poc/macos-audio/Package.swift` 未声明 SwiftPM 外部 package，未发现 `Package.resolved`；Swift 源码只导入 Apple SDK 模块。当前 lifecycle demo 从仓库外部 venv 路径 `backend/.venv/bin/python` 启动后端，并未定义独立 Python 安装器/随包策略。
- 依赖边界已补入 `phase0-model-license-review.md`、`TASKS.md` 和追踪矩阵。此项只说明当前 POC；正式发布的 Python wheel/native 依赖、模型和通知文件仍需根据最终安装包另审。

### 2026-11-08：0G Python 依赖许可证线索复核

- 核实 `tokenizers==0.23.3` 的本机 Trove classifier 与固定版本 PyPI 页均声明 Apache，发布对应的上游 tag 有 LICENSE 文件。更新 SBOM 报告以明确 metadata 分类来源。
- 此处为历史记录：54/54 锁定包当时各有初步来源线索。最新为 55 个非根包，含 `websockets==17.4` 的精确 PyPI BSD-3-Clause 线索；许可证适用范围、通知义务、原生依赖与最终打包闭包仍未审查，不是法律批准。

### 2026-11-08：0B 模拟设备故障注入

- 新增 PortAudio stream open failure 与 callback status error 注入；打开失败被清楚报告并丢弃 PCM 缓冲，callback 状态错误会停止采集、退出 stream context 并清空缓冲。decoder 异常/用户 Ctrl-C 路径继续通过原有测试。
- `tests/test_microphone_buffer.py` 11 项通过；完整 Python 回归 153 项通过。均为 mock 故障，不替代真实麦克风驱动故障测试。阶段 0 仍未验收。

### 2026-11-08：0E 真实系统认证再次成功

- 真实 demo 窗口新状态显示“认证未完成或被系统拒绝”；累计认证成功两次、未认证一次。该按钮路径不访问钥匙串。
- 当前 UI 把用户取消与系统拒绝合并显示，因此不能单靠界面状态确定具体错误原因；按未认证/fail-closed 证据记录。其余未决：异常自动恢复/退避、锁屏/休眠和正式分发。

### 2026-11-08：0E 认证取消区分与实机复测

- 认证测试视图模型按 `LAError.userCancel`、`LAError.systemCancel` 分别显示“用户取消”和“系统中断”；其他错误继续显示未认证状态。新增对应 fake 回归。
- 重建并重开 `.poc-data/backend-lifecycle-poc.app` 后，真实弹窗取消一次，界面准确显示“用户取消了系统认证；未访问钥匙串”。此前真实认证成功两次；本机 Swift 全量回归 31 项通过。
- 异常自动恢复/退避、锁屏/休眠和正式分发仍未验证。阶段 0 未验收。

### 2026-11-08：阶段 0 队列状态校准

- `TASKS.md` 的 0I 项已标记 ASR-final→本机 TTS 合成链路报告完成（5 条样本、7/7 播放成功）；保留独立真人语料/多负载资源、真实 Provider 服务端取消、许可闭包、恢复边界和真实 CI 等缺口。
- 阶段 0 仍未验收，阶段 1 未开始。

### 2026-11-08：0D MemoryStore Embedding 检索集扩展

- 将 disposable MemoryStore 的固定合成评估由 3 条记忆/查询扩为 4 条，新增 Swift 编程语言记忆与 macOS 开发语言 query；不使用私人数据。
- 固定候选权重离线合成检索 4/4 top-1；严格离线输出 `memory_count=4`、`query_count=4`、`top1_matches=4`、来源证据完整，没有输出 query/记忆原文。仍是小型合成集，产品 schema 和默认模型选择保持不变。详见 `poc/phase0-memory-embedding.md`。

### 2026-11-08：0B ASR/TTS 验收缺口复核

- 对照规格书 §13 并新增 manifest 样本 ASR-final → AVSpeechSynthesizer 冒烟脚本；5 条中英/混说系统合成 WAV 共 7/7 得到 final 并正常完成播放，未落盘 transcript。已有独立 AVSpeechSynthesizer 立即打断实测。
- 此证据满足本机候选链路的基本连通性；独立语料、长时/多负载资源稳定性、真实驱动异常和产品性能目标仍未覆盖。`TASKS.md` 已去掉过时的“选择中文或双语模型”建议；当前模型许可只记录公开声明，权利链及转换包许可仍需核验，不隐含产品选型。
- 阶段 0 仍未验收；下一步优先继续 0B 独立真人语料/资源补证或推进其他无外部授权依赖的工作包，不启动麦克风或云请求。

### 2026-11-08：0B/0G 双语 ASR 许可线索复核

- 第一方资料核对发现，归档模型包 README 声明 Apache-2.0 并指向 `pfluo/k2fsa-zipformer-chinese-english-mixed`；sherpa-onnx 官方索引将转换来源列为 `csukuangfj/k2fsa-zipformer-chinese-english-mixed`。两个 Hugging Face 模型页都声明 Apache-2.0，但官方索引只称其使用内部训练数据，权利链未给出可核验细节。
- 修正 ASR 报告中上游归属，新增运行时、sounddevice 与 PortAudio 分层许可线索。结论限于仓库/包维护者声明；不视作训练数据权利审计或正式分发批准。详见 `poc/phase0-model-license-review.md`。
- 用户无需配合；模型仍仅作本机 POC，不据此决定产品打包。

### 2026-11-08：0B 本机 ASR 与 LLM 并发重复测量

- 同一条 6.94 秒合成 WAV + `qwen3.5:0.8b` 新跑三轮，均重叠、35 帧、15 partial/1 final。重叠 0.420–0.553 秒，P50 16.65–20.82 ms、P95 19.55–30.17 ms、峰值帧耗时 35.41–36.90 ms；本机 ASR 与 Ollama 进程 RSS 采样峰值 585,367,552–1,126,219,776 bytes。加上已有一轮，共四轮同样本观察。
- GPU 未测；RSS/CPU 采用 1 秒进程采样，CPU 估算窗口不同且波动，不作横向结论；重复同一音频不是独立语料或产品性能验收。具体范围见 `poc/phase0-local-asr.md`。
- 全量 Python 回归 151 passed；详见报告。

### 2026-11-08：0H 备份 ENOSPC 失败路径

- 在 `backup_to` 复制边界确定性注入 `OSError(ENOSPC)`；安全错误保留可识别 cause，旧备份可用旧密钥检索且完整，源库保持完整，`.partial` 清理。
- 与实际 HFS+/APFS 有界映像写满测试区分：物理目标卷满载下的备份失败尚未实测。该项尝试发现满卷后备份有时仍完成，且 APFS 满载时重开数据库需要可用空间；未将不稳定结果记作通过。
- 窄回归：`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security --group dev pytest -q tests/test_sqlcipher_enospc_poc.py tests/test_sqlcipher_compat_poc.py`，28 passed。

### 2026-11-08：0I 规格阶段归属复核

- 对照规格书 §13–§14 修正 0B 门禁描述：SwiftUI 麦克风、AEC 与锁屏/休眠语音闭环属于阶段 3，不再误列为阶段 0 的 0B 阻塞项。阶段 0 当前继续核对 ASR/TTS 稳定链路报告、资源证据及总体追踪矩阵。
- 真实设备驱动异常仍未专门注入，作为稳健性补证；云 ASR/TTS 候选受 D-011 延期约束，未擅自选择 Provider/区域。阶段 0 未验收，阶段 1 未开始。

### 2026-11-08：0E GUI 后端多轮启停复测

- 在本机 demo 窗口完成两轮停止→启动→健康检查，UI 每轮均先回到“尚未检查”，再显示“本机服务已连接”；进程表最后只有一个 `pac_poc.local_service` 子进程。
- 真实系统认证成功证据已记录，认证测试不会访问钥匙串。Swift 回归 29 项通过；取消/拒绝认证、锁屏/休眠、异常自动恢复与正式签名分发仍待处理。

### 2026-11-08：0E 真实系统认证测试入口就绪

- 在本机生命周期 demo 加入“测试 macOS 系统认证提示”按钮及结果状态；系统认证 reason 明确告知只验证本机认证，不修改钥匙串。该流程只调用 `SensitiveActionAuthorizing`，不读取或写入 Keychain。
- `swift test` 29 项通过；本机 `.app` 已重新构建并打开。观察到用户完成系统认证后，demo 界面显示“系统认证成功；未访问钥匙串”。未推断认证方式；取消/拒绝结果仍待测。
- 更新 0E 报告、追踪矩阵、任务清单和项目上下文。其他锁屏/休眠、正式分发和异常恢复缺口仍在。

### 2026-11-08：开麦实机双语 partial/final 复测

- 用户澄清前一次无识别输出是因为麦克风未打开。重新开麦后，双语 Streaming Zipformer CLI 观察到多组中文和英文 partial/final，包含中文连续指令和英文短句。
- 记录为一次真实麦克风功能冒烟通过；部分识别词句有误，按用户要求作为后续模型优化项，不作为当前功能冒烟阻断项。合计已有三次实机 CLI 观察到 partial/final。
- 阶段 0 仍未验收；驱动异常、SwiftUI 音频集成、性能与模型许可等缺口仍在。

### 2026-11-08：真实麦克风 Ctrl-C 停止冒烟

- 用户运行双语 Streaming Zipformer 麦克风 CLI，程序进入“正在本机识别”；停止前未显示 partial/final，按 Ctrl-C 后显示正常停止提示并返回 shell。
- 这证明真实设备手动停止路径能返回；用户随后说明当时麦克风未打开，因此该次不计为识别成功。报告、追踪矩阵和任务清单已更新。
- 阶段 0 仍未验收；后续需确认讲话时是否有 partial/final，并继续处理驱动异常、SwiftUI 集成、许可和其他工作包缺口。

### 2026-11-08：0B 用户中断路径清理回归

- 将 mock 麦克风清理回归扩展为两种退出：识别器普通异常时错误向上传递；模拟 `KeyboardInterrupt` 时显示停止提示。两条路径都会退出输入流上下文并清空有界缓冲，没有启动真实麦克风。
- 0B 仍需真实设备上的停止/驱动异常冒烟、SwiftUI 音频链路和其他阶段验收证据。
- 验证通过：`tests/test_microphone_buffer.py` 9 passed；全量 Python 149 passed；compileall、`uv lock --check`、`git diff --check` 通过。

### 2026-11-08：0B 识别器异常时的本地清理回归

- 新增模拟麦克风 callback 与故障 decoder 回归：decoder 抛出异常后，输入流上下文退出，音频缓冲关闭并清空；测试没有启用真实麦克风。
- 真实设备的 Ctrl-C / 驱动异常仍需本机交互冒烟，SwiftUI 音频集成也未覆盖。0C 的陈旧取消/JSON 状态同步已修正；两家 Provider 服务端是否停止生成仍未知。
- 验证通过：麦克风窄回归 8 passed；全量 Python 148 passed；compileall、`uv lock --check`、`git diff --check` 通过。

### 2026-11-08：完成 0C 取消证据对齐与 API Key 提示回归

- 对齐了阶段追踪和 Provider 报告：DeepSeek、OpenRouter 均已各自完成一次 SSE 首片段后客户端取消；Provider 是否停止生成或计费仍无服务端证据。DeepSeek JSON 现记为三次一空两成功。
- 补充 CLI 错误提示回归：401 在所有 capability 出错路径均显示中文 API Key 认证失败和 Keychain 检查指引；403 等其他状态不误标为 Key 错误。
- 验证通过：窄回归 36 passed；全量 Python 148 passed；compileall、`uv lock --check`、`git diff --check` 通过。阶段 0 未验收，0C 剩余缺口仍见追踪矩阵。

### 2026-11-08：Provider API Key 错误分类与 DeepSeek JSON 复核

- 用户再次授权的 DeepSeek JSON 请求成功返回 `{"phase0":"ack"}`，结构匹配，finish_reason=`stop`，tokens=68/28/96。结合前一次成功（68/46/114），此前空正文不是 API Key 错误的证据；空正文根因仍未知。
- 适配器对 HTTP 401 给出凭据认证失败提示，并区分 402 余额、403 权限、429 限流；Keychain 缺失仍是独立提示。`error` probe 只把 HTTP 400/422 作为预期请求校验错误，不会把认证/余额等 4xx 误报为通过。错误响应正文仍丢弃；没有发送验证 Key 的额外远端请求。
- 验证通过：窄回归 34 passed；全量 Python 145 passed；`python -m compileall -q pac_poc scripts`、`uv lock --check`、`git diff --check` 均通过。0C 仍未验收。后续 Provider 请求仍需逐项 Consent。

# HANDOFF

> 文档入口：稳定项目约束见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)，已确认/待决选择见 [DECISIONS.md](DECISIONS.md)，阶段任务与下一步见 [TASKS.md](TASKS.md)，阶段证据见 [追踪矩阵](poc/phase0-traceability.md)。本文件仅作为最近交接摘要；避免在这里重复维护完整任务和决策清单。

最近更新：2026-11-09（Asia/Shanghai）

## 最近交接

### 2026-11-08：OpenRouter SSE 客户端取消实测

- 用户逐次确认 `ALLOW OPENROUTER CANCEL 1` 后，真实 SSE 返回首个片段 `phase0-probe-`，脚本立即关闭 gateway stream。与 DeepSeek 一样，证明客户端取消路径；没有服务端信号说明 Provider 停止生成或计费。
- 两家客户端取消实测均完成；DeepSeek JSON 后续已有第三次观察，三次一空两成功；DeepSeek 服务端仍未提供费用/区域 metadata，取消是否停止 Provider 生成未知。阶段 0 整体仍未验收。

### 2026-11-08：DeepSeek SSE 客户端取消实测

- 用户逐次确认 `ALLOW DEEPSEEK CANCEL 1` 后，真实 SSE 返回首个文本片段 `phase`，脚本立即关闭 gateway stream。此结果验证客户端取消路径；没有服务端信号可确认 Provider 停止生成或停止计费。
- 取消能力的本地资源关闭回归已通过（窄 34、全量 145）；本次真实探测无自动重试。随后用户已完成 OpenRouter `cancel`；见上方最新交接记录。

### 2026-11-08：Provider SSE 首片段后取消探测就绪

- `probe_provider_capability_poc.py` 新增 `cancel` 能力：每次经精确 Consent 发起一条 SSE 请求，收到首个文本 delta 后主动关闭 gateway stream。脚本提示可能计费，并明确只观测客户端关闭，不把它当作 Provider 已停止生成的证明。
- 新增 MockTransport 测试，首片段后关闭 gateway stream 会关闭底层 HTTP 响应体。窄回归 34 项、全量 Python 145 项、compileall、uv lock --check 均通过。
- 下一步可分别逐次确认 `deepseek cancel` 与 `openrouter cancel`。复现命令与证据限制见 `poc/phase0-remote-provider.md`。DeepSeek JSON 目前两次一空一成功，原因/重复一致性未明。

### 2026-11-08：拒绝路径 PID 级 socket 检查完成

- 用户提供的全局 `tcpdump -i en0` 捕获 546 个 TCP/443 窗口包；输出包含已建立的会话，未按 PID 过滤，不能据此归因给测试进程。
- 用真实 HTTPX、无 Consent、凭据读取 tripwire 的 harness 分别运行 OpenRouter 与 DeepSeek；两者都在 Adapter 前拒绝，Keychain credential reads=0。Policy 拒绝后在 harness hold 窗口内通过 PID 运行 `lsof -nP -a -p <PID> -i`，均无活动 socket；loopback 正向对照证明 lsof 能列出进程 TCP socket。
- 当前证据支持这两个拒绝路径未建立网络 socket；限制是 lsof 只观察活动 socket，非完整包级/全系统零流量证明。deny-check、真实 HTTPX harness 和证据边界已记录。
- DeepSeek JSON 增强诊断复测已由用户逐次确认：返回 `{"phase0":"ack"}`，结构检查 True，finish_reason=`stop`，tokens=68/46/114；与此前空正文形成一次成功、一次失败。下一步检查 0C 剩余验收，优先远端流式取消语义与 JSON 重复一致性。

### 2026-11-08：拒绝路径真实 HTTPX 与系统监测准备

- 新增 `backend/scripts/probe_denied_egress_poc.py <provider>`：走真实 HTTPX client、默认无 Consent，并以 credential tripwire 避免读取真实凭据；观察窗口内 OpenRouter 被 Policy 在 Adapter 前拒绝，credential reads=0。无 Provider 请求发出。
- `nettop` PID 过滤在本机未能显示测试进程，loopback 正向对照也未出现，不能作为系统证据；`tcpdump` 存在但打开 BPF 需要 sudo，当前 agent shell 无管理员凭据。系统级抓包仍未完成，需用户在本机终端短时运行 `sudo tcpdump -i en0 -nn -l 'tcp port 443 and (tcp[tcpflags] & tcp-syn != 0)'`，同时运行上述本地 harness，然后停止抓包并提供是否观察到新连接/ SYN 的结果。tcpdump 默认只显示包头，不写 pcap 文件。
- DeepSeek metadata 两次结果已由增强 CLI 后记录；下一项可重新逐次确认 DeepSeek JSON 获取 finish_reason/usage，之后完成系统抓包。

### 2026-11-08：DeepSeek metadata 重复观察完成

- 用户分别确认 DeepSeek metadata 两条请求。两次均报告模型 `deepseek-flash`，服务未返回下游 Provider/区域/费用；token 分别 42/29/71 与 42/16/58。第 1 次 ACK 不匹配，第 2 次匹配；旧 CLI 未输出第 1 次正文，原因未知。
- metadata 探测现会在 ACK 不匹配时显示 JSON 编码的实际正文（转义控制字符）。窄回归 33 项、全量 Python 144 项、compileall、uv lock --check 通过。没有重发远端请求。
- 下一步可用增强后的脚本重新逐次确认 DeepSeek JSON，以观察 finish_reason、usage 与空正文诊断；另需完成系统级拒绝零出站验证。阶段 0 仍未验收。

### 2026-11-08：OpenRouter 费用与区域重复核验

- 用户对 `openrouter metadata --repeat 2` 两次请求分别给出精确确认；两次均精确匹配，均报告 Relace/HKG。Token 分别 42/17/59、42/16/58；cost 分别 USD 0.000008752、0.000008252。小样本只记录观察，不推导定价规律。
- OpenRouter 的费用/区域已完成两次重复观察；DeepSeek metadata 重复观察仍待执行，服务此前未提供实际 Provider/区域/费用。下一项命令为 `deepseek metadata --repeat 2`，会逐次确认两条请求。
- 本轮只更新文档；提交前执行 `git diff --check`。

### 2026-11-08：OpenRouter 错误路径返回 HTTP 400

- 用户逐次确认 OpenRouter `error` 探测后，故意无效的 `response_format` 返回已脱敏 HTTP 400，脚本报告预期 4xx 路径通过。与 DeepSeek HTTP 422 结果一致；每家目前只有一次真实错误路径样本。
- 0C 下一项是 OpenRouter `metadata --repeat 2`，每次请求会分别展示目标并要求确认，用于观察重复费用/区域信息；另需考虑 DeepSeek metadata 是否返回可核验的区域/费用数据。
- 更新 Provider 报告、追踪矩阵和任务状态后提交。

### 2026-11-08：DeepSeek 错误路径返回 HTTP 422

- 用户逐次确认 DeepSeek `error` 探测后，故意无效的 `response_format` 收到 HTTP 422；响应正文与凭据均未输出。初次脚本只接受 400，错误地把该请求记为未通过。
- `RemoteProviderError` 现安全保留 HTTP 状态码，`is_client_error` 将 4xx 识别为预期客户端错误；5xx 和无 HTTP 状态错误不计通过。测试窄回归 32 项、全量 Python 143 项、compileall、uv lock --check 均通过。
- 下一项是 OpenRouter `error`（可能计费，需独立确认），然后费用/区域重复核验。阶段 0 仍未验收。

### 2026-11-08：OpenRouter JSON 实测通过

- 用户逐次确认 `ALLOW OPENROUTER JSON 1` 后，返回 `{"phase0":"ack"}`，结构检查 True，finish_reason=`stop`。模型 `deepseek/deepseek-v4.1-flash-1017`，下游 Relace/HKG，tokens=46/36/82，服务报告费用 USD 0.000018276。
- DeepSeek JSON 仍记录为空正文、原因未知；OpenRouter 单次成功不代表稳定性。下一项为 DeepSeek `error` 探测，故意使用无效 response_format，可能计费；须用户对脚本显示的请求逐次确认。
- 已更新 Provider 报告、阶段追踪矩阵与任务清单；变更待 `git diff --check` 并提交。

### 2026-11-08：DeepSeek JSON 空正文与诊断增强

- 用户逐次确认 `ALLOW DEEPSEEK JSON 1` 后，真实请求返回空 JSON 正文，结构检查失败。旧 CLI 未打印 finish_reason、usage 或路由 metadata，因此原因无法判定；无重试。
- `RemoteCompletion` 现保留 finish_reason，JSON 探测输出 finish_reason、模型/路由、token/cost；增加本地 MockTransport 解析回归。窄回归 31 项、全量 Python 142 项、compileall、uv lock --check 通过。
- 下一步逐次确认运行 OpenRouter JSON 探测，观察结构化响应及诊断字段；不要把 DeepSeek 此次结果标记为支持或 Provider 故障定论。0C 仍未验收。

### 2026-11-08：0C 拒绝边界复核

- 本轮分别运行 DeepSeek 与 OpenRouter `deny-check`。两者均在无 Consent 情况下得到 Keychain reads=0、HTTP transport calls=0；检查未出网。证据是进程内 tripwire，不等同于操作系统级抓包。
- 下一步能力矩阵优先跑 DeepSeek JSON，再 OpenRouter JSON；每条命令会单独展示内容并要求精确确认。随后再考虑可能计费的错误路径、metadata 重复核验。阶段 0 仍未验收。

### 2026-11-08：OpenRouter 工具提案实测通过

- 用户在诊断增强后的脚本中再次独立确认 OpenRouter tools 请求。第三次探测返回 `phase0_echo_synthetic(marker=phase0-probe-ack)`，finish_reason=`tool_calls`，模型 `deepseek/deepseek-v4.1-flash-1017`，下游 Provider `Relace` / `HKG`；提案未执行。
- 前两次已授权请求返回空 proposal（第二次文本为空），原因仍未知；第三次成功证明固定配置有可用端到端路径，不代表稳定性。0C 还需两家 JSON/错误、费用和区域重复核验、拒绝后的系统级零出站证据。详见 `poc/phase0-remote-provider.md`。
- 本轮仅更新实测证据与排程文档；待执行 `git diff --check` 并提交。

### 2026-11-08：OpenRouter 工具探测诊断增强

- 用户在保持 `provider.require_parameters=true`、`allow_fallbacks=false` 的配置下再次确认 OpenRouter 工具探测；结果仍为 `工具调用提案（未执行）: []` 与空模型文本。此请求发生在 finish_reason/路由诊断输出加入前，故上游返回形态和原因仍未知。
- 为下一次可复核探测，`ToolCallResult` 现传递 finish_reason、model，以及 OpenRouter metadata 中选中的 downstream Provider/region；CLI 会展示这些字段。工具仍仅作为数据展示、不执行。
- 本地 MockTransport 回归覆盖 OpenRouter 成功响应的这些 metadata 字段；窄回归 31 项、全量 Python 142 项、compileall、uv lock --check 与 git diff --check 均通过。下一步可由用户再次逐项确认 OpenRouter tools，以取得诊断字段；阶段 0 仍未验收。

### 2026-11-08：0C Provider 能力探测工具

- 新增 `backend/scripts/probe_provider_capability_poc.py`，按 Provider/能力单次运行，覆盖 streaming、强制工具提案（不执行）、JSON、故意触发 4xx、重复 metadata，以及无授权 deny-check。每个真实 HTTP 请求都需要单独输入精确确认；故意错误请求可能计费。
- Adapter 新增显式 `tool_choice` 透传。窄回归 31 项通过；deny-check tripwire 结果为 Keychain reads=0、HTTP transport calls=0。该结果不是系统级抓包。用户随后完成 DeepSeek 与 OpenRouter 各一次真实 SSE 探测，拼接响应均精确匹配 `phase0-probe-ack`；DeepSeek tool proposal 成功，OpenRouter 首次没有返回提案，已增加受支持参数路由过滤并等待复测。
- DeepSeek 首次工具请求返回 HTTP 400，正文未保留。按 DeepSeek 官方说明，默认 thinking mode 与指定 tool_choice 不兼容的推断已被落实为工具请求显式关闭 thinking；用户重新确认后获得正确的合成 `phase0_echo_synthetic` 提案，未执行工具。下一项为 OpenRouter tools。
- OpenRouter 工具探测经确认后返回空 proposal list，未显示普通文本，端点 metadata 也未包含在工具结果中，原因尚未确认。根据 OpenRouter 文档，部分不支持工具的上游会忽略 tools 字段；已添加 `provider.require_parameters=true`（仍禁用 fallback）及空提案文本诊断，等待重新授权复测。
- 复现命令、payload、确认短语及未决限制见 `poc/phase0-remote-provider.md`。

### 2026-11-08：0C 同一 Gateway 双 Provider 路由

- 新增 `backend/scripts/probe_provider_switch_poc.py`：同一 ModelGateway 注册 DeepSeek 与 OpenRouter 两个固定 adapter，逐家展示合成请求并要求独立精确确认；拒绝或失败不触发自动 failover。
- 新增 MockTransport 回归证明双路由端点和对应 Keychain account 均按 Provider 选择；窄回归 29 项通过，脚本 compileall 通过。用户之后已分别确认并完成真实顺序路由，两家均精确匹配；OpenRouter 返回 Relace/HKG。该路径不代表自动 fallback；更广能力矩阵仍待验证，见 `poc/phase0-remote-provider.md`。
- 更新后全量 Python 回归 **140 passed**。阶段 0 仍未验收；真实 SSE/工具/JSON/错误能力、其他阶段缺口和延期决策仍需按矩阵处理。

### 2026-11-08：0G Python 依赖 SBOM

- 从锁文件导出 CycloneDX 1.5 SBOM，覆盖当时所有 54 个 Python 锁定依赖（包括所有 extras 与 dev 组），并核对 BOM 的 `(name, version)` 集合与 `uv.lock` 完全一致。此后加入实时语音依赖；最新 55 个非根依赖的报告和 SHA-256 见 `poc/phase0-python-sbom.md`。
- uv 导出的组件未包含许可证字段；当时 54 个锁定 Python 包均有初步许可证线索。最新 55 个非根包也已补充 `websockets==17.4` 的精确 PyPI BSD-3-Clause 来源；完整许可证范围/通知审查、模型权重许可、真实标注记忆检索集和 D-014 模型决定仍未完成。

### 2026-11-08：两家 Provider 实测与本地语音功能复测

- 用户在每条命令中分别输入精确确认短语后，DeepSeek 与 OpenRouter 各完成一次 L1 合成文本请求，均返回 `phase0-probe-ack`。DeepSeek：`deepseek-flash`，prompt/completion/total=42/41/83，服务未返回 downstream Provider、region 或 cost。OpenRouter：`deepseek/deepseek-v4.1-flash-1017`，下游 `Relace` / `HKG`，token=42/17/59，cost USD 0.000008752。报告见 `poc/phase0-remote-provider.md`。
- 用户另运行 30 秒双语麦克风 CLI，观察到多个 partial 和一个 final。用户指定本轮 ASR 验证以链路功能为准，识别质量留待后续模型选择/优化；该轮不计 CER。测试仍未覆盖 SwiftUI 采集、停止/异常清理、性能和多轮稳定性。
- `cd backend` 因用户终端已经位于 backend 目录而报错，之后运行的脚本命令仍成功。

### 2026-11-08：阶段追踪记录与最新 Provider 证据对齐

- 将 D-010 保持为 V1 Provider 选型待决，同时把两家实际合成文本调用记录到阶段追踪；更新 Consent/Policy 真实路径证据与 Python 139 项最新回归数。阶段 0 仍有明确缺口，不能签收。

### 2026-11-08：首次双语麦克风实测与 Provider 组合输入

- 用户主动运行官方中英 Streaming Zipformer 麦克风 CLI，回报多个 partial、两个 final。混合中文/英语话语出现可见错词，第二段英语也未稳定识别；无逐字 ground truth，未算 CER。该轮只作为一次真实设备观察，原始音频未保存。复测要求见 `poc/phase0-local-asr.md` 和 `TASKS.md`。
- 用户给出两家 Provider 候选：DeepSeek、OpenRouter，并确认 DeepSeek 按中国处理、OpenRouter 选 Global。官方隐私/区域资料与模型 id 见 `poc/phase0-remote-provider.md`。
- 已向用户说明不要把 API Key 发到聊天。新实现固定 Keychain service `com.personal-ai-assistant.phase0.provider`，account 分别为 `deepseek`、`openrouter`；每次请求须先由用户在本机 CLI 输入精确确认语句，ConsentAwarePolicy 放行后才从 Keychain 读取并发送。
- 用户命令开头的 `cd backend` 报错只因其已位于 `backend` 目录；后续相对路径命令实际成功运行并启动麦克风捕获。

### 2026-11-08：DeepSeek / OpenRouter 一次性探测实现

- 新增固定 URL/model/region 的 OpenAI chat-completions adapter、macOS `/usr/bin/security` Keychain reader 和 `scripts/probe_remote_provider_poc.py`。每次运行最多发一个 L1 合成文本请求；不重试、不 fallback、不执行模型工具。正确的逐次确认短语后才会生成 60 秒精确 Consent，策略通过后才读取 Keychain；拒绝路径在本机验证无 Keychain 读取/网络请求。
- MockTransport 验证默认拒绝、文本请求、SSE、工具调用数据（不执行）、`response_format`、OpenRouter provider failover 关闭、选定 Provider/region/token/cost metadata、端点/model/region allowlist 和 HTTP 错误脱敏。局部测试 28 项，全量 Python 139 项，Swift 27 项通过；`compileall` 与 `uv lock --check` 通过。
- 用户还未把 API Key 保存到 Keychain，故没有真实 Provider 请求。下一步按 `poc/phase0-remote-provider.md` 创建两项登录钥匙串记录，然后由用户分别在 `deepseek` 与 `openrouter` CLI 探测提示中输入授权短语。阶段 0 仍未验收。
- 用户随后已分别运行两家探测并输入对应确认短语；两次均返回 `provider credential is missing or unavailable in Keychain`。查询未取得密钥，因此无 HTTP 请求。下一步核对 login 钥匙串“通用密码”项的 service/account 与报告完全一致；具体结果写入 `poc/phase0-remote-provider.md`。
- 用户之后提供截图；本机只读元数据查询确认两个账户名与 service 在 login 钥匙串匹配（未读取密钥值）。用户报告 DeepSeek 一次合成请求成功；OpenRouter 因账户余额不足的判断按用户要求记为预期失败，但原因未独立核验。后续仍需 OpenRouter 成功探测证据；阶段 0 未验收。

### 2026-11-08：双语流式 ASR 分帧评估与评分修正

- 官方 sherpa-onnx `sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20` 已下载至忽略目录 `backend/.poc-data/models/`。包内 README 声明 Apache-2.0；模型页、来源和四个关键文件 SHA-256 记录在 `poc/phase0-local-asr.md`。
- 使用项目 streaming adapter 按 200 ms 输入 8 条 Tingting 中文、1 条 Samantha 英语、1 条中英混说合成 WAV，尾部追加 3 秒静音：10/10 final、82 partial、weighted CER 0.0254。小型合成样本只证明适配器文件分帧路径可运行；真实麦克风及 SwiftUI 流程仍需用户操作。
- 修复 CER 对英语大小写敏感的问题，并修复多段 final 只评分最后一段的问题；ASR 评测回归 8 项通过，Python 全量 129 项、Swift 27 项通过。
- 下一步由用户按固定中英短句重复麦克风测试；其余阶段缺口与门禁以 `poc/phase0-traceability.md`、`TASKS.md` 为准。阶段 0 未验收。

### 2026-11-08：0E/0H 交接记录去重与差异核对

- 对照实现、报告与当前回归，清理了 0E 报告中的陈旧说法：SwiftUI demo 启停和退出清理已有一次实机证据；supervisor 异常退出后由调用方显式重启已有集成回归；DB 崩溃/ENOSPC 恢复证据在独立报告，不再写成“未做”。自动重启/退避、锁屏/休眠、真实系统认证提示及正式分发策略仍未验收。
- `TASKS.md` 将已经有证据的 0H 原子替换审查和 0E supervisor 异常退出审查标为本机已完成，避免重复排队；增加了用户可执行的本机麦克风命令和当前外部输入清单。
- 阶段 0 仍待用户亲自开始麦克风采集、提供 Provider 名称/区域，及必要的许可/产品证据；没有运行云请求或启动录音。最新代码回归仍为 Python 129、Swift 27 项通过。

### 2026-11-08：用户提供 Qwen3-ASR 多语言候选

- 将 `~/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25` 移至 `backend/.poc-data/models/` 下同名目录；972 MB 权重与样本目录被 Git 忽略。三份 ONNX 权重 SHA-256 和复现入口记录于 `poc/phase0-local-asr.md`。
- 新增 `backend/scripts/evaluate_qwen3_asr_poc.py`，以 sherpa-onnx 2.0.1 `OfflineRecognizer.from_qwen3_asr` 在 CPU 上对随包 5 条中/英/混说 WAV 执行自动语言离线解码。模型 load 2.025 秒，observed peak RSS 4,472,487,936 bytes；五条加权 CER 0.1564，单项和 RTF 已入报告。完整 transcript 不写日志。
- 88 秒英语样本在 max-total-len 1024 下出现截断警告；该结果已排除。将 max-total-len 调到 4096 后复跑，英语样本 CER 0.1743，RTF 0.8094。
- 本次不是 streaming 或麦克风测试。Qwen 官方资料说明 streaming inference 当前仅在 vLLM backend；本地 ONNX 候选目前经 OfflineRecognizer 整段解码。Qwen 源项目标注 Apache-2.0，但第三方 ONNX 转换包和随附 WAV 的再分发许可待核。用户仍需主动完成真人麦克风流程，未启动录音。

### 2026-11-08 补充

- 用户要求先延期未决事项。`DECISIONS.md` 已将 D-001–D-015 和 ADR-019/020/021/022 记为延期；D-010 Provider 组合待用户另行提供。尚无 Provider 名称/区域或请求授权，因此未读取凭据、未发出云请求。延期不等同于相关阶段验收证据通过。
- 继续 0H：新增子进程在 `os.replace` 调用前与成功返回后暂停，再经 SIGKILL 的两条边界用例。调用前中断保留旧加密备份，成功返回后中断保留新备份；两条路径源库和预期备份均可查询且 `integrity_check=ok`。不声称 syscall 内部中断或断电持久性。
- SQLCipher 专项回归 21 项通过；本轮全量 Python 回归 127 项通过。首次全量运行发现两项追踪文档契约断言需随报告术语同步，已修订后通过。阶段 0 仍未验收。

- 建立 `PROJECT_CONTEXT.md`、`DECISIONS.md`、`TASKS.md` 文档入口；阶段 0 证据权威来源仍是 `poc/phase0-traceability.md` 和各 POC 报告。
- 继续 0H：WAL backup progress callback 中独立 writer 提交一条及活动 reader 固定 snapshot 下三次 writer 提交，源库/备份检索与完整性检查均通过。SQLCipher 专项现为 19 项通过。
- 继续 0H：在 WAL TRUNCATE checkpoint 等待读锁期间对隔离子进程 SIGKILL；释放 reader 后源库两条已提交记录均可检索，完整性检查通过，checkpoint 重试成功。备份复制期间 SIGKILL 现覆盖 DELETE/WAL 两种 journal mode。
- 扩展 ENOSPC POC 到 APFS 临时映像。首轮试跑发现 APFS `hdiutil` 返回多个设备项且填充阶段可能先遇到文件级 `ENOSPC`；现按实际挂载点选择卷设备，并让填充器安全停在 ENOSPC，再独立验证数据库写入失败。48 MiB HFS+ 和 128 MiB APFS 测试均通过。
- 补记当前设备快照：MacBook Air `MacBookAir10,1` / M1 / 16 GiB，macOS 26.5.1，Xcode 26.6，Swift 6.3.3，uv Python 3.12.13，检查时数据卷可用约 18 GiB，内建麦克风/扬声器 48 kHz；主力设备身份仍待确认。
- 离线 Embedding 评估新增三次，4/4 合成 query 均命中，observed max RSS 为 883,130,368–883,490,816 bytes。Embedding 权重/上游模型页和 FastEmbed metadata 标注 Apache-2.0 初核完成；中文 ASR 上游要求接受访问条件，公开分发条款仍未核实，证据见 `phase0-model-license-review.md`。
- 新增根 `README.md`、`AGENTS.md` 和 macOS arm64 GitHub Actions workflow；本机等价 Python 125 项、Swift 27 项通过，`uv lock --check`、`compileall`、锁定依赖安装和 workflow YAML 语法通过。仓库没有 Git remote，因此 GitHub Actions 尚未实际运行。
- ENOSPC 额外尝试“满卷时覆盖既有备份”时，HFS+/APFS 结果不稳定，未纳入验收证据；保留稳定的源库 ENOSPC 回滚与事先生成备份恢复证据。备份目标自身 ENOSPC 仍为缺口。
- 本轮修改还包括根 `AGENTS.md`、`README.md`、`.github/workflows/ci.yml`，SQLCipher checkpoint crash helper、APFS ENOSPC 支持，以及相关 POC 报告、追踪/任务/决策记录。
- 下一步：审查并记录原子替换边界证据；继续补 0E supervisor 异常退出策略的可验证路径。0B 真人麦克风验收与 ASR 授权条款仍待设备/许可输入；0C Provider 组合待用户提供并逐请求明确授权；D-001–D-015 与 ADR-019/020/021/022 已延期。阶段 0 未验收，阶段 1 未开始。

## 当前阶段

阶段 0 POC；0B 本地语音实机验证已完成当前可执行项；0C Gateway/Agent Registry/能力注册表模拟已提交；0D 记忆存储/0F SQLCipher 兼容 POC 已提交；0G 候选权重已下载并离线评测，但产品选择/真实检索集未验收；0E SwiftUI demo 已接入 supervisor 并实测启动/握手/停止/退出清理、两轮 GUI 启停及一次真实系统认证成功（未访问钥匙串）；用户取消/拒绝、异常自动恢复/退避、锁屏/休眠和正式分发仍待验收；0H SQLCipher 崩溃/页数耗尽/WAL 恢复与备份故障注入持续补证。阶段 0 尚未验收，阶段 1 未开始。

## 已完成

- 完整阅读 v1.2 开发规格书、V1.1 技术架构和产品构想书。
- 将三份基线文档纳入 Git 初始提交 `769d4a4`。
- 记录本机 Apple M1/16 GiB、macOS 26.5.1、Xcode 26.6、Swift 6.3.3、Python 3.12 和音频设备。
- 建立本地 ASR 事件契约与 sherpa-onnx 适配器。
- 使用本地中文合成语音与本地模型完成分帧 partial/final 冒烟验证。
- 建立交互式麦克风捕获 CLI、有界内存帧队列和溢出清理；加入 sounddevice 0.5.6。
- 建立 AVSpeechSynthesizer 播放/立即打断 POC；实际打断返回 `interrupted=true speaking=false`。
- Python 测试 9 项、Swift 测试 3 项通过；uv 锁文件检查和本机默认输入参数支持检查通过。
- 修复直接执行 ASR 脚本时 `pac_poc` 无法导入的问题：项目包现由 uv 环境安装，新增锁定的 setuptools 构建依赖和入口回归测试；Python 测试增至 10 项并通过。
- 修复麦克风输入回调中误删 `frames` 后又读取该变量的问题；加入 PCM 帧长度回归测试，Python 测试现为 11 项通过。
- 用户实机反馈当前中文专用 ASR 模型不能识别英文；用户澄清这是后续补下载多语言模型的安排，不是代码 bug，不影响当前使用。本轮不把英语模型替换列为阻塞。
- 开始本机 Gateway POC：本机 Ollama Adapter、Loopback 校验、LocalOnlyPolicy、统一 generate/stream 契约；同机 qwen3.5:0.8b 的生成与流式 smoke 均成功，Python 全量测试 17 项通过。
- 用户实机运行麦克风 CLI，确认可以录音；当前模型是中文专用，英语覆盖留给后续多语言模型下载与验证，不视为实现 bug。
- 完成 Agent Registry / 统一结果协议的 POC 模拟：额外条目必须显式标注模拟，权限只可取父权限交集，不创建产品 Agent run；工作包测试 4 项通过。
- 开始记忆存储 POC：进程内 SQLite + FTS5、来源/claim/观察时间、纠错版本链、FTS 与 fixture embedding 删除、内存备份恢复；产品 schema 未改动。
- 开始 POC-05 本机安全集成：Keychain 凭据管理 + Touch ID/设备密码 gate、loopback FastAPI/token、Swift URLSession/SwiftUI 状态样例、Consent/Policy 默认拒绝；本机 Swift CLI 对真实 loopback FastAPI 的跨语言冒烟成功，具体测试见 `docs/poc/phase0-security-client.md`。
- 开始 SQLCipher 静态加密兼容性 POC：ARM64/Python 3.12 上 FTS5、错误 key 拒绝、独立密钥加密备份/恢复、SQLAlchemy/Alembic migration upgrade/downgrade 通过；候选尚未定案，详见 `docs/poc/phase0-sqlcipher-compat.md`。
- 建立 FastEmbed 多语言 Embedding 候选接口和测试。初次权重下载曾停滞；随后以分段 SHA-256 校验完成固定 revision 权重下载，并在本机完成离线加载和小型合成检索。质量/产品选型仍开放，详情见 `docs/poc/phase0-local-embedding.md`。
- 开始恢复 POC：在 SQLCipher 临时 DB 上验证未提交事务遇进程立即退出后的恢复，以及页数上限触发数据库错误时 memory/FTS 事务回滚；报告见 `docs/poc/phase0-failure-recovery.md`。
- 建立精确 Provider/Model capability registry POC；未知默认拒绝，支持状态要求证据，报告见 `docs/poc/phase0-model-capability-registry.md`。
- 为本地 ASR 新增测试先行的离线计时与峰值 RSS 测量脚本；使用现存合成 WAV 单次记录 ASR 分帧耗时、RTF、模型加载、进程 RSS 与事件计数。数据写入 `docs/poc/phase0-local-asr.md`，只作观察值，不等于麦克风链路性能验收。
- 建立 `docs/poc/phase0-traceability.md`，按 v1.2 §13/§14 和 V1.1 §16 逐项列出阶段 0 证据、状态、缺口、模块依赖、未决项、后续阶段门禁与风险。矩阵判定阶段 0 未验收，阶段 1 未开始。
- 补强本地 Model Gateway 流式关闭语义：非本地 adapter stream 在调用前拒绝；下游关闭时关闭 adapter async generator。测试先行捕获原有未关闭问题，现已修复并回归。
- 历史全量回归记录：Python（包含 `phase0-security` 与 `phase0-embedding` extras）103 项通过；本机 Swift Testing 27 项通过；`compileall`、`uv lock --check`、当时工作包 whitespace 检查通过。最新结果以新增的工作包记录为准。
- 用户澄清本机是软件开发、测试和运行设备，允许下载模型并行进行。Embedding 下载曾出现停滞，后改用分段校验传输完成候选权重；下载不作为开发阻塞项。固定 revision 权重、离线加载与小型合成检索证据见 `phase0-local-embedding.md`。
- 扩展 Swift↔FastAPI loopback 集成 POC：测试 harness 可重启服务；后续固定模块协议和 Swift Foundation `Process` supervisor 已接入独立 SwiftUI demo，随机端口/短期 token handshake、健康检查、停止、owner 释放和失败路径均有测试。本机 GUI 已实测启停；正式签名分发、锁屏策略和异常退出自动重启仍未验收。
- SQLCipher 恢复 POC 新增真实子进程 `SIGKILL` 注入：在事务写入后、提交前强制杀进程，再开启 DB 验证已提交行、未提交 memory/FTS 行和 `integrity_check`；恢复测试只覆盖默认 rollback journal，不代表断电/WAL。
- 同一 SIGKILL 恢复用例现分别在 SQLite DELETE journal 与 WAL 模式下运行通过；正常 WAL checkpoint 已测；断电、checkpoint 执行中断和 APFS/外接介质 ENOSPC 仍未覆盖。
- SQLCipher 备份 POC 增加目标父路径不可创建的故障测试。测试先发现 `mkdir` 异常会穿透 POC API，现统一转为不含敏感信息的安全错误；源数据库查询和完整性仍通过。未模拟真实介质故障。
- 用户澄清“本机”指软件在本机开发、测试、运行，不排除后续本机客户端连接云 Provider；已据此修正阶段追踪矩阵。新建 Gateway `ConsentAwarePolicy` 工作包：对远端 generate/stream 默认拒绝，只有精确有效 Consent/Policy 才会调用 adapter；所有验证使用 fake adapter，不发网络请求。报告见 `docs/poc/phase0-consent-aware-gateway.md`。
- 在工具调用始终不执行的前提下，新增 Ollama Gateway `call_with_tools` 契约与固定本机合成 probe。`qwen3.5:0.8b` 实际返回 `lookup(key=phase0-probe)`，已将精确型号/基础 tools 能力更新为有单次证据；不推断并行工具或严格 JSON Schema。
- 多语言 Embedding 候选权重已分段落在项目 `.poc-data/embedding-staging` 并逐个校验大小和 SHA-256；固定 revision ONNX、tokenizer、unigram 总体完整。最后一个 20 MB 分段的 curl 重试会回退长度，已保留失败尝试供审计，改用 20 个 1 MB 独立段完成。模型在项目 FastEmbed cache 本地加载，两次 4-query 合成检索均 top-1 命中 4/4；`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 下再次加载通过。两次 `/usr/bin/time -l` 最大 RSS 为 851,804,160 与 868,909,056 bytes；这是小样本单次进程观察，不代表产品性能。完整证据和未决项见 `phase0-local-embedding.md`。
- 按 v1.2 §POC-02 / V1.1 §4.5 完成 LiteLLM、Bifrost、Portkey 第一方资料对照报告与文档契约测试；仅桌面资料评估，没有安装 Gateway 或云端调用。ADR-020 仍 Deferred；报告明确本项目 Consent Manager/Policy Engine 默认拒绝、Keychain 凭据和 L3 隔离不可由候选 Gateway 代替。
- 依 FR-SEC-006 修正敏感操作认证策略：由仅 biometric-only 改为 LocalAuthentication `.deviceOwnerAuthentication`（Touch ID 或设备密码）；先添加策略回归测试，验证通过。未触发真实系统提示；旧 `touchIDUnavailable` 错误 case 保留兼容，当前不可用路径抛出通用 `authenticationUnavailable`。
- 为 POC-01 新增同步 barrier 并发测量 helper 与本机脚本；同一合成 WAV 的 ASR 与 Ollama `qwen3.5:0.8b` 请求确证重叠 0.785 秒。该次 ASR frame P95 52.17 ms / max 75.45 ms，ASR+Ollama 进程 RSS 采样峰值 702,267,392 bytes，CPU 增量约 10.95 秒；GPU 未测，只有一次样本且不是完整 Agent 或性能验收。详见 `phase0-local-asr.md`。
- 同一条 6.94 秒合成 WAV 新增 3 次独立进程 ASR 资源测量；各次均为 15 partial/1 final，P50 16.01–16.51 ms、P95 17.22–31.78 ms、RTF 0.0527–0.0665、脚本峰值 RSS 462,159,872–471,318,528 bytes。第一轮帧尾延迟较高，报告保留完整范围。该重复不是独立语料，也不是麦克风/性能验收。
- 本机重跑 8 条合成 ASR 集：8/8 final、59 partial、weighted CER 0.0；最新全量 Python 回归 120 项通过，ASR 测量与合成评测数据仅代表记录样本，性能门槛与真人麦克风验证仍未解决。
- 为 0H SQLCipher POC 增加受限模式 WAL TRUNCATE checkpoint；已验证 checkpoint 前后 encrypted memory/FTS 可查询、checkpoint status 正常、重开 integrity check 通过，并拒绝未列入白名单的 mode 文本。不是进程中断/断电 checkpoint 可靠性证明。
- SQLCipher POC 备份先写同目录加密 staging 文件、重新打开并执行 `integrity_check`，通过后才 `os.replace`。在复制错误与 staging 校验不通过两条注入路径中，旧目标备份均可用原密钥解密、查询且完整，源数据不变，正常异常路径清理 `.partial`。
- 新增真实子进程备份中断 POC：通过 sqlite backup progress callback 确认 staging 已复制部分页面后，对子进程发送 SIGKILL；旧目标备份仍可解密、查询、integrity check 通过，源库 80 条合成记录仍完整。SIGKILL 后 `.partial` 会遗留，测试 teardown 清理；产品运行时 staging 文件保留/清理策略未决，POC 不自动扫描目录。SQLCipher 专项 13 项、全量 Python 107 项通过。详见 `phase0-failure-recovery.md`。
- 增加 WAL 模式加密备份/恢复测试：源库在 WAL 下提交两条 memory/FTS 记录，以独立密钥备份并恢复，源库与恢复库的检索及完整性检查均通过。没有并发 writer/reader 下备份或 WAL 生命周期产品策略证据。SQLCipher 专项现 14 项；全量 Python 回归当时待执行。
- 增加 `os.replace` 故障注入：原子替换抛错时旧目标仍可解密且完整，源库可查询，staging 清理；SQLCipher 专项 15 项通过。随后全量 Python 回归增至 115 项。仍未测试 SIGKILL 恰好发生于 replace 系统调用内部。
- 新增静态加密候选资料比较（SQLCipher、SQLite SEE、CryptoKit AES.GCM 容器）；只引用项目候选/官方第一方资料，明确区分实测与工程推论，未下载/集成 SEE 或实现 CryptoKit 容器。SQLCipher 目前有最多本项目实测证据，但 ADR-019 仍 Deferred；报告见 `docs/poc/phase0-encryption-candidates.md`。
- 新增可复现 SQLCipher/SQLite + FTS5 合成性能对照：同 M1、2,000 条记录/100 查询、连续 3 轮，计入 staging、完整性检查和原子替换的备份路径；写/查/备份及数据库大小范围见 `phase0-sqlcipher-performance.md`。结果只描述该固定合成工作负载；无冷/热控制、并发、CPU/RSS 或产品性能阈值。
- 新增真实 ENOSPC 恢复 POC：只在仓库 `.poc-data` 下创建 48 MiB HFS+ 临时映像，触发 SQLCipher `SQLITE_FULL` 后重开验证源库原记录、未提交记录回滚、完整性与先前独立加密备份；脚本强制工作目录限制并清理映像/挂载。APFS/外接卷、并发、断电与正式 App 目录仍未验证，详见 `phase0-enospc-recovery.md`。
- 为 POC-01 新增字符级 CER 统计和显式 manifest 评估脚本，manifest 路径限制为同目录文件。固定 8 条本机合成中文语音重测为 8/8 final、59 partial、weighted CER 0.0；不是真人麦克风质量或英语能力证据。见 `phase0-local-asr.md`。
- 新增固定 Python 后端模块进程协议 POC：随机 loopback 端口与短期 token 仅经 stdout 握手；owner 可通过 stdin stop/EOF 触发有界优雅关闭，未知命令也会先关服务。三项真实子进程测试覆盖认证握手、健康检查、关闭和异常命令清理；在该工作包完成时尚未接入 Swift `Foundation.Process`。
- 新增 Swift `LocalBackendSupervisor`：Foundation `Process` 固定执行 `python -m pac_poc.local_service`，最小环境变量、不经 shell、限时解析 stdout 握手、loopback 健康检查和 stdin 优雅关闭；停止后可再次启动。Swift 本机集成测试验证有效/无效 token、重复启动保护与重启，以及无握手超时/非法握手清理；此时尚未接入正式 SwiftUI demo，未实现崩溃自动重启/退避和真实认证提示。
- 为 Swift supervisor 增加失败路径回归：固定后端模块不发送握手时触发配置启动时限并回收子进程；非法 JSON 握手被拒绝且不保留子进程。250 ms 只为测试注入值，不视为产品时限决策。
- 为 supervisor 增加异常退出恢复回归；测试先捕获向已退出子进程写 stop 管道触发 SIGPIPE。现在使用 stdin EOF 作为优雅关闭信号，清理退出的 Process 后只允许调用方显式重新启动，不引入自动重启策略。
- SwiftUI demo 已接入本机后端 supervisor：主动启动后才启动子进程，完成 loopback health 检查后显示 connected；用户可主动停止。旧 client-only initializer 保留；fake controller 覆盖启停与启动失败清理，GUI 实机交互另见下项。
- 新增 `backend-lifecycle-poc` SwiftUI demo target 和 build/run scripts，要求显式提供本机 Python 与 backend 路径；SwiftUI demo 已实测启动/握手/停止/退出清理，本机 `.app` 显示健康连接且退出后后端无残留。deinit 清理有集成回归测试；真实认证、异常自动恢复/退避与休眠场景仍开放。
- 为 POC-04 将 Embedding 作为默认禁用、显式注入的 provider 集成进 disposable 内存记忆仓库；FTS 不受影响，语义结果保留 source evidence，纠错/删除/备份恢复派生向量有回归测试。固定候选权重离线合成检索 3/3 top-1；不代表模型选型或真实记忆质量。详见 `phase0-memory-embedding.md`。
- 为 0H 增加 SQLCipher WAL reader contention 故障用例：活动 reader 固定 snapshot 时 `TRUNCATE` checkpoint 返回 busy=1，提交数据仍可检索；释放 reader 后重试 busy=0，关闭/重开后 memory/FTS 与 integrity check 通过。未声称覆盖 checkpoint 执行中断电或 SIGKILL；报告见 `phase0-failure-recovery.md`。

## 当前限制

- 官方双语 Streaming Zipformer 已有合成中英文件分帧 partial/final 证据；Qwen3-ASR ONNX 候选另有随包中/英离线评测。双语模型尚无真人麦克风与 SwiftUI 实机验收；不得静默改用云 ASR。
- 尚未验证 SwiftUI 麦克风链路、中英混合识别质量、P50/P95、资源占用、AEC、TTS 与 ASR 同时工作和锁屏/休眠处理。
- ASR 资源测量已对同一条合成 WAV 做 3 次独立进程重复，但没有独立语料或实时麦克风端到端统计；重复样本分布和可确认性能阈值仍未验证/未决。
- Gateway 已准备 DeepSeek（中国）与 OpenRouter（Global）的固定目标 adapter、Keychain 读取和逐请求确认 CLI；真实远程 Provider 请求、能力矩阵、费用、错误/fallback 尚未验证，需按 `poc/phase0-remote-provider.md` 由用户配置 Keychain 并逐次确认。POC-05 真实系统认证提示、异常自动恢复/退避、锁屏/休眠策略和正式分发仍未验证，SwiftUI demo 的进程握手/启停/退出清理已通过；POC-06 尚未评估密钥生命周期、APFS/外接介质 ENOSPC、断电/checkpoint 执行中断、备份介质故障和产品性能，也未作 ADR。记忆 Embedding 只接入 disposable 内存 repository，产品 schema 与真实检索质量仍未验收。
- 所有产品待决策项继续保持未定；本地 ASR 模型是临时 POC 候选。

## 下一步

继续阶段 0：Provider 方面，DeepSeek 与 OpenRouter 各有经用户逐次授权的真实合成文本请求成功；同一 ModelGateway 顺序跨 Provider 路由也真实通过一次，OpenRouter 返回 Relace/HKG；两家 SSE 各一次真实探测精确匹配。两家工具/JSON/错误能力、拒绝后的系统级零出站与重复费用/区域核验仍缺。Embedding 候选已集成至可注入的内存记忆 POC 并在本机离线合成检索，但真实检索集、资源目标、持久化迁移与产品模型选择未验收。备份 staging 经校验后原子替换目标，真实子进程备份期间 SIGKILL 后旧备份/源数据恢复通过；崩溃 staging 清理策略、断电和介质故障仍未验证。阶段 0 验收前不得进入阶段 1。

## 交接要求

后续每阶段完成或中断时更新本文件，并在报告中列修改文件、设计、测试命令与结果、未决项和验收对照。

### 2026-11-09：修复模型切换后的旧请求反馈

- 用户报告在模型设置切换后，当前聊天仍像是在使用旧模型。检查发现新请求会从 `selectedProvider`/`selectedModel` 获取当前值，但若切换发生在流式请求期间，旧请求仍可继续生成，且状态可能显示旧模型。
- `poc/macos-audio/Sources/MacBetaApp/main.swift`：source、本地模型 ID 或云 Provider 变更时取消旧客户端流、清除 request ID 以忽略迟到回调，并把状态更新为当前 Provider/模型。发送和完成状态显示本轮实际 Provider/模型。
- 验证：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 成功。本轮未运行测试、未启动 GUI、未发送云请求；GUI 切换和连续聊天手动复核仍待做。客户端取消不保证 Provider 服务端同步停止生成。
- 更新 `docs/beta/macOS-beta-chat.md`、`docs/TASKS.md`。如需确认实机行为，请在模型设置中切换本地/千问/DeepSeek/OpenRouter 后观察状态栏，再分别发消息核对显示的本轮 Provider/模型；无需更改任何 Key。接续任务应从 B1 GUI 手动复核开始。

### 2026-11-09：提前接入本机实时语音切片

- 用户报告模型切换与现有语音输入均可用，并要求查看阶段安排后，在不影响流程时提前实现实时语音。文档原计划把 SwiftUI streaming partial、WebSocket、AEC/插话纳入阶段 3；ADR-021（音频协议/AEC/插话）处于 Deferred。用户本轮授权提前做独立的本机 Beta 切片。
- 本次只实现本机路径：采集 PCM 转为 200 ms 帧，通过带 Bearer token 的 loopback WebSocket 到本机 sherpa-onnx Streaming ASR；部分识别只临时显示，final 在用户停止后进入草稿；点“打断并语音输入”会取消文字生成并停止本机朗读，再请求/启动麦克风。队列与 30 秒音频量有界，错误不切云。
- 更新文件：`poc/macos-audio/Sources/MacAudioPOC/LocalVoiceStream.swift`、`LocalAPIClient.swift`、`LocalMicrophoneCapture.swift`、`MacBetaApp/main.swift`；`backend/pac_poc/asr.py`、`voice_transcription.py`、`beta_api.py`；`docs/beta/macOS-beta-voice.md`、`docs/PROJECT_CONTEXT.md`、`docs/DECISIONS.md`、`docs/TASKS.md`、`docs/poc/phase0-traceability.md`。
- 验证：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；`backend/` 下 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc` 通过。没有运行测试、启动 GUI、申请/启动麦克风或播放语音；WebSocket 协议和真实设备 partial/final 尚待实机验证。
- 云端 Realtime（包括 Qwen Token Plan）、自动 VAD/AEC 声学插话、全双工 ASR/TTS、锁屏/休眠/切换用户生命周期均未实现；Token Plan 个人版 Key 仍不得用于自建应用。ADR-021 仍 Deferred，阶段 3 未验收。下一步先构建启动 GUI，由用户明确点击“语音输入”进行设备冒烟，复核 partial、停止后的 final 草稿、取消和“打断并语音输入”行为。
- 2026-11-09 接续时已再次构建成功，但 `open -n` 返回 LaunchServices Launch failed。桌面当前仍运行启动约 36 分钟的旧 Beta 实例，Accessibility 树显示旧版“语音输入”提示；窗口内有未保存的用户聊天内容，因此没有退出/强制替换该实例。最新 build 尚未进入运行中的 GUI。下一步需用户先复制需要保留的未保存聊天内容，再退出旧 Beta 并运行 `poc/macos-audio/scripts/run_beta_app.sh`；新实例显示实时识别提示后，用户再明确点击“语音输入”完成麦克风冒烟。
- 2026-11-09 用户随后报告运行启动脚本时报错。复核发现同一旧 Beta PID 27272 仍在运行（累计约 40 分钟）；`run_beta_app.sh` 原先不检查已有实例，继续以 `open -n` 启动同 bundle 的第二进程并触发 LaunchServices POSIX 162。现已在脚本构建前加入进程检查；发现旧实例时清楚提示先保留未保存聊天、正常退出旧应用再重跑，不会自动杀进程。`sh -n poc/macos-audio/scripts/run_beta_app.sh` 和 `git diff --check` 通过；没有重启/关闭旧实例。用户此时仍需手动复制未保存聊天、退出旧 Beta 后重跑，再点语音输入验证新链路。

### 2026-11-09：修复实时语音无响应

- 用户反馈点击语音输入并说话没有反应。当前 GUI 状态栏显示通用服务器响应错误；语音模型文件存在、Beta 和本机服务均运行。
- 根因已定位：`backend/pyproject.toml` 仅依赖 `uvicorn==0.54.0`，环境里没有 `websockets` 或 `wsproto`，Uvicorn 无法接收 WebSocket Upgrade。`websockets` 当前版本资料列出 17.4（BSD-3-Clause），Uvicorn 官方安装说明指出安装 `websockets` 后默认使用它处理 WebSocket；见 [Uvicorn installation](https://uvicorn.dev/installation/) 与 [websockets on PyPI](https://pypi.org/project/websockets/)。
- 锁定 `websockets==17.4` 并通过 `uv sync --locked --all-extras --all-groups` 安装，同时恢复所有项目 extras。运行时检查显示 `WebSocketsSansIOProtocol`。正常重启空白 Beta 实例，GUI 已显示新控件且本机服务已连接；没有再次开启麦克风。当前真实语音握手/partial/final 仍待用户复试。
- 更新 `docs/beta/macOS-beta-voice.md`、`docs/TASKS.md`。下一步请用户再点“语音输入”说一句不含敏感信息的话，确认系统权限后 UI 是否显示录音计时和 partial；停止后确认 final 写入草稿。若仍失败，回报状态栏完整错误文本；不要重复连续录音。

### 2026-11-09：确认实时 partial 并完善打断语义

- 用户确认语音输入时能在控件右侧看到正在说的话的文字，证明依赖修复后的实时 partial 已在 GUI 工作。final 在停止后是否稳定写入草稿、取消丢弃和生成中点击打断尚未反馈。
- 为避免把被打断的回复当作完整上下文，`BetaChatModel` 现在保留部分回答供界面查看，但将其从下一次模型请求的消息历史中排除，并禁用对该部分回答的本机朗读。正常模型切换取消在途请求时也适用。
- `swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；未运行测试或启动麦克风。新二进制已经构建，但运行中的应用需重启后才载入上下文处理改动。下一步请在保存必要草稿后重启，测试“停止并识别”后 final 进入草稿，再在文字生成中点“打断并语音输入”；不需要切换 Provider 或发送云请求。

### 2026-11-09：启动阶段 0 逐项收尾

- 用户要求逐项完成全部阶段 0。先从工程基线复核：Python 全量首次暴露 2 个云路由 `NameError: time`（`beta_api.py` 改用 monotonic 后遗漏了 `time()`）；已补回导入。窄回归 `tests/test_beta_api.py -k 'cloud_chat_requires_one_time_consent_before_adapter_access or qwen_application_route_is_available_with_exact_region_and_model'` 2 passed；全量 `pytest -q` 170 passed。Swift `swift test --package-path poc/macos-audio` 31 passed；`uv lock --check` 与 Python `compileall` 通过。
- 阶段 0 矩阵工程基线仍为 PARTIAL：workflow 声明 `push`/`pull_request`/`workflow_dispatch`，但没有实际 PR 运行；当前本机 `main` commit `d5ed799` 比 `origin/main` `51b9ab9` ahead 13 commits，尚未推送。`uv.lock` 新增 `websockets==17.4` 后，既有 SBOM SHA 锚点过期，需要更新。当前不通过推送/PR提前发布 13 个未核准提交；待阶段 0改动收敛再安排实际 PR CI。
- 更新 `PROJECT_CONTEXT.md`、`TASKS.md` 和追踪矩阵。本次 `beta_api.py` 修复和最新回归记录仍待提交；接下来按追踪矩阵处理下一项。D-001 设备快照及 D-001/D-002 用户确认已补入决策记录。
- D-001/D-002 已刷新并获用户确认：MacBook Air `MacBookAir10,1` / M1 / 16 GiB 为主力设备，最低 macOS 为 14；本机快照见 `docs/poc/phase0-local-asr.md`。
- 用户已确认当前 MacBook Air M1/16 GiB 为主力设备，最低系统 macOS 14.0；据此将 D-001/D-002 标为 Accepted，并记录与 Beta `LSMinimumSystemVersion` 一致。
- POC-01 实时 streaming 代码增加 seam 注入 `BetaVoiceTranscriber`，自动覆盖 WebSocket token、协议、PCM frame sequence、partial/final/ended 顺序、坏序号拒绝和清理；ASR `finish()` 覆盖 endpoint flush 及 endpoint 缺失时 partial 晋升 final。窄回归 `tests/test_beta_api.py tests/test_local_streaming_asr.py` 当前 13 项通过（Starlette TestClient 有 deprecation warning），随后应跑全量回归。
- 上述实时语音改动后 Python 全量回归 174 passed（1 条 Starlette TestClient/httpx deprecation warning），Swift `swift test --package-path poc/macos-audio` 31 tests passed。依赖 SBOM 已按最新 `backend/uv.lock` 重生成，55 个非根依赖的 name/version 与 CycloneDX 1.5 BOM 完全匹配；新 SHA 见 `phase0-python-sbom.md`。
- 用户已确认 D-003：不保存对话、安全日志保留 30 天、临时会话/音频缓存退出或中断时清理、不备份对话。决策记录与 Beta 范围说明已更新；当前没有持久安全日志，启用写盘前需落实 30 天清理和排除正文/凭据/音频的 metadata-only 约束。
- 用户确认 D-004 最终采用 30 秒音频上限；保留取消、异常、断连和退出时立即清理规则。新增 API 30 秒上限与 WebSocket 断连清理回归，窄回归 15 passed；之后全量 Python 176 passed、Swift 31 passed，compileall 与 `uv lock --check` 通过。用户已在 GUI 验证取消清理；录音中退出和真实驱动异常清理仍未验证，下一步继续逐条处理阶段 0 缺口。
- 用户确认 D-005：自然月 API 预算 100 元人民币，80 元提醒，100 元硬拦截。仅记录决策，Beta 尚无跨 Provider 费用归一/硬限额实现；启用前需实现费用来源和 fail-closed、汇率/缺失 usage、并发和月界重置行为。
- 用户确认 D-006：V1 不提供备份或恢复；未来加入持久数据时再定 RPO/RTO、份数和目的地。现有 SQLCipher/备份 POC 仍只是验证候选和故障行为，不构成产品功能。
- 用户确认 D-007 的 V1 范围：不保存会话、不备份、不设置 app 数据库；持久化功能开发前再选静态加密方案。ADR-019 继续 Deferred，SQLCipher POC 不视为产品选型。
- 用户确认 D-008：V1 不支持外接盘作为活动数据目录；随持久化数据目录功能再评估。该决策也不批准将模型权重或缓存写到外接盘。
- 用户确认 D-009：少量固定专业 Agent 归入 V2，完整 Agent 集归入 V3；V1 继续单总助理。Agent Registry POC 仍为模拟接口。
- 用户确认 D-010：V1 默认千问应用 API，并支持 DeepSeek（中国）及 OpenRouter（Global）。此为 Provider 范围决策，不替代 POC-02 尚缺的完整能力、费用、区域、错误和取消验证；每个真实远端请求仍受 Consent/Policy 控制。
- 用户确认 D-012：V1 支持用户主动只读导入 TXT、Markdown、PDF，单文件最多 10 MB。产品导入流程尚未实现；启用前须完成文件类型/路径和 PDF 解析资源安全 POC。
- 用户确认 D-013：主力 M1/16 GiB 上 App 启动 P95≤5 秒、ASR partial P95≤500 毫秒、停止录音到 final 草稿可用 P95≤2 秒。现有合成/CLI 测量不是端到端验收，须补真实 GUI 会话分布。
- 用户确认 D-014：V1 不提供长期记忆/Embedding；开始持久化记忆功能前再定模型和格式。FastEmbed/MiniLM 的小型合成集 POC 不作为产品型号或 schema 选择。
- 用户确认 D-015：V1 不提供 app 数据导出；未来加入持久数据时再定格式和默认加密，当前不生成 app 导出文件。
- 用户确认 ADR-020：V1 继续使用项目自有轻量 ModelGateway，不引入开源 Gateway 运行依赖；LiteLLM/Bifrost/Portkey 研究留作后续评估参考。
- 用户确认 ADR-021：V1 本机点击触发实时 ASR，语音按钮可打断文字生成，final 入草稿；不做 AEC、自动声学插话或云 Realtime。GUI 停止后 final、取消清理和打断仍待用户实机验证。
- 用户在最新 Beta GUI 完成三项语音冒烟并确认均通过：停止后 final 进入草稿；取消丢弃 partial、草稿不变；本地文字生成时点击语音会打断生成并开始采集。录音中退出清理、真实驱动异常、TTS 手动播放和 P95 端到端性能仍待验证。
- 用户随后实机验证录音中 Cmd-Q：app 和 backend 均退出，重启后没有残留转写或录音。D-004 的用户可执行路径已覆盖；真实 AVAudioEngine 驱动故障仍未注入，D-013 P95 样本仍待采集。
# 2026-11-09 阶段 0 语音退出证据及离线延迟观察

- 用户确认：录音中按 Cmd-Q 后应用与 backend 都退出，重启后没有残留转写或录音。该结果已由用户实际验证，D-004/ADR-021 和 Beta 语音路径的退出清理证据已更新；真实 AVAudioEngine 驱动故障仍未在硬件上复现。
- 对同一 `bilingual-mandarin-16k.wav` 执行 20 次现有离线 ASR 测量：每次 28 帧、10 partial、1 final；运行级帧 P95 为 11.378–14.229 ms，运行级 P95 的 P95 为 13.721 ms；模型加载 0.575–0.752 秒。样本与方法详见 `docs/poc/phase0-local-asr.md`。这是离线帧计算，不是 Beta 麦克风/UI partial 端到端性能证据。
- 阶段 0 仍未验收。继续按追踪矩阵逐项推进；近期可继续补 D-013 的 App 启动 P95 与停止到 final 草稿 P95。若需真实 GUI 计时或用户朗读配合，会提供具体步骤；不把离线计算结果外推为整链路通过。
- 工作前 Git 状态干净，分支为 `main`，本地领先 `origin/main` 34 个提交。本轮仅更新文档，待 `git diff --check`、复核变更并提交。

# 2026-11-09 D-013 GUI 性能采样准备

- 新增可选 `PAC_BETA_PERF_DIAGNOSTICS=1` 模式，展示进程启动至本机服务 ready、200 ms PCM 帧就绪至 partial 更新 SwiftUI 状态、点击停止至 final 草稿更新三项耗时。只在当前进程内保留数值，默认关闭，不保存转写或音频；指标边界见 `docs/beta/macOS-beta-voice.md`。
- 验证：`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过；`swift test --package-path poc/macos-audio` 通过（31 项）；`sh -n poc/macos-audio/scripts/run_beta_app.sh` 与 `git diff --check` 通过。采样值尚未收集。
- 下一步需要用户运行 `PAC_BETA_PERF_DIAGNOSTICS=1 poc/macos-audio/scripts/run_beta_app.sh`，收集 20 次 app 启动值、20 次 partial 和 20 次停止→final 草稿值。此操作会开启用户主动点击才开始的本机麦克风采集；建议只说不含敏感信息的固定短句。完成后将当前面板显示的每类样本数/P95 与 20 个启动值发回，之后继续处理矩阵其他缺口。
- 完成本次提交后本地 `main` 预计领先 `origin/main` 36 个提交；勿推送。阶段 0 仍未验收。

# 2026-11-09 Beta 模型切换实机确认

- 用户确认模型之间可自由切换，切换后的当前聊天使用新选择；用户也反馈新千问 API 可以正常聊天。B1 文档与任务清单已据此更正；旧的单次合成失败保留为历史样本，无法追溯是否到达 Provider/计费。停止/取消生成的 GUI 专门复核仍待做。
- 阶段 0 性能采样已准备好 opt-in GUI 面板。按上一节的步骤由用户采集 D-013 数据；这是当前需要手动参与的一项。
- 最近提交 `403b42e`（B1 文档）、`b3e0b19`（性能诊断）和 `d62ff5a`（语音退出及离线指标证据）均在本机 `main`；本轮变更尚未推送。工作区在交接前应保持干净。
- 用户先贴出 5 次 `bash run_beta_app.sh` 构建日志；日志没有 GUI 计时值，且未设置 `PAC_BETA_PERF_DIAGNOSTICS=1`，故不能用于 D-013。已重新提供仓库根目录的正确命令和采样步骤；当前等待实际数值。
- 用户随后报告 20 个启动值均低于 5 秒（原范围文本“0.9s-0.11s”端点/小数位有歧义），第一次语音停止正常，但紧接着再次点语音输入无响应。当前 CUA 观察到 Beta GUI 有语音按钮且状态栏显示 WebSocket 服务响应错误；没有开启新的麦克风采集。
- 根因是服务端在向客户端发送 WebSocket `ended` 后才释放 ASR 单会话锁，快速重连可能撞锁。现改为结束并清理 ASR 流、释放锁后才发 `ended`；同一客户端结束后立即新建会话回归通过。`tests/test_beta_api.py tests/test_local_streaming_asr.py` 15 passed；全量 `UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q` 176 passed（1 条 Starlette/httpx deprecation warning）。GUI 重构建后的二次录音仍需手动验证。
- 下一步：用户 Cmd-Q 退出旧 Beta，运行 `PAC_BETA_PERF_DIAGNOSTICS=1 ./poc/macos-audio/scripts/run_beta_app.sh` 构建并重开；先验证停止后立即再次语音可用，再继续累计 20 个 partial 与 20 个停止→final 样本。避免重复做云端请求。
- 修复提交：`46bca45`（语音锁在 `ended` 前释放）。用户报告的 20 次启动值均低于 5 秒，因此启动门槛有用户观测支持；原范围文本仍需更正精确上下界。partial/final 性能尚无有效 GUI 分布，阶段 0 不能据此验收。
- 用户回报重构建后第二次语音仍无响应；随后 CUA 查看当前窗口显示“测试版尚未配置”，进程快照只有 App、没有 backend。该运行没有加载启动脚本注入的 `PAC_POC_PYTHON`/`PAC_POC_BACKEND`，因此尚不能判断 `46bca45` 的 GUI 复测结果。用户已收到先 Cmd-Q，再从仓库根目录运行诊断启动命令，并确认新窗口显示“本机服务已连接”后再测的步骤。
- 后续用户反馈仍出现英文 “There was a bad response from the server”。本次进程快照确认 Beta App 和其管理的 `pac_poc.local_service` 均运行；GUI Accessibility 显示本机已连接、partial 样本 n=5、stop→final n=0。WebSocket 握手时服务端的忙碌拒绝是该英文错误的一个可能原因，但根因尚未证实。客户端现对本机语音 WebSocket 做最多 5 次、间隔 200 ms 的握手重试；耗尽后显示中文提示并明确音频未发往云端。验证：Beta Swift build 通过，`swift test --package-path poc/macos-audio` 32 项通过。下一步需用户 Cmd-Q 后重建启动，确认立即连续两次“语音→停止并识别”均能开始且 final 入草稿；若仍失败，请提供最新状态栏全文与诊断面板 n/P95。性能采样只有在这条路径通过后继续。
- 已同步 `PROJECT_CONTEXT.md`、`TASKS.md`、`DECISIONS.md`、本机语音报告和阶段 0 矩阵中有关当前重连状态的摘要；历史记录保留为历史，最新验收缺口为：新重试构建尚无 GUI 复测，partial/stop→final P95 未达 20 个有效样本，最终 P95 未取值。`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_phase0_traceability_report.py`（工作目录 `backend/`）9 passed；`git diff --check` 通过。不因文档同步改变矩阵状态。
- 审查发现握手重试的最终提示原先把失败推断为“上一段识别仍在完成”，但这个原因尚未确认；现改为中性连接失败提示，仍明确音频未发往云端。`swift test --package-path poc/macos-audio` 32 项通过；待提交。
- 重新跑当前全量基线：`UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --all-extras --all-groups pytest -q`（`backend/`）176 passed、1 条 Starlette/httpx deprecation warning；`swift test --package-path poc/macos-audio` 32 项通过；`uv run --locked python -m compileall -q pac_poc scripts tests` 和 `uv lock --check` 通过。已将权威当前基线从 Swift 31 更新为 32；远端 CI 和 macOS 14 runtime 仍未补证。文档改动待检查并提交。
- 0G SBOM 可复现性复核：用当前 `backend/uv.lock` 重导出 CycloneDX 1.5 临时清单，锁定非根依赖与仓库 BOM 均为 55 项且 `(name, version)` 集合完全相同；两个 SHA-256 均与 `phase0-python-sbom.md` 记录一致，临时文件已清理。复核过程仅有一次命令环境错误（shell 未提供 `python` 命令），随后用 `.venv/bin/python` 完成核对。该项证明 Python 锁定依赖 BOM 与锁文件一致，不覆盖 wheel 原生组件/模型许可或正式发行物闭包。
- 延续语音 bad response 排查：`/voice/stream` 过去在单会话锁忙时、WebSocket accept 前直接以 1013 关闭，客户端容易呈现泛化握手错误。现改为先验证授权并 accept，再发送明确的 busy `error` 事件并以 1013 结束；无效凭据仍在 accept 前拒绝。新增并发会话回归确认 busy 事件可读取、活动会话保持可用。窄回归 `tests/test_beta_api.py tests/test_local_streaming_asr.py` 16 passed；全量 Python 177 passed（1 条既有 Starlette/httpx 弃用警告）；追踪文档回归 9 passed；compileall 与 `uv lock --check` 通过。GUI 实机根因和修复效果仍待用户复测。
- 用户提供的新截图确认上一版重试客户端在真实 GUI 仍无法恢复连接；诊断显示启动 ready 0.6 ms、partial n=3/P95 31.4 ms、停止→final n=0。根因仍未证实。进一步加固：服务端在 WebSocket accept 后最多等待 ASR 锁 2 秒，正常收尾后直接接受新会话，超时才返回 busy 事件；Swift 客户端遇到 JSON error 会保留服务端原因并立即显示业务拒绝，底层握手异常仍有限重试，避免把两者合并成同一通用错误。新增 busy 并发回归。验证：语音窄回归 16 passed；Python 全量 177 passed（1 条 Starlette/httpx 弃用警告）；Swift Beta build 成功、Swift 33 项通过；追踪文档回归 9 passed；compileall、`uv lock --check` 和 `git diff --check` 通过。此版仍需用户 GUI 实机复测后才能判断修复。
- 用户随后提供两张截图：一张显示“本机实时识别中断”，另一张显示服务端返回“本机语音识别正忙”，诊断 partial n=5、停止→final n=0。这证明旧会话确实仍占用 ASR 锁，但尚未解释前一次停止为何进入中断路径。新增客户端保留 sender/receiver 的底层错误文案；异常停止及用户取消均向服务端发送 `abort` 命令，服务端清理转写器、释放锁并应答 `ended`，之后再关闭 WebSocket。新增 abort→立即新建会话回归。语音窄回归 17 passed；Python 全量 178 passed（1 条既有 Starlette/httpx 弃用警告）；Swift Beta build 成功、33 项通过；追踪文档回归 9 passed；compileall 与 `uv lock --check` 通过。GUI 仍需用户用新构建验证，并把“本机实时识别中断：...”完整错误发回。
