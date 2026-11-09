# 本机文本文件导入

更新日期：2026-11-09

## 已启用范围

- macOS 文件选择器只开放用户主动选取的 `.txt`、`.md`、`.markdown`；不扫描目录。
- 客户端在打开用户选择的安全作用域期间读取文件，限制为普通文件且不超过 10 MiB；读取最多 `10 MiB + 1` 字节，防止选择后文件变大导致无界读取。
- 本机 API 再验证后缀、文件名（拒绝路径分隔符/控制字符）、严格 UTF-8、非空和 NUL；请求体按流最多接收 10 MiB。原文件路径不会发送到后端。
- 文本仅存于后端进程内存，最多 8 个文件、累计 20 MiB；支持通过附件条目移除，应用/后端退出时进程内引用释放。没有临时文件、数据库、索引或持久副本。
- 每次聊天请求最多附带 4 个导入 ID；按编排后所有消息的 `content` 字符总数（含 system 指引和资料边界）计算 40,000 字符限制，超限直接拒绝，不静默截断。
- 文件内容进入本机模型上下文前会加固定 system 指引，作为不可信 JSON 资料；不作为 system 指令。带导入资料的云请求在任何 Provider/Gateway 调用前返回拒绝，即便 UI 误发也不会出站。

## 尚未启用

PDF 仍禁用。新增隔离的 pypdf 7.0.0 安全 POC（`backend/pac_poc/pdf_import_poc.py`），仅在 `phase4-pdf-poc` 可选 extra 下可用，不接入 Beta API/UI。它在独立子进程解析，输入上限 10 MiB、CPU 软/硬限额 4/5 秒、墙钟超时 5 秒、页树最多 100 页、提取文本最多 200,000 字符，并设置解析对象/流解压/工作预算；超时会终止子进程。5 项自动化测试覆盖有效 PDF、输入超限、无效 PDF、页数边界和父进程超时转换（超时通过模拟覆盖）。

此 POC 尚未完成 D-012 启用门：本机尝试对 `RLIMIT_AS`、`RLIMIT_DATA`、`RLIMIT_RSS` 设 512 MiB 有限限额均失败，Python 报 `ValueError: current limit exceeds maximum limit`；当前方案没有可用的硬内存上限。另缺少恶意 PDF 语料、CPU 压力/超时实测、对象数/解压炸弹专项测试或 Beta GUI 端到端验证。因此 PDF 仍禁用，以上 POC 结果不视为产品保证。文件相关内容仍仅本机临时处理，无云端处理或长期保存。

## 自动验证

Swift 客户端请求契约回归（2026-11-09）：`swift test --package-path poc/macos-audio` → 40 passed，Beta target build 通过。新增 URLProtocol fixture 验证导入请求只携带 basename、文件内容和 loopback Bearer token；不包含原始路径；PDF 与大于 10 MiB 文件在网络调用前拒绝。此项不代替 GUI 文件选择、移除和聊天引用实机冒烟。

在 `backend/` 目录：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py
```

结果：45 passed；Ruff 全部通过；mypy 无问题；pytest 有一条既有 Starlette/httpx 弃用警告。覆盖有效 TXT/Markdown、路径/类型/二进制拒绝、字符/字节上限、进程内删除、云端拒绝、上下文不可信标注、准确上下文长度门和移除后失效。

`swift test --package-path poc/macos-audio` → 35 passed，Beta app target 编译通过。未重启 GUI 做手动文件选择/移除冒烟；本机聊天联调待下一次启动确认。未读取 Keychain、未发起云请求、未采集麦克风。
