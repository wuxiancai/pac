# 本机文本文件导入

更新日期：2026-11-09

## 已启用范围

- macOS 文件选择器只开放用户主动选取的 `.txt`、`.md`、`.markdown`；不扫描目录。
- 客户端在打开用户选择的安全作用域期间读取文件，限制为普通文件且不超过 10 MiB；读取最多 `10 MiB + 1` 字节，防止选择后文件变大导致无界读取。
- 本机 API 再验证后缀、文件名（拒绝路径分隔符/控制字符）、严格 UTF-8、非空和 NUL；请求体按流最多接收 10 MiB。原文件路径不会发送到后端。
- 文本仅存于后端进程内存，最多 8 个文件、累计 20 MiB；支持通过附件条目移除，应用/后端退出时进程内引用释放。没有临时文件、数据库、索引或持久副本。
- 每次聊天请求最多附带 4 个导入 ID；按编排后所有消息的 `content` 字符总数（含 system 指引和资料边界）计算 40,000 字符限制，超限直接拒绝，不静默截断。
- 文件内容进入本机模型上下文前会加固定 system 指引，作为不可信 JSON 资料；不作为 system 指令。带导入资料的云请求在任何 Provider/Gateway 调用前返回拒绝，即便 UI 误发也不会出站。

## Beta 客户端并发边界

2026-11-09：macOS Beta 将文件导入限制为单个在途任务。导入期间禁用重复文件选择、发送和语音入口；模型层也拒绝重入。这样避免用户连续打开选择器时并发读取/上传多个 10 MiB 文件，并确保前端最多 4 个附件的限制不会因并发检查竞态而被绕过。后端 8 文件/20 MiB 和每次聊天最多 4 个 ID 限制仍是独立保护。Swift 全量 40 项通过，`personal-assistant-beta` 构建通过。GUI 文件选择、移除及聊天引用闭环仍待干净启动后人工验证。

## 尚未启用

PDF 仍禁用。新增隔离的 pypdf 7.0.0 安全 POC（`backend/pac_poc/pdf_import_poc.py`），仅在 `phase4-pdf-poc` 可选 extra 下可用，不接入 Beta API/UI。它在独立子进程解析，输入上限 10 MiB、CPU 软/硬限额 4/5 秒、墙钟超时 5 秒、页树最多 100 页、提取文本最多 200,000 字符，并设置解析对象/流解压/工作预算；超时会终止子进程。7 项自动化测试覆盖有效 PDF、输入超限、无效 PDF、页数边界、FlateDecode 解压上限和父进程超时转换（超时通过模拟覆盖）。新增的合成解压炸弹 PDF 小于 10 KB，内容解压后超过 worker 的 2 MB 单过滤器上限，实际由隔离子进程拒绝；另一项构造 200,001 字符页面文本，验证 worker 的 200,000 字符上限。

CI 现显式安装 `phase4-pdf-poc` extra，因此通用 Python 回归会实际执行以上 7 项测试，而不是因缺少 pypdf 将该测试模块跳过。该 CI 覆盖只证明代码路径可自动回归，不改变 PDF 的禁用状态或资源隔离证据缺口。

此 POC 尚未完成 D-012 启用门：本机尝试对 `RLIMIT_AS`、`RLIMIT_DATA`、`RLIMIT_RSS` 设 512 MiB 有限限额均失败，Python 报 `ValueError: current limit exceeds maximum limit`；随后又在 worker 启动前用 `/bin/sh` 的 `ulimit -v` 试设 768 MiB、1 GiB、1.5 GiB，三次均被 macOS 返回 `cannot modify limit: Invalid argument`。因此当前目标系统上没有验证通过的硬内存上限。仍缺代表性恶意 PDF 语料、CPU 压力/真实墙钟超时实测、对象数专项测试和 Beta GUI 端到端验证。合成 FlateDecode 上限回归只覆盖一种受控输入，不代表完整恶意样本集。因此 PDF 仍禁用，以上 POC 结果不视为产品保证。文件相关内容仍仅本机临时处理，无云端处理或长期保存。

## 自动验证

Swift 客户端请求契约回归（2026-11-09）：`swift test --package-path poc/macos-audio` → 40 passed，Beta target build 通过。新增 URLProtocol fixture 验证导入请求只携带 basename、文件内容和 loopback Bearer token；不包含原始路径；PDF 与大于 10 MiB 文件在网络调用前拒绝。此项不代替 GUI 文件选择、移除和聊天引用实机冒烟。2026-11-09 只读检查当前已运行 Beta 的 accessibility 控件树，未看到“添加资料”按钮；当前运行窗口显示已有未持久化对话，未重启应用以免清除该会话。仓库源代码仍包含 `import-text-file-button` 与文件选择器，原因可能是运行中的旧构建或控件树遗漏，尚未判定。需在下次用户可接受的干净启动后确认实际控件及导入闭环。

在 `backend/` 目录：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py
```

结果：45 passed；Ruff 全部通过；mypy 无问题；pytest 有一条既有 Starlette/httpx 弃用警告。覆盖有效 TXT/Markdown、路径/类型/二进制拒绝、字符/字节上限、进程内删除、云端拒绝、上下文不可信标注、准确上下文长度门和移除后失效。

`swift test --package-path poc/macos-audio` → 35 passed，Beta app target 编译通过。未重启 GUI 做手动文件选择/移除冒烟；本机聊天联调待下一次启动确认。未读取 Keychain、未发起云请求、未采集麦克风。
