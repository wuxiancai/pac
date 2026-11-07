# HANDOFF

> 文档入口：稳定项目约束见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)，已确认/待决选择见 [DECISIONS.md](DECISIONS.md)，阶段任务与下一步见 [TASKS.md](TASKS.md)，阶段证据见 [追踪矩阵](poc/phase0-traceability.md)。本文件仅作为最近交接摘要；避免在这里重复维护完整任务和决策清单。

最近更新：2026-11-07（Asia/Shanghai）

## 最近交接（2026-11-07）

- 建立 `PROJECT_CONTEXT.md`、`DECISIONS.md`、`TASKS.md` 文档入口；阶段 0 证据权威来源仍是 `poc/phase0-traceability.md` 和各 POC 报告。
- 继续 0H：新增 SQLCipher WAL 备份逐页复制期间的独立 writer 注入。writer 在 progress callback 中提交 memory/FTS 后，源库与恢复备份均含并发提交和已有记录，完整性检查通过。专项回归 `uv run --extra phase0-security --group dev pytest -q tests/test_sqlcipher_compat_poc.py`：16 passed。
- 本轮修改：`docs/PROJECT_CONTEXT.md`、`docs/DECISIONS.md`、`docs/TASKS.md`、`docs/HANDOFF.md`、`docs/poc/phase0-failure-recovery.md`、`docs/poc/phase0-traceability.md`、`backend/tests/test_sqlcipher_compat_poc.py`。
- 继续顺序：0H 活动 reader/持续 writer 下备份；staging 遗留清理规则待产品决定；随后完成 0B/0E/0F/0G 的证据和决策门禁。阶段 0 未验收，阶段 1 未开始。

## 当前阶段

阶段 0 POC；0B 本地语音实机验证已完成当前可执行项；0C Gateway/Agent Registry/能力注册表模拟已提交；0D 记忆存储/0F SQLCipher 兼容 POC 已提交；0G 候选权重已下载并离线评测，但产品选择/真实检索集未验收；0E SwiftUI demo 已接入 supervisor 并实测启动/握手/停止/退出清理，真实认证、异常自动恢复/退避和正式分发仍待验收；0H SQLCipher 崩溃/页数耗尽/WAL 恢复与备份故障注入持续补证。阶段 0 尚未验收，阶段 1 未开始。

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

- ASR 仅在当前中文模型上验证；本机麦克风已实测可录音。多语言模型由用户安排后续补充，不属于当前代码 bug；不得静默改用云 ASR。
- 尚未验证 SwiftUI 麦克风链路、中英混合识别质量、P50/P95、资源占用、AEC、TTS 与 ASR 同时工作和锁屏/休眠处理。
- ASR 资源测量已对同一条合成 WAV 做 3 次独立进程重复，但没有独立语料或实时麦克风端到端统计；重复样本分布和可确认性能阈值仍未验证/未决。
- Gateway 的真实远程 Provider/能力矩阵/费用/错误/fallback 对照未开始，需在本地客户端连接外部服务时经 Consent/Policy、Keychain 和合成数据逐项测试；POC-05 真实系统认证提示、异常自动恢复/退避、锁屏/休眠策略和正式分发仍未验证，SwiftUI demo 的进程握手/启停/退出清理已通过；POC-06 尚未评估密钥生命周期、APFS/外接介质 ENOSPC、断电/checkpoint 执行中断、备份介质故障和产品性能，也未作 ADR。记忆 Embedding 只接入 disposable 内存 repository，产品 schema 与真实检索质量仍未验收。
- 所有产品待决策项继续保持未定；本地 ASR 模型是临时 POC 候选。

## 下一步

继续阶段 0：收尾 POC-01/02/04/05/06/0G/0H。多语言 ASR 按用户安排留待后续模型补充；当前不当作代码 bug。Gateway 对照报告已完成桌面资料比较，真实 Provider/Gateway 实测尚缺；本机软件可连接云 Provider，但每个出站请求仍必须经 Consent Manager 与 Policy Engine，默认拒绝；凭据只经 Keychain。Embedding 候选已集成至可注入的内存记忆 POC 并在本机离线合成检索，但真实检索集、资源目标、持久化迁移与产品模型选择未验收。备份 staging 经校验后原子替换目标，真实子进程备份期间 SIGKILL 后旧备份/源数据恢复通过；崩溃 staging 清理策略、原子替换中断、断电和介质故障仍未验证。阶段 0 验收前不得进入阶段 1。

## 交接要求

后续每阶段完成或中断时更新本文件，并在报告中列修改文件、设计、测试命令与结果、未决项和验收对照。
