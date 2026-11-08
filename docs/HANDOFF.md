# HANDOFF

> 文档入口：稳定项目约束见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)，已确认/待决选择见 [DECISIONS.md](DECISIONS.md)，阶段任务与下一步见 [TASKS.md](TASKS.md)，阶段证据见 [追踪矩阵](poc/phase0-traceability.md)。本文件仅作为最近交接摘要；避免在这里重复维护完整任务和决策清单。

最近更新：2026-11-08（Asia/Shanghai）

## 最近交接

### 2026-11-08：OpenRouter 工具探测诊断增强

- 用户在保持 `provider.require_parameters=true`、`allow_fallbacks=false` 的配置下再次确认 OpenRouter 工具探测；结果仍为 `工具调用提案（未执行）: []` 与空模型文本。此请求发生在 finish_reason/路由诊断输出加入前，故上游返回形态和原因仍未知。
- 为下一次可复核探测，`ToolCallResult` 现传递 finish_reason、model，以及 OpenRouter metadata 中选中的 downstream Provider/region；CLI 会展示这些字段。工具仍仅作为数据展示、不执行。
- 本地 MockTransport 回归覆盖 OpenRouter 成功响应的这些 metadata 字段；窄回归 31 项、全量 Python 142 项、compileall、uv lock --check 与 git diff --check 均通过。下一步可由用户再次逐项确认 OpenRouter tools，以取得诊断字段；阶段 0 仍未验收。

### 2026-11-08：0C Provider 能力探测工具

- 新增 `backend/scripts/probe_provider_capability_poc.py`，按 Provider/能力单次运行，覆盖 streaming、强制工具提案（不执行）、JSON、故意触发 4xx、重复 metadata，以及无授权 deny-check。每个真实 HTTP 请求都需要单独输入精确确认；故意错误请求可能计费。
- Adapter 新增显式 `tool_choice` 透传。窄回归 31 项通过；deny-check tripwire 结果为 Keychain reads=0、HTTP transport calls=0。该结果不是系统级抓包。用户随后完成 DeepSeek 与 OpenRouter 各一次真实 SSE 探测，拼接响应均精确匹配 `phase0-probe-ack`；DeepSeek tool proposal 成功，OpenRouter 首次没有返回提案，已增加受支持参数路由过滤并等待复测。
- DeepSeek 首次工具请求返回 HTTP 400，正文未保留。按 DeepSeek 官方说明，默认 thinking mode 与指定 tool_choice 不兼容的推断已被落实为工具请求显式关闭 thinking；用户重新确认后获得正确的合成 `phase0_echo_synthetic` 提案，未执行工具。下一项为 OpenRouter tools。
- OpenRouter 工具探测经确认后返回空 proposal list，未显示普通文本，端点 metadata 也未包含在工具结果中，原因尚未确认。根据 OpenRouter 文档，部分不支持工具的上游会忽略 tools 字段；已添加 `provider.require_parameters=true`（仍禁用 fallback）及空提案文本诊断，等待重新授权复测。
- 复现命令、payload、确认短语及未决限制见 `poc/phase0-remote-provider.md`。

### 2026-11-08：0C 同一 Gateway 双 Provider 路由

- 新增 `backend/scripts/probe_provider_switch_poc.py`：同一 ModelGateway 注册 DeepSeek 与 OpenRouter 两个固定 adapter，逐家展示合成请求并要求独立精确确认；拒绝或失败不触发自动 failover。
- 新增 MockTransport 回归证明双路由端点和对应 Keychain account 均按 Provider 选择；窄回归 29 项通过，脚本 compileall 通过。用户之后已分别确认并完成真实顺序路由，两家均精确匹配；OpenRouter 返回 Relace/HKG。该路径不代表自动 fallback；更广能力矩阵仍待验证，见 `poc/phase0-remote-provider.md`。
- 更新后全量 Python 回归 **140 passed**。阶段 0 仍未验收；真实 SSE/工具/JSON/错误能力、其他阶段缺口和延期决策仍需按矩阵处理。

### 2026-11-08：0G Python 依赖 SBOM

- 从锁文件导出 CycloneDX 1.5 SBOM，覆盖所有 54 个 Python 锁定依赖（包括所有 extras 与 dev 组），并核对 BOM 的 `(name, version)` 集合与 `uv.lock` 完全一致。复现步骤、SHA-256 和范围限制见 `poc/phase0-python-sbom.md`。
- uv 导出的组件未包含许可证字段；54 个锁定 Python 包现均有 metadata、随包 LICENSE 或对应 PyPI 精确版本页的初步许可证线索。完整许可证范围/通知审查、模型权重许可、真实标注记忆检索集和 D-014 模型决定仍未完成。

### 2026-11-08：两家 Provider 实测与本地语音功能复测

- 用户在每条命令中分别输入精确确认短语后，DeepSeek 与 OpenRouter 各完成一次 L1 合成文本请求，均返回 `phase0-probe-ack`。DeepSeek：`deepseek-flash`，prompt/completion/total=42/41/83，服务未返回 downstream Provider、region 或 cost。OpenRouter：`deepseek/deepseek-v4.1-flash-1017`，下游 `Relace` / `HKG`，token=42/17/59，cost USD 0.000008752。报告见 `poc/phase0-remote-provider.md`。
- 用户另运行 30 秒双语麦克风 CLI，观察到多个 partial 和一个 final。用户指定本轮 ASR 验证以链路功能为准，识别质量留待后续模型选择/优化；该轮不计 CER。测试仍未覆盖 SwiftUI 采集、停止/异常清理、性能和多轮稳定性。
- `cd backend` 因用户终端已经位于 backend 目录而报错，之后运行的脚本命令仍成功。

### 2026-11-08：阶段追踪记录与最新 Provider 证据对齐

- 将 D-010 保持为 V1 Provider 选型待决，同时把两家实际合成文本调用记录到阶段追踪；更新 Consent/Policy 真实路径证据与 Python 139 项最新回归数。阶段 0 仍有明确缺口，不能签收。

### 2026-11-08：首次双语麦克风实测与 Provider 组合输入

- 用户主动运行官方中英 Streaming Zipformer 麦克风 CLI，回报多个 partial、两个 final。混合中文/英语话语出现可见错词，第二段英语也未稳定识别；无逐字 ground truth，未算 CER。该轮只作为一次真实设备观察，原始音频未保存。复测要求见 `poc/phase0-local-asr.md` 和 `TASKS.md`。
- 用户给出两家 Provider 候选：DeepSeek、OpenRouter，并确认 DeepSeek 按中国处理、OpenRouter 选 Global。官方隐私/区域资料与模型 id 见 `poc/phase0-remote-provider.md`。
- 已向用户说明不要把 API Key 发到聊天。新实现固定 Keychain service `com.personal-ai-assistant.phase0.provider`，account 分别为 `deepseek`、`openrouter`；每次请求须先由用户在本机 CLI 输入精确确认语句，ConsentAwarePolicy 放行后才从 Keychain 读取并发送。
- 用户命令开头的 `cd backend` 报错只因其已位于 `backend` 目录；后续相对路径命令实际成功运行并启动麦克风捕获。

### 2026-11-08：DeepSeek / OpenRouter 一次性探测实现

- 新增固定 URL/model/region 的 OpenAI chat-completions adapter、macOS `/usr/bin/security` Keychain reader 和 `scripts/probe_remote_provider_poc.py`。每次运行最多发一个 L1 合成文本请求；不重试、不 fallback、不执行模型工具。正确的逐次确认短语后才会生成 60 秒精确 Consent，策略通过后才读取 Keychain；拒绝路径在本机验证无 Keychain 读取/网络请求。
- MockTransport 验证默认拒绝、文本请求、SSE、工具调用数据（不执行）、`response_format`、OpenRouter provider failover 关闭、选定 Provider/region/token/cost metadata、端点/model/region allowlist 和 HTTP 错误脱敏。局部测试 28 项，全量 Python 139 项，Swift 27 项通过；`compileall` 与 `uv lock --check` 通过。
- 用户还未把 API Key 保存到 Keychain，故没有真实 Provider 请求。下一步按 `poc/phase0-remote-provider.md` 创建两项登录钥匙串记录，然后由用户分别在 `deepseek` 与 `openrouter` CLI 探测提示中输入授权短语。阶段 0 仍未验收。
- 用户随后已分别运行两家探测并输入对应确认短语；两次均返回 `provider credential is missing or unavailable in Keychain`。查询未取得密钥，因此无 HTTP 请求。下一步核对 login 钥匙串“通用密码”项的 service/account 与报告完全一致；具体结果写入 `poc/phase0-remote-provider.md`。
- 用户之后提供截图；本机只读元数据查询确认两个账户名与 service 在 login 钥匙串匹配（未读取密钥值）。用户报告 DeepSeek 一次合成请求成功；OpenRouter 因账户余额不足的判断按用户要求记为预期失败，但原因未独立核验。后续仍需 OpenRouter 成功探测证据；阶段 0 未验收。

### 2026-11-08：双语流式 ASR 分帧评估与评分修正

- 官方 sherpa-onnx `sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20` 已下载至忽略目录 `backend/.poc-data/models/`。包内 README 声明 Apache-2.0；模型页、来源和四个关键文件 SHA-256 记录在 `poc/phase0-local-asr.md`。
- 使用项目 streaming adapter 按 200 ms 输入 8 条 Tingting 中文、1 条 Samantha 英语、1 条中英混说合成 WAV，尾部追加 3 秒静音：10/10 final、82 partial、weighted CER 0.0254。小型合成样本只证明适配器文件分帧路径可运行；真实麦克风及 SwiftUI 流程仍需用户操作。
- 修复 CER 对英语大小写敏感的问题，并修复多段 final 只评分最后一段的问题；ASR 评测回归 8 项通过，Python 全量 129 项、Swift 27 项通过。
- 下一步由用户按固定中英短句重复麦克风测试；其余阶段缺口与门禁以 `poc/phase0-traceability.md`、`TASKS.md` 为准。阶段 0 未验收。

### 2026-11-08：0E/0H 交接记录去重与差异核对

- 对照实现、报告与当前回归，清理了 0E 报告中的陈旧说法：SwiftUI demo 启停和退出清理已有一次实机证据；supervisor 异常退出后由调用方显式重启已有集成回归；DB 崩溃/ENOSPC 恢复证据在独立报告，不再写成“未做”。自动重启/退避、锁屏/休眠、真实系统认证提示及正式分发策略仍未验收。
- `TASKS.md` 将已经有证据的 0H 原子替换审查和 0E supervisor 异常退出审查标为本机已完成，避免重复排队；增加了用户可执行的本机麦克风命令和当前外部输入清单。
- 阶段 0 仍待用户亲自开始麦克风采集、提供 Provider 名称/区域，及必要的许可/产品证据；没有运行云请求或启动录音。最新代码回归仍为 Python 129、Swift 27 项通过。

### 2026-11-08：用户提供 Qwen3-ASR 多语言候选

- 将 `~/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25` 移至 `backend/.poc-data/models/` 下同名目录；972 MB 权重与样本目录被 Git 忽略。三份 ONNX 权重 SHA-256 和复现入口记录于 `poc/phase0-local-asr.md`。
- 新增 `backend/scripts/evaluate_qwen3_asr_poc.py`，以 sherpa-onnx 2.0.1 `OfflineRecognizer.from_qwen3_asr` 在 CPU 上对随包 5 条中/英/混说 WAV 执行自动语言离线解码。模型 load 2.025 秒，observed peak RSS 4,472,487,936 bytes；五条加权 CER 0.1564，单项和 RTF 已入报告。完整 transcript 不写日志。
- 88 秒英语样本在 max-total-len 1024 下出现截断警告；该结果已排除。将 max-total-len 调到 4096 后复跑，英语样本 CER 0.1743，RTF 0.8094。
- 本次不是 streaming 或麦克风测试。Qwen 官方资料说明 streaming inference 当前仅在 vLLM backend；本地 ONNX 候选目前经 OfflineRecognizer 整段解码。Qwen 源项目标注 Apache-2.0，但第三方 ONNX 转换包和随附 WAV 的再分发许可待核。用户仍需主动完成真人麦克风流程，未启动录音。

### 2026-11-08 补充

- 用户要求先延期未决事项。`DECISIONS.md` 已将 D-001–D-015 和 ADR-019/020/021/022 记为延期；D-010 Provider 组合待用户另行提供。尚无 Provider 名称/区域或请求授权，因此未读取凭据、未发出云请求。延期不等同于相关阶段验收证据通过。
- 继续 0H：新增子进程在 `os.replace` 调用前与成功返回后暂停，再经 SIGKILL 的两条边界用例。调用前中断保留旧加密备份，成功返回后中断保留新备份；两条路径源库和预期备份均可查询且 `integrity_check=ok`。不声称 syscall 内部中断或断电持久性。
- SQLCipher 专项回归 21 项通过；本轮全量 Python 回归 127 项通过。首次全量运行发现两项追踪文档契约断言需随报告术语同步，已修订后通过。阶段 0 仍未验收。

- 建立 `PROJECT_CONTEXT.md`、`DECISIONS.md`、`TASKS.md` 文档入口；阶段 0 证据权威来源仍是 `poc/phase0-traceability.md` 和各 POC 报告。
- 继续 0H：WAL backup progress callback 中独立 writer 提交一条及活动 reader 固定 snapshot 下三次 writer 提交，源库/备份检索与完整性检查均通过。SQLCipher 专项现为 19 项通过。
- 继续 0H：在 WAL TRUNCATE checkpoint 等待读锁期间对隔离子进程 SIGKILL；释放 reader 后源库两条已提交记录均可检索，完整性检查通过，checkpoint 重试成功。备份复制期间 SIGKILL 现覆盖 DELETE/WAL 两种 journal mode。
- 扩展 ENOSPC POC 到 APFS 临时映像。首轮试跑发现 APFS `hdiutil` 返回多个设备项且填充阶段可能先遇到文件级 `ENOSPC`；现按实际挂载点选择卷设备，并让填充器安全停在 ENOSPC，再独立验证数据库写入失败。48 MiB HFS+ 和 128 MiB APFS 测试均通过。
- 补记当前设备快照：MacBook Air `MacBookAir10,1` / M1 / 16 GiB，macOS 26.5.1，Xcode 26.6，Swift 6.3.3，uv Python 3.12.13，检查时数据卷可用约 18 GiB，内建麦克风/扬声器 48 kHz；主力设备身份仍待确认。
- 离线 Embedding 评估新增三次，4/4 合成 query 均命中，observed max RSS 为 883,130,368–883,490,816 bytes。Embedding 权重/上游模型页和 FastEmbed metadata 标注 Apache-2.0 初核完成；中文 ASR 上游要求接受访问条件，公开分发条款仍未核实，证据见 `phase0-model-license-review.md`。
- 新增根 `README.md`、`AGENTS.md` 和 macOS arm64 GitHub Actions workflow；本机等价 Python 125 项、Swift 27 项通过，`uv lock --check`、`compileall`、锁定依赖安装和 workflow YAML 语法通过。仓库没有 Git remote，因此 GitHub Actions 尚未实际运行。
- ENOSPC 额外尝试“满卷时覆盖既有备份”时，HFS+/APFS 结果不稳定，未纳入验收证据；保留稳定的源库 ENOSPC 回滚与事先生成备份恢复证据。备份目标自身 ENOSPC 仍为缺口。
- 本轮修改还包括根 `AGENTS.md`、`README.md`、`.github/workflows/ci.yml`，SQLCipher checkpoint crash helper、APFS ENOSPC 支持，以及相关 POC 报告、追踪/任务/决策记录。
- 下一步：审查并记录原子替换边界证据；继续补 0E supervisor 异常退出策略的可验证路径。0B 真人麦克风验收与 ASR 授权条款仍待设备/许可输入；0C Provider 组合待用户提供并逐请求明确授权；D-001–D-015 与 ADR-019/020/021/022 已延期。阶段 0 未验收，阶段 1 未开始。

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

- 官方双语 Streaming Zipformer 已有合成中英文件分帧 partial/final 证据；Qwen3-ASR ONNX 候选另有随包中/英离线评测。双语模型尚无真人麦克风与 SwiftUI 实机验收；不得静默改用云 ASR。
- 尚未验证 SwiftUI 麦克风链路、中英混合识别质量、P50/P95、资源占用、AEC、TTS 与 ASR 同时工作和锁屏/休眠处理。
- ASR 资源测量已对同一条合成 WAV 做 3 次独立进程重复，但没有独立语料或实时麦克风端到端统计；重复样本分布和可确认性能阈值仍未验证/未决。
- Gateway 已准备 DeepSeek（中国）与 OpenRouter（Global）的固定目标 adapter、Keychain 读取和逐请求确认 CLI；真实远程 Provider 请求、能力矩阵、费用、错误/fallback 尚未验证，需按 `poc/phase0-remote-provider.md` 由用户配置 Keychain 并逐次确认。POC-05 真实系统认证提示、异常自动恢复/退避、锁屏/休眠策略和正式分发仍未验证，SwiftUI demo 的进程握手/启停/退出清理已通过；POC-06 尚未评估密钥生命周期、APFS/外接介质 ENOSPC、断电/checkpoint 执行中断、备份介质故障和产品性能，也未作 ADR。记忆 Embedding 只接入 disposable 内存 repository，产品 schema 与真实检索质量仍未验收。
- 所有产品待决策项继续保持未定；本地 ASR 模型是临时 POC 候选。

## 下一步

继续阶段 0：Provider 方面，DeepSeek 与 OpenRouter 各有经用户逐次授权的真实合成文本请求成功；同一 ModelGateway 顺序跨 Provider 路由也真实通过一次，OpenRouter 返回 Relace/HKG；两家 SSE 各一次真实探测精确匹配。两家工具/JSON/错误能力、拒绝后的系统级零出站与重复费用/区域核验仍缺。Embedding 候选已集成至可注入的内存记忆 POC 并在本机离线合成检索，但真实检索集、资源目标、持久化迁移与产品模型选择未验收。备份 staging 经校验后原子替换目标，真实子进程备份期间 SIGKILL 后旧备份/源数据恢复通过；崩溃 staging 清理策略、断电和介质故障仍未验证。阶段 0 验收前不得进入阶段 1。

## 交接要求

后续每阶段完成或中断时更新本文件，并在报告中列修改文件、设计、测试命令与结果、未决项和验收对照。
