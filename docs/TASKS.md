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
| 0A | 仓库审计与基线 | IN PROGRESS | 已新增根 README、AGENTS、macOS arm64 CI workflow；本机等价 Python/Swift 回归通过。仓库没有 Git remote，首次 GitHub Actions 运行仍待验证。 |
| 0B | 本地语音链路 | IN PROGRESS | 在 SwiftUI 链路完成真实麦克风的 partial/final、停止/异常清理与 TTS 打断验证；记录重复轮次和性能。目标阈值待 D-013；多语言 ASR 按 C-003 延后；当前中文权重的许可条款仍需从授权页面核验。 |
| 0C | Gateway、能力注册、Agent 模拟 | IN PROGRESS | 本机 Ollama 与模拟接口已有证据。D-010 按用户要求延期，用户将另提供 Provider 组合；在供应商和区域明确、凭据经 Keychain 配置且 Consent/Policy 明确放行前，不发送远端请求。 |
| 0D | 记忆存储 | IN PROGRESS | 内存 SQLite/FTS 与派生索引 POC 已完成；补真实标注检索集、模型重建/崩溃覆盖和产品 schema 决策。持久化产品实现留待阶段 1/后续阶段门禁。 |
| 0E | Swift、Loopback、Keychain、Consent | IN PROGRESS | POC demo 启停和退出清理已有实机证据；补真实系统认证提示、锁屏/休眠、多轮 GUI、正式分发与恢复策略证据。 |
| 0F | 静态加密兼容性 | IN PROGRESS | SQLCipher 已有 ARM64、FTS、迁移和恢复证据；完成密钥生命周期、产品性能及发布形态评估，形成 ADR-019 决定。 |
| 0G | Embedding 候选 | IN PROGRESS | 固定候选已离线推理三次，均为 4/4 合成 query top-1；observed max RSS 883,130,368–883,490,816 bytes；模型卡/运行包许可初核见 `poc/phase0-model-license-review.md`。补真实标注检索集、完整依赖 SBOM 和产品选择（D-014）。 |
| 0H | 故障注入与性能 | IN PROGRESS | 已测 WAL 备份的活动 reader + 三次 writer 提交、checkpoint 等待读锁期间 SIGKILL 后恢复、备份复制在 DELETE/WAL 下 SIGKILL、HFS+ 与 APFS 有界映像 ENOSPC；新增 `os.replace` 调用前/成功返回后的 SIGKILL 边界测试。边界测试不代表系统调用内部中断或断电持久性；备份目标 ENOSPC、实际外接介质/产品 WAL 生命周期与 staging 清理规则仍待处理。 |
| 0I | 阶段追踪与验收 | OPEN | D-001–D-015 与 ADR-019/020/021/022 已按用户要求标记延期（D-010 的 Provider 组合待用户另行提供）。延期不豁免规格要求的 POC 证据；GitHub Actions 真实运行、语音/认证验收、许可与恢复边界等仍有缺口，完成证据审查后才能签收。 |

## 近期执行队列

1. **继续 0H：原子替换边界恢复审查。** 子进程在 `os.replace` 调用前 SIGKILL 后旧备份有效；在调用成功返回后 SIGKILL，新备份有效；两种情况下源库完整。没有声称系统调用内部中断或断电持久性。下一步审查恢复结果并同步报告；真实活动卷/外接介质故障需单独设计和记录。
2. **可本机继续：0E supervisor 异常退出路径。** 现有策略是异常退出后显式由调用方重启；需对照规格梳理调用方 GUI、退出清理与错误提示证据。自动重启/退避和锁屏策略若无产品决定，保持 OPEN。
3. **需设备操作：0B SwiftUI 真实麦克风验收。** 需要用户实际多轮说话、停止/异常清理与 TTS 打断；D-013 的性能阈值由产品负责人确认。中文当前模型继续使用，多语言 ASR 按 C-003 延后。
4. **需许可条款：0B 中文 ASR 权重分发。** 上游模型页要求接受访问条件，公开页面无条款；需授权账号下人工查看并归档许可/再分发条件，或选择其他许可清晰模型。
5. **需用户提供组合及凭据授权：0C 真实远端 Provider/Gateway。** 用户已表示会另提供组合；名单/区域确定后，才可用合成输入和 Keychain 凭据逐家验证，并在每次请求前通过 Consent/Policy。
6. **已延期产品输入：0F/0G。** ADR-019 与 D-014 已按用户要求延期；如要恢复决策，仍需真实标注记忆/query 语料、资源目标及安全/许可证据。

## 阶段门禁

- 阶段 0 必需验收、报告和未决事项状态以规格书 §13、§14 与追踪矩阵为准。
- 只有阶段 0 签收并确认关键 ADR/产品决策后，才开始阶段 1。
- 每个工作包关闭时，将结果、修改文件、验证命令与结果、剩余风险写入对应 POC 报告；同步更新追踪矩阵、本文件和 `HANDOFF.md`，并提交 Git。
