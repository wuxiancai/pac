# 阶段 0 POC：本机安全与 Swift/FastAPI 集成（工作包 0E）

状态：`IN_PROGRESS`。本报告覆盖本机认证/出站策略和原生客户端连接样例；不代表完整 SwiftUI 应用、真实生物识别交互或阶段 0 验收。

## 已实现与验证

- FastAPI POC API 只提供无副作用 `/health`；OpenAPI 文档端点关闭。
- `create_local_server` 固定 Uvicorn 单 worker、`127.0.0.1`、关闭 access log；API 校验 Host 为 loopback IP、拒绝任何 Origin、要求未过期 Bearer session token，并使用 constant-time 比较。响应不回显 token。
- 本机短期 token 使用进程内对象保存。集成脚本将 token 通过受控 stdin pipe 交给 Swift CLI；token 不进命令参数、环境变量或输出。端口先由测试进程绑定到 loopback，避免测试时端口抢占。
- 原生集成回归现在执行两次完整的本机服务启动→Swift 健康握手→有界关闭，再用新端口和新短期 token 重启并握手；测试验证旧 token 不出现在 Swift 子进程输出中。该项仅证明集成 harness 的服务重启/重新握手，不证明正式 App 拥有或管理后端子进程。
- 新增固定 Python 模块入口 `pac_poc.local_service`：只绑定 `127.0.0.1` 随机端口，token 由服务端生成，仅通过 stdout 首行 JSON 握手提供；stdout 不用于日志。owner 可通过 stdin 发送 `stop` 或关闭管道，服务设置 Uvicorn `should_exit` 并在有界时间内等待关闭。未知命令也会先停止服务再返回错误码；不接受脚本路径、shell 命令或任意服务参数。
- 子进程集成测试验证动态端口、无 token 时拒绝、有效 token 健康检查、`stop`、owner 管道关闭和无效命令清理。它验证固定后端进程协议，不代表 Swift `Process` 集成或正式 App 生命周期完成。
- Swift `LocalBackendSupervisor` 现以 Foundation `Process` 直接执行注入的 Python runtime，并固定参数为 `-m pac_poc.local_service`；runtime 与 backend 目录是本机打包配置接口，不接受 shell/附加命令。子进程环境仅含固定 PATH 和 Python 隔离开关，stderr 接 `/dev/null`，stdout 仅解析受限 JSON 握手。启动等待、优雅停止有界；停止超时会 terminate，随后必要时 SIGKILL。token 只保存在内存并用于 loopback `LocalAPIClient`。
- Swift 本机集成测试实测 supervisor 启动→握手→正确 token 健康检查/错误 token 拒绝→关闭，并验证重复 start 被拒、停止后可重启。测试运行时从仓库 backend `.venv` 使用本机 Python。
- SwiftUI 连接 POC 新增可选 backend-controller 接口与主动启动/停止按钮：点击启动后在 detached task 启动服务、创建本机客户端并执行健康检查，健康确认后才显示 connected；点击停止后关闭服务。旧的 `init(client:)` 与“检查本机服务”路径保留。ViewModel fake-controller 测试覆盖成功启停与启动失败清理；GUI 启停实机证据见下。
- 新增独立 `backend-lifecycle-poc` SwiftUI demo target，以及本机 build/run shell scripts；应用运行配置通过 `PAC_POC_PYTHON` 和 `PAC_POC_BACKEND` 显式提供，缺少配置或入口文件时 fail closed。构建输出 bundle 放在忽略目录 `.poc-data/backend-lifecycle-poc.app`，不会纳入 Git。
- 已通过 `poc/macos-audio/scripts/run_backend_lifecycle_poc.sh` 实机启动本地 `.app`，无服务初始显示“尚未检查”；点击启动后状态变为“本机服务已连接”；点击停止后回到“尚未检查”，停止/检查按钮恢复禁用。随后另完成两轮停止→启动→健康检查：每轮 UI 状态正确变化，最终进程表仅有一个受管理的 `pac_poc.local_service`；不覆盖锁屏/休眠或 App 退出期间故障。
- 失败路径测试在 `.poc-data` 临时夹具下运行固定模块入口：无握手服务在 250 ms 配置期限触发 `startupTimedOut` 并被清理；非法 JSON 握手返回 `invalidHandshake` 且不保留运行子进程。该时限是测试注入值，不是产品启动时限决策。
- 子进程握手后立即异常退出的回归曾使 supervisor 在向已关闭 pipe 写 `stop` 时收到 SIGPIPE。停止协议已改为关闭 stdin 以发送 EOF；supervisor 会清理已退出的 `Process` 后允许调用方显式重启。回归验证异常退出、清理和调用方显式重启；不实现或暗示自动重启/退避。
- 新增 owner 生命周期释放测试：释放最后一个 supervisor 引用后，健康端点不再可访问，证明其 deinit 会停止自己拥有的 FastAPI 子进程。本机 GUI 试验也在服务已连接时退出应用，随后未发现残留 `pac_poc.local_service` 进程；macOS 恢复窗口会按系统设置重新打开 demo，但新实例因缺少环境配置而 fail closed。
- Swift `LocalAPIClient` 仅允许 HTTP `127.0.0.1` / `::1`，使用内存 token，拒绝 HTTP redirect；SwiftUI POC 连接视图只展示状态并提供主动检查按钮。
- API Key POC 使用 macOS Keychain generic-password，`AfterFirstUnlockThisDeviceOnly`；外部可见的凭据管理 API 只提供写入、删除、存在状态查询，不提供明文读取。
- 凭据写入/删除先经过 `LocalAuthentication` 敏感操作授权门；认证策略为 `.deviceOwnerAuthentication`。独立 SwiftUI 系统认证测试区使用同一系统授权器，不调用 `CredentialManagementService` 或 `KeychainCredentialStore`。视图模型现按 `LAError.userCancel`、`LAError.systemCancel` 分别显示用户取消和系统中断；其他认证失败保持 fail closed 状态。fake evaluator 测试覆盖策略/原因传递、系统不可用时 fail closed、系统拒绝向上传递；fake authorizer 回归覆盖成功、普通认证失败、用户取消及系统中断。真实 demo 窗口此前两次认证成功，本次新版 UI 实测用户取消，显示“用户取消了系统认证；未访问钥匙串”。测试路径不访问钥匙串。
- Consent/Policy 只允许精确匹配 Provider、Model、Region、Purpose、数据等级和期限的 grant；无 grant 默认拒绝、L3 永远拒绝，支持撤销。没有实现或调用任何云 Provider。
- 当前 POC 没有数据库 schema 变更；FastAPI/Uvicorn 版本已锁定到 `0.159.1` / `0.54.0`。

## 测试命令

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked pytest -q
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python -m compileall -q pac_poc scripts tests
cd ../poc/macos-audio
swift test
./scripts/run_backend_lifecycle_poc.sh
```

截至 2026-11-08 当前本机验证：Python 全量 151 项通过（当前阶段总基线）；认证状态分类后 `swift test` 31 项通过。Python 覆盖实际 loopback HTTP 服务、Swift CLI → FastAPI 集成和固定 Python 服务模块的 owner pipe 子进程测试；Swift 覆盖 supervisor 子进程失败/显式重启、GUI ViewModel fake 路径、Keychain dummy secret 及认证策略/拒绝行为 fake 测试。网络集成只访问 `127.0.0.1`。

## 未解决/未验收

- SwiftUI demo 已实测一次启动/停止并验证退出清理；已完成两轮连续启停和连接检查；锁屏/休眠场景仍未测试，也不是完整产品 UI。
- LocalAuthentication API 接入已实现，测试按钮和视图模型已构建并在 demo 界面显示；真实系统认证成功两次、用户取消一次均有实机结果，取消状态正确区分并显示；普通认证失败和系统中断由 fake 回归覆盖。测试按钮不会访问钥匙串。
- POC Swift supervisor 已验证本机后端进程所有权、随机端口 handshake、优雅关闭、手动停止后重启、启动超时与非法握手清理、owner deinit 清理及异常退出后的调用方显式重启；未实现异常退出自动重启/退避、锁屏策略、持久化/正式分发 app 运行时配置或面向用户的启动诊断 UI。
- supervisor 的 stderr 当前定向 `/dev/null`，避免将意外服务日志并入普通输出；正式诊断/脱敏日志策略需在产品阶段设计。
- Host/Origin、token 和无云出站策略经过 POC 测试；真实用户 Consent UI、完整数据分类/脱敏/审计与撤销竞态未实现。
- 数据库崩溃/重启、磁盘不足和备份恢复故障注入见独立 `phase0-failure-recovery.md`、`phase0-enospc-recovery.md`；不是本报告的 supervisor/App 故障注入。静态加密方案与 POC 证据见 `phase0-sqlcipher-compat.md`，产品 ADR 仍延期；不得将这些分项证据视为 POC-05 或阶段 0 完成。
- 未验证真实云端 Provider，符合本轮本机使用边界；云请求仍保持不可用/默认拒绝。

## 阶段边界

这是 POC 代码，不是 V1 工程底座。凭据服务内部没有明文读取接口；Tool Gateway、任意 shell/文件访问、连接器、后台任务及 Agent 团队均未加入。ASR、TTS、LLM 仍独立配置。
