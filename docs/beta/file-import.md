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

PDF 仍禁用。D-012 要求在启用前验证 PDF 解析器的 CPU/内存/对象数/页面数/超时边界；本次没有解析 PDF，也没有将 PDF 冒充为已验证能力。UI 当前只允许 TXT/Markdown。文件相关内容也未做云端处理或长期保存。

## 自动验证

在 `backend/` 目录：

```bash
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked pytest -q tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py tests/test_model_capability_registry_poc.py tests/test_local_model_gateway.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked ruff check pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py tests/test_imported_text.py tests/test_beta_api.py tests/test_orchestrator.py
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked mypy pac_poc/imported_text.py pac_poc/beta_api.py pac_poc/orchestrator.py
```

结果：45 passed；Ruff 全部通过；mypy 无问题；pytest 有一条既有 Starlette/httpx 弃用警告。覆盖有效 TXT/Markdown、路径/类型/二进制拒绝、字符/字节上限、进程内删除、云端拒绝、上下文不可信标注、准确上下文长度门和移除后失效。

`swift test --package-path poc/macos-audio` → 35 passed，Beta app target 编译通过。未重启 GUI 做手动文件选择/移除冒烟；本机聊天联调待下一次启动确认。未读取 Keychain、未发起云请求、未采集麦克风。
