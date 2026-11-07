# HANDOFF

## 当前阶段

阶段 0 POC；0B 本地语音实机验证已完成当前可执行项；0C Gateway/Agent Registry/能力注册表模拟已提交；0D 记忆存储/0F SQLCipher 兼容 POC 已提交；0G Embedding 真实模型权重未下载完成；0E 本机安全与 Swift/FastAPI 集成仍有 Touch ID/完整生命周期项；0H SQLCipher 崩溃/页数耗尽注入已提交。阶段 0 尚未验收，阶段 1 未开始。

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
- 开始记忆存储 POC：进程内 SQLite + FTS5、来源/claim/观察时间、纠错版本链、FTS 与 fixture embedding 删除、内存备份恢复；测试 4 项与当前全量 25 项通过。产品 schema 未改动。
- 开始 POC-05 本机安全集成：Keychain 凭据管理 + Touch ID gate、loopback FastAPI/token、Swift URLSession/SwiftUI 状态样例、Consent/Policy 默认拒绝；本机 Swift CLI 对真实 loopback FastAPI 的跨语言冒烟成功，具体测试见 `docs/poc/phase0-security-client.md`。
- 开始 SQLCipher 静态加密兼容性 POC：ARM64/Python 3.12 上 FTS5、错误 key 拒绝、独立密钥加密备份/恢复、SQLAlchemy/Alembic migration upgrade/downgrade 通过；候选尚未定案，详见 `docs/poc/phase0-sqlcipher-compat.md`。
- 建立 FastEmbed 多语言 Embedding 候选接口和测试。真实权重下载停滞并中断；未计算真实向量或检索准确性，详情见 `docs/poc/phase0-local-embedding.md`。
- 开始恢复 POC：在 SQLCipher 临时 DB 上验证未提交事务遇进程立即退出后的恢复，以及页数上限触发数据库错误时 memory/FTS 事务回滚；报告见 `docs/poc/phase0-failure-recovery.md`。
- 建立精确 Provider/Model capability registry POC；未知默认拒绝，支持状态要求证据，报告见 `docs/poc/phase0-model-capability-registry.md`。
- 为本地 ASR 新增测试先行的离线计时与峰值 RSS 测量脚本；使用现存合成 WAV 单次记录 ASR 分帧耗时、RTF、模型加载、进程 RSS 与事件计数。数据写入 `docs/poc/phase0-local-asr.md`，只作观察值，不等于麦克风链路性能验收。
- 建立 `docs/poc/phase0-traceability.md`，按 v1.2 §13/§14 和 V1.1 §16 逐项列出阶段 0 证据、状态、缺口、模块依赖、未决项、后续阶段门禁与风险。矩阵判定阶段 0 未验收，阶段 1 未开始。
- 补强本地 Model Gateway 流式关闭语义：非本地 adapter stream 在调用前拒绝；下游关闭时关闭 adapter async generator。测试先行捕获原有未关闭问题，现已修复并回归。
- 当前最终回归记录：Python（包含 `phase0-security` 与 `phase0-embedding` extras）77 项通过；本机 Swift Testing 13 项通过；`compileall`、`uv lock --check`、本次提交文件的 whitespace 检查通过。ASR 单样本数据及适用范围见 ASR POC 报告。
- 用户澄清本机是软件开发、测试和运行设备，允许下载模型并行进行。Embedding 下载单独进程仍停滞于权重文件；显式设置项目级 HF/XDG cache 和代理后，Python 下载器仍打开 macOS Library HTTP 缓存，现已停止。权重不完整部分保留在 `.poc-data`；将改用受控传输方式后继续下载，不让下载阻塞开发。
- 扩展 Swift↔FastAPI loopback 集成 POC：服务由测试 harness 停止后重新创建，Swift CLI 使用新随机端口/新短期 token 再次健康握手；这不是正式 App 后端子进程管理，真实 App 生命周期仍未验收。
- SQLCipher 恢复 POC 新增真实子进程 `SIGKILL` 注入：在事务写入后、提交前强制杀进程，再开启 DB 验证已提交行、未提交 memory/FTS 行和 `integrity_check`；恢复测试只覆盖默认 rollback journal，不代表断电/WAL。
- 同一 SIGKILL 恢复用例现分别在 SQLite DELETE journal 与 WAL 模式下运行通过；WAL checkpoint、断电和真 ENOSPC 仍未覆盖。
- SQLCipher 备份 POC 增加目标父路径不可创建的故障测试。测试先发现 `mkdir` 异常会穿透 POC API，现统一转为不含敏感信息的安全错误；源数据库查询和完整性仍通过。未模拟真实介质故障。
- 用户澄清“本机”指软件在本机开发、测试、运行，不排除后续本机客户端连接云 Provider；已据此修正阶段追踪矩阵。新建 Gateway `ConsentAwarePolicy` 工作包：对远端 generate/stream 默认拒绝，只有精确有效 Consent/Policy 才会调用 adapter；所有验证使用 fake adapter，不发网络请求。报告见 `docs/poc/phase0-consent-aware-gateway.md`。
- 在工具调用始终不执行的前提下，新增 Ollama Gateway `call_with_tools` 契约与固定本机合成 probe。`qwen3.5:0.8b` 实际返回 `lookup(key=phase0-probe)`，已将精确型号/基础 tools 能力更新为有单次证据；不推断并行工具或严格 JSON Schema。
- 多语言 Embedding 候选权重已分段落在项目 `.poc-data/embedding-staging` 并逐个校验大小和 SHA-256；固定 revision ONNX、tokenizer、unigram 总体完整。最后一个 20 MB 分段的 curl 重试会回退长度，已保留失败尝试供审计，改用 20 个 1 MB 独立段完成。模型在项目 FastEmbed cache 本地加载，两次 4-query 合成检索均 top-1 命中 4/4；`HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` 下再次加载通过。两次 `/usr/bin/time -l` 最大 RSS 为 851,804,160 与 868,909,056 bytes；这是小样本单次进程观察，不代表产品性能。完整证据和未决项见 `phase0-local-embedding.md`。
- 按 v1.2 §POC-02 / V1.1 §4.5 完成 LiteLLM、Bifrost、Portkey 第一方资料对照报告与文档契约测试；仅桌面资料评估，没有安装 Gateway 或云端调用。ADR-020 仍 Deferred；报告明确本项目 Consent Manager/Policy Engine 默认拒绝、Keychain 凭据和 L3 隔离不可由候选 Gateway 代替。
- 依 FR-SEC-006 修正敏感操作认证策略：由仅 biometric-only 改为 LocalAuthentication `.deviceOwnerAuthentication`（Touch ID 或设备密码）；先添加策略回归测试，验证通过。未触发真实系统提示；旧 `touchIDUnavailable` 错误 case 保留兼容，当前不可用路径抛出通用 `authenticationUnavailable`。

## 当前限制

- ASR 仅在当前中文模型上验证；本机麦克风已实测可录音。多语言模型由用户安排后续补充，不属于当前代码 bug；不得静默改用云 ASR。
- 尚未验证 SwiftUI 麦克风链路、中英混合识别质量、P50/P95、资源占用、AEC、TTS 与 ASR 同时工作和锁屏/休眠处理。
- 目前仅有合成短音频单次 ASR 性能观测；真实麦克风端到端延迟、重复样本分布与可确认性能阈值仍未验证/未决。
- Gateway 的真实远程 Provider/能力矩阵/费用/错误/fallback 对照未开始，需在本地客户端连接外部服务时经 Consent/Policy、Keychain 和合成数据逐项测试；POC-05 真实 Touch ID、完整 App 生命周期/握手未验证；POC-06 尚未评估密钥生命周期、WAL checkpoint、真实 ENOSPC/断电、备份介质故障和性能，也未作 ADR。记忆 POC 尚未评测真实本地 Embedding。
- 所有产品待决策项继续保持未定；本地 ASR 模型是临时 POC 候选。

## 下一步

继续阶段 0：收尾 POC-01/02/05/06/0G/0H。多语言 ASR 按用户安排留待后续模型补充；当前不当作代码 bug。Gateway 对照报告已完成桌面资料比较，真实 Provider/Gateway 实测尚缺；本机软件可连接云 Provider，但每个出站请求仍必须经 Consent Manager 与 Policy Engine，默认拒绝；凭据只经 Keychain。Embedding 候选已在本机离线推理，但真实检索集、资源目标与产品模型选择未验收。阶段 0 验收前不得进入阶段 1。

## 交接要求

后续每阶段完成或中断时更新本文件，并在报告中列修改文件、设计、测试命令与结果、未决项和验收对照。
