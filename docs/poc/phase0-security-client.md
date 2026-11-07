# 阶段 0 POC：本机安全与 Swift/FastAPI 集成（工作包 0E）

状态：`IN_PROGRESS`。本报告覆盖本机认证/出站策略和原生客户端连接样例；不代表完整 SwiftUI 应用、真实生物识别交互或阶段 0 验收。

## 已实现与验证

- FastAPI POC API 只提供无副作用 `/health`；OpenAPI 文档端点关闭。
- `create_local_server` 固定 Uvicorn 单 worker、`127.0.0.1`、关闭 access log；API 校验 Host 为 loopback IP、拒绝任何 Origin、要求未过期 Bearer session token，并使用 constant-time 比较。响应不回显 token。
- 本机短期 token 使用进程内对象保存。集成脚本将 token 通过受控 stdin pipe 交给 Swift CLI；token 不进命令参数、环境变量或输出。端口先由测试进程绑定到 loopback，避免测试时端口抢占。
- 原生集成回归现在执行两次完整的本机服务启动→Swift 健康握手→有界关闭，再用新端口和新短期 token 重启并握手；测试验证旧 token 不出现在 Swift 子进程输出中。该项仅证明集成 harness 的服务重启/重新握手，不证明正式 App 拥有或管理后端子进程。
- 新增固定 Python 模块入口 `pac_poc.local_service`：只绑定 `127.0.0.1` 随机端口，token 由服务端生成，仅通过 stdout 首行 JSON 握手提供；stdout 不用于日志。owner 可通过 stdin 发送 `stop` 或关闭管道，服务设置 Uvicorn `should_exit` 并在有界时间内等待关闭。未知命令也会先停止服务再返回错误码；不接受脚本路径、shell 命令或任意服务参数。
- 子进程集成测试验证动态端口、无 token 时拒绝、有效 token 健康检查、`stop`、owner 管道关闭和无效命令清理。它验证固定后端进程协议，不代表 Swift `Process` 集成或正式 App 生命周期完成。
- Swift `LocalAPIClient` 仅允许 HTTP `127.0.0.1` / `::1`，使用内存 token，拒绝 HTTP redirect；SwiftUI POC 连接视图只展示状态并提供主动检查按钮。
- API Key POC 使用 macOS Keychain generic-password，`AfterFirstUnlockThisDeviceOnly`；外部可见的凭据管理 API 只提供写入、删除、存在状态查询，不提供明文读取。
- 凭据写入/删除先经过 `LocalAuthentication` 敏感操作授权门；认证策略为 `.deviceOwnerAuthentication`，允许系统按可用性使用 Touch ID 或设备密码。fake evaluator 测试覆盖策略/原因传递、系统不可用时 fail closed、系统拒绝向上传递；fake authorizer 测试验证拒绝路径不会变更 Keychain。真实系统认证提示未触发。
- Consent/Policy 只允许精确匹配 Provider、Model、Region、Purpose、数据等级和期限的 grant；无 grant 默认拒绝、L3 永远拒绝，支持撤销。没有实现或调用任何云 Provider。
- 当前 POC 没有数据库 schema 变更；FastAPI/Uvicorn 版本已锁定到 `0.159.1` / `0.54.0`。

## 测试命令

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc scripts tests
cd ../poc/macos-audio
swift test
```

最近全量回归：Python（包含 `phase0-security` 与 `phase0-embedding` extras）93 项通过；`compileall`、`uv lock --check` 通过。Swift 测试 16 项通过。Python 测试包括实际 loopback HTTP 服务、Swift CLI → FastAPI 集成和固定 Python 服务模块的 owner pipe 子进程测试；Swift 测试包含真实本机 Keychain dummy secret 写入/轮换/删除及认证策略/拒绝行为 fake 测试。网络集成只访问 `127.0.0.1`。

## 未解决/未验收

- SwiftUI View 目前只完成编译及连接状态模型单测，未在 GUI 中实机交互，也不是完整产品 UI。
- LocalAuthentication API 接入已实现，默认策略覆盖生物识别或设备密码；单测不等于真实系统交互。真实 Touch ID/设备密码提示、拒绝/取消仍未实测。
- 真实 App 启动后端的进程所有权、随机端口重试/生命周期、锁屏行为尚未完成；当前重启用例由测试 harness 负责启动/关闭 FastAPI，并经 pipe 将新 token 交给 Swift CLI。
- 固定后端入口的 owner pipe 协议及优雅关闭已由 Python 子进程测试；Swift App/CLI 尚未成为该进程 owner，未实现启动 readiness 消费、启动超时 UI、异常退出监控或有限退避重启。
- Host/Origin、token 和无云出站策略经过 POC 测试；真实用户 Consent UI、完整数据分类/脱敏/审计与撤销竞态未实现。
- 未做崩溃、重启、磁盘不足、备份恢复故障注入，也未验证静态加密方案；不得将本工作包视为 POC-05 完成。
- 未验证真实云端 Provider，符合本轮本机使用边界；云请求仍保持不可用/默认拒绝。

## 阶段边界

这是 POC 代码，不是 V1 工程底座。凭据服务内部没有明文读取接口；Tool Gateway、任意 shell/文件访问、连接器、后台任务及 Agent 团队均未加入。ASR、TTS、LLM 仍独立配置。
