# 阶段任务清单

最后核对：2026-11-08（Asia/Shanghai）

## 状态和流程

- `DONE`：工作包的明确完成条件已满足，证据可复核。
- `IN PROGRESS`：正在执行，尚有明确完成条件未满足。
- `OPEN`：可继续推进，尚未开始或证据不足。
- `BLOCKED`：依赖产品决定、用户操作、凭据或外部条件；记录解除阻塞所需输入。
- `DEFERRED`：按用户或基线范围暂缓，不作为当前缺陷。

执行顺序：开始前读取根目录 `AGENTS.md`（如存在）、`PROJECT_CONTEXT.md`、`TASKS.md`、`DECISIONS.md`、`HANDOFF.md`；检查 Git 状态；按下面的顺序选取未阻塞任务；实现后执行适用验证、更新 POC 报告与追踪矩阵、更新本清单和交接文档，最后提交 Git。不得因任务清单中的 POC 把阶段 1 提前启动。

阶段 0 的验收证据详情以 [追踪矩阵](poc/phase0-traceability.md) 为准；本清单负责执行排程和下一步。

## 阶段 0 工作包

| 顺序 | 工作包 | 状态 | 下一步 / 完成条件 |
|---:|---|---|---|
| 0A | 仓库审计与基线 | IN PROGRESS | 已新增根 README、AGENTS、macOS arm64 CI workflow；最新本机 Python 151 项、Swift 29 项回归通过。仓库没有 Git remote，首次 GitHub Actions 运行仍待验证。 |
| 0B | 本地语音链路 | IN PROGRESS | 官方中英 Streaming Zipformer 文件分帧 10/10 final、82 partial、weighted CER 0.0254；用户已完成三次真实 CLI 麦克风采集并看到 partial/final；另一次麦克风未打开时按 Ctrl-C 正常停止。用户将当前目标限定为功能冒烟，识别质量转为后续模型选择/优化项；识别器异常与模拟用户中断时 stream context 均关闭、缓冲清空已有 mock 回归；真实设备 Ctrl-C 停止路径已有一次记录。新增 ASR-final→AVSpeechSynthesizer 合成链路，3 条 WAV 共 5/5 完成；仍不代表独立真人语料或长时稳定性。按规格书 §13，SwiftUI 麦克风/AEC 属阶段 3，不作 0B 门禁；本机 ASR+LLM 并发已有四轮同样本观察。真实驱动异常和多负载资源评估作补证；Qwen 云 ASR/云 TTS 未测试且受 D-011 延期约束；中英 Streaming Zipformer 模型仓库声明 Apache-2.0，但上游标识不一致、训练数据权利链未核验；原中文模型与 Qwen 转换包许可仍待核。 |
| 0C | Gateway、能力注册、Agent 模拟 | IN PROGRESS | DeepSeek 与 OpenRouter 文本、同一 Gateway 顺序路由、两家各一次真实 SSE 均通过；DeepSeek 与 OpenRouter 工具提案实测成功且均未执行；OpenRouter 在前两次空结果后，第三次返回正确 proposal（tool_calls、Relace/HKG）。OpenRouter JSON 一次结构匹配成功（Relace/HKG）；DeepSeek JSON 三次结果为一次空正文、两次结构匹配成功（后两次 finish_reason=stop，tokens=68/46/114 与 68/28/96）；成功请求证明该次 API Key 被接受。适配器会对 401 明确提示 Key 认证失败，并分类 402 余额、403 权限、429 限流；error probe 仅将 400/422 作为无效请求路径通过。两家客户端 SSE 取消均已实测收到首片段后关闭流，Provider 是否停止生成/计费未知；OpenRouter metadata 两次均精确匹配并返回 Relace/HKG（cost USD 0.000008752、0.000008252）；DeepSeek metadata 两次已观察：一次 ACK 不匹配、一次匹配；两次均未返回 downstream Provider/区域/费用，首次正文未被旧 CLI 捕获。本轮 deny-check 两家均为 Keychain reads=0、HTTP calls=0（进程内 tripwire）；真实 HTTPX 无 Consent harness 对两家均在 Adapter 前拒绝、credential reads=0；PID 级 lsof 观察无活动网络 socket（loopback 正向对照可见）。本次全局 tcpdump 虽见 546 个包但未按进程过滤，不能归因给测试进程；lsof 是活动 socket 快照，不是完整包级证明。详见 `poc/phase0-remote-provider.md`。 |
| 0D | 记忆存储 | IN PROGRESS | 内存 SQLite/FTS 与派生索引 POC 已完成；补真实标注检索集、模型重建/崩溃覆盖和产品 schema 决策。持久化产品实现留待阶段 1/后续阶段门禁。 |
| 0E | Swift、Loopback、Keychain、Consent | IN PROGRESS | POC demo 启停和退出清理已有实机证据；已新增显式系统认证测试按钮，真实 demo 窗口已显示认证成功且未访问钥匙串；两轮 GUI 停止/启动/健康检查完成，进程数符合预期；用户取消/拒绝路径、锁屏/休眠、正式分发与异常恢复策略证据仍待补。 |
| 0F | 静态加密兼容性 | IN PROGRESS | SQLCipher 已有 ARM64、FTS、迁移和恢复证据；完成密钥生命周期、产品性能及发布形态评估，形成 ADR-019 决定。 |
| 0G | Embedding 候选 | IN PROGRESS | 固定候选已离线推理三次，均为 4/4 合成 query top-1；observed max RSS 883,130,368–883,490,816 bytes；Python 锁定依赖 CycloneDX SBOM 已覆盖 54/54 个包，见 `poc/phase0-python-sbom.md`。补许可证闭包、真实标注检索集和产品选择（D-014）。 |
| 0H | 故障注入与性能 | IN PROGRESS | 已测 WAL 备份的活动 reader + 三次 writer 提交、checkpoint 等待读锁期间 SIGKILL 后恢复、备份复制在 DELETE/WAL 下 SIGKILL、HFS+ 与 APFS 有界映像 ENOSPC；新增 `os.replace` 调用前/成功返回后的 SIGKILL 边界测试。边界测试不代表系统调用内部中断或断电持久性；备份复制路径的确定性 ENOSPC 注入已通过且旧备份/源库保全；真实备份目标满载仍未实测。实际外接介质/产品 WAL 生命周期与崩溃后 staging 清理规则仍待处理。 |
| 0I | 阶段追踪与验收 | OPEN | D-001–D-015 与 ADR-019/020/021/022 已按用户要求标记延期（D-010 候选及区域已明确，V1 选型仍延期）。延期不豁免规格要求的 POC 证据；GitHub Actions 真实运行、ASR/TTS 稳定链路及独立语料/负载资源证据、Provider 服务端取消/稳定性、许可及恢复边界等仍有缺口；SwiftUI 麦克风/AEC 属阶段 3，完成证据审查后才能签收。 |

## 近期执行队列

1. **本机已完成：0H 原子替换边界恢复审查。** 调用 `os.replace` 前 SIGKILL 保留旧备份，成功返回后 SIGKILL 保留新备份，两条路径源库均完整；不覆盖 syscall 内部中断或断电持久性。报告和测试已记录。
2. **本机已完成：0E supervisor 异常退出路径审查。** 子进程握手后异常退出时能清理并由调用方显式重启；GUI 启停与退出清理已实测。真实系统认证成功和两轮 GUI 启停已记录；用户取消/拒绝认证、自动重启/退避、锁屏/休眠及正式分发仍缺证据或决策，见安全客户端报告。
3. **0B 语音功能冒烟已取得用户实机证据。** 两次主动采集均产生 partial/final；用户决定将当前识别质量留待后续模型选择，不作为本轮功能冒烟阻断项。按规格书 §13，SwiftUI 麦克风/AEC 在阶段 3，不作为 0B 关闭条件。阶段 0 的后续核对聚焦 ASR/TTS 稳定链路报告与资源证据；真实驱动异常为稳健性补证，D-013 数值目标继续延期。
4. **0B 语音链路补证。** 合成样本上的“ASR final → AVSpeechSynthesizer 播放”已覆盖 3 条样本、共 5/5 完成并归档；下一步补独立真人语料/长时运行与资源覆盖。原中文 ASR 权重许可仍未核；双语 Streaming Zipformer 的仓库声明 Apache-2.0，但来源标识与训练数据权利链未独立核实；Qwen ONNX 转换包许可也未核。不得据此自动选定产品模型或分发方案。
5. **0C DeepSeek 工具提案已实测通过。** 用户重新确认显式关闭 thinking 后的完整请求，DeepSeek 返回合成函数提案，未执行。DeepSeek 空 JSON 的原因仍未知，不能由单次空正文认定为 Key 错误；新增 HTTP 状态分类与本地回归。继续处理 Provider 侧取消证据及其他 0C 缺口，每条外发请求仍需独立确认。
6. **产品决策继续延期：0F/0G 及规格 D 项。** ADR-019 与 D-014 等照用户要求保持延期；这不关闭对应证据缺口，也不允许开始阶段 1。

麦克风复现命令（从仓库根目录，在本机交互式终端运行）：

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache uv run --locked python scripts/run_live_microphone_poc.py .poc-data/models/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20 --seconds 30
```

## 阶段门禁

- 阶段 0 必需验收、报告和未决事项状态以规格书 §13、§14 与追踪矩阵为准。
- 只有阶段 0 签收并确认关键 ADR/产品决策后，才开始阶段 1。
- 每个工作包关闭时，将结果、修改文件、验证命令与结果、剩余风险写入对应 POC 报告；同步更新追踪矩阵、本文件和 `HANDOFF.md`，并提交 Git。
