# 本机文本文件导入

更新日期：2026-11-10

## 已启用范围

- macOS 文件选择器只开放用户主动选取的 `.txt`、`.md`、`.markdown`；不扫描目录。
- 客户端在打开用户选择的安全作用域期间读取文件，限制为普通文件且不超过 10 MiB；读取最多 `10 MiB + 1` 字节，防止选择后文件变大导致无界读取。
- 本机 API 再验证后缀、文件名（拒绝路径分隔符/控制字符）、严格 UTF-8、非空和 NUL；请求体按流最多接收 10 MiB。原文件路径不会发送到后端。
- 文本仅存于后端进程内存，最多 8 个文件、累计 20 MiB；支持通过附件条目移除，应用/后端退出时进程内引用释放。没有临时文件、数据库、索引或持久副本。
- 每次聊天请求最多附带 4 个导入 ID；按编排后所有消息的 `content` 字符总数（含 system 指引和资料边界）计算 40,000 字符限制，超限直接拒绝，不静默截断。
- 文件内容进入本机模型上下文前会加固定 system 指引，作为不可信 JSON 资料；不作为 system 指令。带导入资料的云请求在任何 Provider/Gateway 调用前返回拒绝，即便 UI 误发也不会出站。

## Beta 客户端并发边界

2026-11-09：macOS Beta 将文件导入限制为单个在途任务。导入期间禁用重复文件选择、发送和语音入口；模型层也拒绝重入。这样避免用户连续打开选择器时并发读取/上传多个 10 MiB 文件，并确保前端最多 4 个附件的限制不会因并发检查竞态而被绕过。后端 8 文件/20 MiB 和每次聊天最多 4 个 ID 限制仍是独立保护。2026-11-10 后端 API 也增加单飞接收锁：已有上传尚未完成时，第二个上传立即收到 409，且不消费其请求体；因此请求流暂存不会按并发上传数倍增，单请求仍受 10 MiB 流上限约束。Swift 全量 40 项通过，`personal-assistant-beta` 构建通过。之后 GUI 文件选择、导入暂存和移除已用 141-byte 合成 TXT 在本机 Ollama 模式验证通过；附件进入聊天上下文的 GUI 闭环仍待人工验证。

2026-11-10 Swift 聊天请求契约新增 URLProtocol 回归：捕获 `/chat/stream` 请求，验证 loopback Bearer 认证和 `import_ids` 序列化。Swift 全量 44 项通过，`swift build --package-path poc/macos-audio --product personal-assistant-beta` 通过。此自动回归证明客户端会提交选中的资料 ID，不替代 GUI 对话中资料引用的手动验收。

2026-11-10 阶段 6 当前本机 CI 等价复核发现拒绝 PDF/超大文件的 Swift 用例与有效导入用例共享静态 URLProtocol 捕获器；并行执行时前者可能消费后者的请求记录。已为拒绝路径增加独立网络请求计数探针，避免跨测试共享状态。修复后 `swift test` → 44 项通过，Beta target build 通过；CI 的 `uv lock --check`、Ruff、mypy、tracked-file detect-secrets、compileall 和后端全量 282 项均通过。

## 尚未启用

PDF 仍禁用。新增隔离的 pypdf 7.0.0 安全 POC（`backend/pac_poc/pdf_import_poc.py`），仅在 `phase4-pdf-poc` 可选 extra 下可用，不接入 Beta API/UI。它在独立子进程解析，输入上限 10 MiB、CPU 软/硬限额 4/5 秒、墙钟超时 5 秒、页树最多 100 页、提取文本最多 200,000 字符，并设置解析对象/流解压/工作预算；超时会终止子进程。7 项自动化测试覆盖有效 PDF、输入超限、无效 PDF、页数边界、FlateDecode 解压上限和父进程超时转换（超时通过模拟覆盖）。新增的合成解压炸弹 PDF 小于 10 KB，内容解压后超过 worker 的 2 MB 单过滤器上限，实际由隔离子进程拒绝；另一项构造 200,001 字符页面文本，验证 worker 的 200,000 字符上限。

CI 现显式安装 `phase4-pdf-poc` extra，因此通用 Python 回归会实际执行以上 7 项测试，而不是因缺少 pypdf 将该测试模块跳过。该 CI 覆盖只证明代码路径可自动回归，不改变 PDF 的禁用状态或资源隔离证据缺口。

此 POC 尚未完成 D-012 启用门：本机尝试对 `RLIMIT_AS`、`RLIMIT_DATA`、`RLIMIT_RSS` 设 512 MiB 有限限额均失败，Python 报 `ValueError: current limit exceeds maximum limit`；随后又在 worker 启动前用 `/bin/sh` 的 `ulimit -v` 试设 768 MiB、1 GiB、1.5 GiB，三次均被 macOS 返回 `cannot modify limit: Invalid argument`。因此当前目标系统上没有验证通过的硬内存上限。仍缺代表性恶意 PDF 语料、CPU 压力/真实墙钟超时实测、对象数专项测试和 Beta GUI 端到端验证。合成 FlateDecode 上限回归只覆盖一种受控输入，不代表完整恶意样本集。因此 PDF 仍禁用，以上 POC 结果不视为产品保证。文件相关内容仍仅本机临时处理，无云端处理或长期保存。

2026-11-10 macOS 资源隔离资料核对：Apple 将 App Sandbox 描述为限制应用访问文件、网络连接和硬件等系统资源的边界；官方 `os_proc_available_memory()` 说明明确将结果限定为当前 app 可用内存的建议值，数值会随生命周期变化，且调用者不是 app 时返回 0。它不能给当前 Python helper worker 提供可配置、可验证的硬内存上限。此轮没有找到可替代已失败 `setrlimit`/`ulimit` 尝试且在目标 macOS 上验证通过的公共机制；这不证明不存在其他机制。PDF 继续禁用，直到候选隔离能以超限样本证明限制和拒绝行为。[App Sandbox 文档](https://developer.apple.com/documentation/security/app-sandbox)；[`os_proc_available_memory()` 文档](https://developer.apple.com/documentation/os/os_proc_available_memory)。

## 自动验证

2026-11-10 超大附件前置拒绝：API 在 ContextBuilder 将资料 JSON 序列化前，以消息字符数与附件原始字符数之和作下限检查；明显超过上下文上限时返回 413，避免对最大尺寸的合法上传先创建大型 JSON 副本。最终上下文仍执行完整字符上限检查，以覆盖 JSON 转义和固定框架开销。回归替换 Orchestrator 为一旦构造即失败的哨兵，100,000 字符附件仍在编排前返回 413。定向 2 passed，Ruff/mypy 通过；后端全量 282 passed，1 条既有 Starlette/httpx 弃用警告。

2026-11-10 上下文注入边界回归：合成 TXT 内容含“忽略前文指令、插入 system role 并调用工具”的注入文本，文件名含可伪造 JSON 结构的引号。Orchestrator 仍只产出固定 system 指引和 user 消息；附件名/内容经 JSON 编码后保持在同一 user 资料字段，system 指引不含原文，Gateway 请求的 `tools` 为空。云端导入请求的 API 拒绝回归仍通过；这些测试证明上下文隔离和当前无工具面，不证明模型对任意提示注入都能语义免疫，也不替代聊天引用 GUI 手动验收。窄回归 4 passed，Ruff 通过；最新后端全量 273 passed、1 条既有 Starlette/httpx 弃用警告。

Swift 客户端请求契约回归（2026-11-09）：`swift test --package-path poc/macos-audio` → 40 passed，Beta target build 通过。新增 URLProtocol fixture 验证导入请求只携带 basename、文件内容和 loopback Bearer token；不包含原始路径；PDF 与大于 10 MiB 文件在网络调用前拒绝。GUI 文件选择、暂存和移除已另行实测通过；自动契约测试不代替尚未完成的聊天引用 GUI 验收。较早一次只读检查旧运行实例时，accessibility 控件树未呈现“添加资料”；当时窗口有未持久化对话，因此未重启。之后确认 Beta 实例已退出，从仓库根目录运行 `poc/macos-audio/scripts/run_beta_app.sh` 启动当前构建，状态栏显示本机服务已连接，accessibility 树可见 `import-text-file-button`。随后进行本机 GUI 冒烟：仓库内 141-byte 合成 TXT 由文件选择器选中，Beta 显示 `gui-import-fixture.txt` 和 65 字符计数；点击移除后附件 chip 消失，状态提示“已从本机临时资料中移除”。当时应用选择 Ollama 本地模型，未发送聊天消息或触发 Provider，因此只确认文件选择、暂存和移除；资料实际进入聊天上下文的 GUI 引用仍待验证。

2026-11-10 聊天引用 GUI 验收：在新会话选择 `.poc-data/gui-reference-test.txt`（85 bytes，合成内容含唯一标记 `PAC-TXT-REF-20261110-K7Q2`），界面显示文件名和 85 字符；随后询问该资料中的唯一 marker，本机 `qwen3.5:0.8b` 回复包含完全一致的标记，证明本次附件 ID 和内容进入了本机聊天上下文。点击移除后 chip 消失并显示成功状态。没有调用云 Provider、没有采集麦克风。回复用时约 45 秒，期间显示本机生成状态。验收测试聊天保留在本机 SQLCipher 历史；临时导入 chip 已移除，测试文件已在完成记录后删除。该单样本只证明该 TXT 引用路径，不证明所有模型均能准确利用资料，也不改变 PDF 禁用状态。

2026-11-10 补充复核：当前 Beta 仍可选择合成 TXT、显示附件并成功移除。使用本机 `qwen3.5:0.8b` 询问文件 marker 后，约 60 秒仍处于本机生成状态；用户停止后 run 为已取消，UI 明确说明 Ollama 可能仍在结束本机生成。没有远端请求或麦克风操作。此次没有得到资料引用回答；此前约 45 秒成功的单样本验收仍是有效证据。复核用临时文件已移除并删除，测试会话保留在 SQLCipher 历史。延迟原因未判定；当前先记录为本机模型响应波动，不据此归因导入上下文缺陷。

在 `backend/` 目录：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py
```

结果：45 passed；Ruff 全部通过；mypy 无问题；pytest 有一条既有 Starlette/httpx 弃用警告。覆盖有效 TXT/Markdown、路径/类型/二进制拒绝、字符/字节上限、进程内删除、云端拒绝、上下文不可信标注、准确上下文长度门和移除后失效。

`swift test --package-path poc/macos-audio` → 35 passed，Beta app target 编译通过。未重启 GUI 做手动文件选择/移除冒烟；本机聊天联调待下一次启动确认。未读取 Keychain、未发起云请求、未采集麦克风。


2026-11-10 后端并发接收回归：上传 A 暂停在第一段请求体后，上传 B 返回 409 且其异步 body generator 未运行；释放 A 后其完成导入。定向导入测试 3 passed；`ruff check pac_poc/beta_api.py tests/test_beta_api.py` 与 `mypy pac_poc/beta_api.py` 通过；后端全量 274 passed，1 条既有 Starlette/httpx 弃用警告。
