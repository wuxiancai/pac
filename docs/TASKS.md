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
| 0A | 仓库审计与基线 | IN PROGRESS | 已新增根 README、AGENTS、macOS arm64 CI workflow；本机 Python 129 项、Swift 27 项回归通过。仓库没有 Git remote，首次 GitHub Actions 运行仍待验证。 |
| 0B | 本地语音链路 | IN PROGRESS | 除 Qwen3 离线候选外，官方中英双语 Streaming Zipformer 已对 10 条本机合成中英/混说音频完成 200 ms 分帧测试（10/10 final、82 partial、weighted CER 0.0254）。下一步由用户实际参与麦克风多轮 partial/final、停止/异常清理测试；Qwen ONNX 转换包许可仍待核，性能目标暂缓。 |
| 0C | Gateway、能力注册、Agent 模拟 | IN PROGRESS | 本机 Ollama 与模拟接口已有证据。D-010 按用户要求延期，用户将另提供 Provider 组合；在供应商和区域明确、凭据经 Keychain 配置且 Consent/Policy 明确放行前，不发送远端请求。 |
| 0D | 记忆存储 | IN PROGRESS | 内存 SQLite/FTS 与派生索引 POC 已完成；补真实标注检索集、模型重建/崩溃覆盖和产品 schema 决策。持久化产品实现留待阶段 1/后续阶段门禁。 |
| 0E | Swift、Loopback、Keychain、Consent | IN PROGRESS | POC demo 启停和退出清理已有实机证据；补真实系统认证提示、锁屏/休眠、多轮 GUI、正式分发与恢复策略证据。 |
| 0F | 静态加密兼容性 | IN PROGRESS | SQLCipher 已有 ARM64、FTS、迁移和恢复证据；完成密钥生命周期、产品性能及发布形态评估，形成 ADR-019 决定。 |
| 0G | Embedding 候选 | IN PROGRESS | 固定候选已离线推理三次，均为 4/4 合成 query top-1；observed max RSS 883,130,368–883,490,816 bytes；模型卡/运行包许可初核见 `poc/phase0-model-license-review.md`。补真实标注检索集、完整依赖 SBOM 和产品选择（D-014）。 |
| 0H | 故障注入与性能 | IN PROGRESS | 已测 WAL 备份的活动 reader + 三次 writer 提交、checkpoint 等待读锁期间 SIGKILL 后恢复、备份复制在 DELETE/WAL 下 SIGKILL、HFS+ 与 APFS 有界映像 ENOSPC；新增 `os.replace` 调用前/成功返回后的 SIGKILL 边界测试。边界测试不代表系统调用内部中断或断电持久性；备份目标 ENOSPC、实际外接介质/产品 WAL 生命周期与 staging 清理规则仍待处理。 |
| 0I | 阶段追踪与验收 | OPEN | D-001–D-015 与 ADR-019/020/021/022 已按用户要求标记延期（D-010 的 Provider 组合待用户另行提供）。延期不豁免规格要求的 POC 证据；GitHub Actions 真实运行、语音/认证验收、许可与恢复边界等仍有缺口，完成证据审查后才能签收。 |

## 近期执行队列

1. **本机已完成：0H 原子替换边界恢复审查。** 调用 `os.replace` 前 SIGKILL 保留旧备份，成功返回后 SIGKILL 保留新备份，两条路径源库均完整；不覆盖 syscall 内部中断或断电持久性。报告和测试已记录。
2. **本机已完成：0E supervisor 异常退出路径审查。** 子进程握手后异常退出时能清理并由调用方显式重启；GUI 启停与退出清理已实测。自动重启/退避、锁屏/休眠、真实系统认证提示仍缺证据或决策，见安全客户端报告。
3. **需用户参与：0B 双语实时麦克风验收。** 请在本机交互终端运行下方命令，看到隐私提示后按回车启动；朗读程序提示的中英句子，结束时按 Ctrl-C，并把 JSON 事件或错误信息发回。该流程只在你按回车后打开麦克风，不保存音频文件。D-013 性能阈值继续延期。
4. **需许可条款：0B 中文 ASR 权重分发。** 原中文候选上游要求接受访问条件，公开页面未展示许可；可提供获准账号所见许可文本供记录，或明确只采用官方双语 Apache-2.0 候选，后者仍需真人语音验证。
5. **需用户提供组合：0C 真实远端 Provider/Gateway。** 请给至少两家 Provider 与区域。之后将凭据放入 macOS Keychain；每家仅使用合成输入，经 Consent/Policy 明确放行后各发一次请求。当前未读凭据、未发请求。
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
