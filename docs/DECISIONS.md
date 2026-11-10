# 决策记录

最后核对：2026-11-10（Asia/Shanghai）

本文件只记录已确认的边界和决策状态，不替产品负责人补做规格书中的待决选择。正式架构决策按规格书 §16 的 ADR 编号追踪；证据和阶段完成度见 [阶段 0 追踪矩阵](poc/phase0-traceability.md)。

## 已确认

| 编号 | 决策 | 依据 / 影响 |
|---|---|---|
| C-001 | 本机是软件开发、测试和运行设备；这不排除未来由本机客户端连接云 Provider。 | 用户澄清；真实远端请求仍须单独满足 C-002。 |
| C-002 | 远端 Provider 请求必须由用户显式启用云端模型并经 Consent Manager 与 Policy Engine 授权；凭据只从 Keychain 取得。 | 用户 2026-11-08 明确选择云模型即作为持续授权，不再每条消息弹确认框。模型设置需说明所选服务商、后续聊天会自动出站及切回本地的方式；L3 凭据拦截、固定端点、无自动 fallback 继续生效。 |
| C-003 | 原中文专用 ASR 模型不覆盖英语不属于代码缺陷；新增 Qwen3-ASR 候选已做随包音频的离线中/英检查，但尚未完成流式/麦克风验收或模型选型。不得静默改用云 ASR。 | 用户澄清及 2026-11-08 离线 POC；详见 `phase0-local-asr.md`。 |
| C-004 | POC 证据不能替代产品验收或未决产品决策。阶段 0 原门禁仅适用于完整 V1/正式发布；单用户测试版按 C-007 分批推进。 | 原规格书 §13 门禁由 2026-11-08 用户明确收敛：测试版先交付核心可用闭环，后期能力开发时再做验证；安全与隐私底线仍适用。 |
| C-005 | 当前 Agent Registry 是模拟接口；权限取父权限交集，不在此阶段交付 Agent 团队或任意工具执行器。 | 规格书阶段 0 范围及现有 POC 报告。 |
| C-006 | 阶段 0 的交互式云模型 POC 测试默认优先使用千问；任何真实请求仍要求逐次 Consent/Policy 放行，不启用自动 fallback。 | 用户 2026-11-08 指定。Token Plan 文本兼容端点暂用 `qwen3.8-flash`、北京区域，限合规的交互式测试。Token Plan 服务支持文本 OpenAI-compatible HTTP 和 `qwen-audio-3.0-realtime-plus` Realtime WebSocket；个人版条款将使用范围限定在编程/智能体工具交互，并排除自定义应用后端，因此个人版 Key 不接入本项目自建 SwiftUI/FastAPI Beta。应用内云语音须另用适用于自定义应用的 API 凭据，或通过官方允许的 Agent 工具扩展路线。接入参数和状态见 `beta/qwen-token-plan-integration.md`。此项不等同于 D-010 的 V1 Provider 决策。 |
| C-007 | 开始建设单用户 macOS 测试版；阶段 0 未完成的验证不再整体阻塞可用测试版。 | 用户 2026-11-08 明确希望先交付可使用的软件，后期功能先留扩展接口，待功能开发时再完成相应验证。当前优先本机闭环；非测试版必需的 CI 远端运行、广泛负载/独立语料、未来云语音、服务端取消/区域费用核验、许可与正式分发闭环等转为按功能启用/发布前的任务。延期项不得表述为已验证；本机优先、逐次远端 Consent、Keychain、L3 默认拒绝等安全底线不延期。**补注（2026-11-09）**：本条列为延期项的"CI 远端运行"已不再延期——仓库已推送到 `origin`，GitHub Actions `Phase 0 checks` 已在 `main` 真实成功运行（run `42489738004`，Python `162 passed`、Swift `31 tests passed`）。C-007 其余延期项（广泛负载/独立语料、云语音、服务端取消与区域费用核验、许可与正式分发闭环）状态不变。 |

| C-008 | macOS 测试版 GUI 提供本地/云端模型来源选择；选中云模型后不再逐条弹确认。 | 用户 2026-11-08 要求优先增加模型设置按钮、默认云模型优先千问，并明确逐条弹窗影响聊天体验。云端默认配置为千问 `qwen3.8-flash` 按量计费应用 API（`sk-ws-`，独立 Keychain account `qwen-app`）；另保留 DeepSeek/OpenRouter 固定 POC 路由。选择云端模型视为持续授权，设置中明确告知聊天内容会发送到所选服务商，并允许切回本地。千问 Token Plan 个人版 `sk-sp-` 官方条款仅允许通过受支持的编程/智能体工具扩展交互使用，排除自定义应用后端，因此不能作为本应用直连 Provider。此 Beta 入口不等同于 D-010 的 V1 Provider 决策。 |
| C-009 | V1 使用项目自有轻量 ModelGateway，不引入第三方 Gateway 作为运行依赖；需要时再评估。 | 用户 2026-11-09 确认。LiteLLM/Bifrost/Portkey 桌面比较保留为参考；V1 的 Consent/Policy 默认拒绝、Keychain 和 L3 安全边界继续由项目实现并强制。 |
| C-010 | V1 语音范围为本机、用户主动点击后的实时 ASR；语音按钮可打断文字生成，final 进入草稿；不做 AEC、自动声学插话或云 Realtime。 | 用户 2026-11-09 确认。用户随后实机验证 partial、final 入草稿、取消丢弃、文字生成中点击打断并开始采集，以及录音中 Cmd-Q 后 app/backend 退出且重启无残留。后续 GUI 复测发现停止后立即再次点语音时握手失败；根因是 `LocalVoiceTranscriber` 收尾调用不存在的 `LocalStreamingASR.reset()`，异常清理使 ASR 锁未释放。现已改为重置底层 recognizer、保证异常时释放锁；用户随后确认故障已修复。D-013 Beta GUI 的启动、partial、停止→final 样本已达到采样数量且均低于门槛；真实硬件驱动异常仍未验证。 |

## 待决产品事项

以下事项沿用规格书 §15，状态以该规格和追踪矩阵为准；除非用户明确决定，不作为实现默认值：

| 编号 | 待决事项 | 当前记录 |
|---|---|---|
| D-001 | 主力 Mac 型号、内存、磁盘 | **Accepted（2026-11-09）**。用户确认当前 MacBook Air `MacBookAir10,1` / Apple M1 / 16 GiB 为主力开发/运行设备；数据卷剩余约 21 GiB，当前快照见 `poc/phase0-local-asr.md`。 |
| D-002 | 最低 macOS | **Accepted（2026-11-09）：macOS 14.0**。与 Beta Info.plist 当前 `LSMinimumSystemVersion` 相符；仍需 CI 目标和安装包验证覆盖该最低版本。 |
| D-003 | 对话、日志、缓存和备份保留期限 | **部分确认（2026-11-10）**：用户决定本地持久化聊天、任务与已确认记忆；聊天和已确认记忆由用户手动删除，完成任务在 30 天后自动清理。其余安全日志/临时缓存规则沿用原决策：安全日志仅元数据保留 30 天，临时会话/音频缓存退出或中断时清理。D-006 已确认本机预恢复副本仅保留最近一份，新份创建时替换旧份；用户自选位置中的手动备份仍由用户管理。记忆派生数据删除流程尚待设计。B3 已接入聊天/任务/确认记忆持久化，记忆支持显式修正、版本快照、当前会话来源关联与只读查看。 |
| D-004 | 音频缓冲上限及异常清理 | **Accepted（2026-11-09）**。本机 PCM16 单声道缓存最多 30 秒（960,000 字节）；取消、异常、断连和应用退出时立即停止采集并清空未完成音频。正常停止只把最终转写放入当前输入草稿，录音本身不保留。Beta 已有 30 秒上限及实时 WebSocket 上限/断连回归；用户实机确认取消丢弃 partial，且录音中 Cmd-Q 后 app/backend 退出、重启无残留。真实 AVAudioEngine 硬件驱动故障仍未注入。 |
| D-005 | 月 API 预算、币种、软/硬阈值 | **Accepted（2026-11-09；估算规则补充确认 2026-11-10）**：每月 100 元人民币；累计到 80 元提示；累计到 100 元硬拦截后续云请求，额度按自然月重置。无请求级实际费用/usage 或汇率时，按带版本的公开价目估算并明确标注为估算，估算累计达限后拦截。估算不得表述为实扣费用；已落地版本化估算器，覆盖当前固定 Beta 的 DeepSeek、OpenRouter DeepSeek Flash 和 Qwen3.8 Flash；SQLCipher 月聚合、80 元用量页提示、请求前预算预留和完成结算已接入，SQLite 事务在共享数据库实例间原子检查余额。请求预留五分钟过期回收，活动流每分钟续租（远端 HTTP 读取空闲超时 45 秒）；当前月份功能启用前的账单无法回填，真实 Provider usage/cost E2E 尚未关闭，价目快照需随官方价格变更人工升级。 |
| D-006 | 备份 RPO/RTO、份数和目的地 | **部分确认（2026-11-10）**：用户主动触发、写入自选位置，每份使用独立口令；恢复输入同一口令并通过系统认证，恢复前自动制作当前数据预备份。用户确认备份口令使用 scrypt（N=32768、r=8、p=1、16-byte random salt、32-byte derived key），不保存在应用/Keychain；只支持当前 Mac 恢复。恢复后将备份数据库重新加密为当前安装的 Keychain 数据库密钥。RPO 是最近一次成功手动备份。用户补充确认预恢复加密副本仅保留最近一份，新副本创建时替换旧副本；已实现为完成校验和恢复切换后原子替换固定路径，轮替回归覆盖连续恢复。RTO、外部备份副本保留规则、断电/强制终止期间恢复仍待实机验证。 |
| D-007 | 静态加密方案 | **Accepted（方向，2026-11-10）**：产品持久数据库使用 SQLCipher；每个安装生成随机数据库密钥并存 macOS Keychain，用户登录解锁 Keychain 后可自动打开数据库，不要求每次启动都做 Touch ID。密钥丢失会使本地数据不可读，须在备份/恢复方案中处理；在 Keychain ACL/可访问性、密钥创建/轮换/删除、SQLCipher Community attribution、migration 与恢复路径完成验证前，不标记加密产品实现完成。B3 已接入聊天、任务和确认记忆的本机加密存储；备份、Keychain 实机与恢复验收仍未完成。
| D-008 | 外接盘能否作为活动数据目录 | **Accepted（2026-11-09，范围决策）**：V1 不支持外接盘作为活动数据目录；若未来加入持久化数据目录，再评估外接介质并补断连/故障/性能验证。该决策不批准将模型权重或缓存写到外接盘。 |
| D-009 | 固定专业 Agent 属于 V2 还是 V3 | **Accepted（2026-11-09）**：V2 提供少量固定专业 Agent；完整专业 Agent 集放 V3。V1 仍为一个总助理，不实现 Agent 团队或任意 Agent 执行器。 |
| D-010 | V1 首批 Provider | **Accepted（2026-11-09）**：千问应用 API 为默认云端 Provider，另支持 DeepSeek（中国路由）和 OpenRouter（Global 路由）。这是产品范围选择，不代表各 Provider 的完整能力、取消、费用或区域证据均已验收；POC 证据见 `poc/phase0-remote-provider.md`。 |
| D-011 | 云 ASR/TTS 供应商与区域 | **阶段 0 交互式 POC 候选已确认（2026-11-08）**：优先千问 Token Plan，北京区域；候选为 `qwen-audio-3.0-asr-flash`、`qwen-audio-3.0-realtime-plus` 和 `qwen-audio-3.0-tts-plus`。服务端能力支持已核实，但个人版 Key 不可用于本项目自建应用；应用内云语音须另选适用于自定义应用的计费凭据，或经官方允许的 Agent 工具扩展路线。接口和用户真实音频尚未验证。范围见[Token Plan 个人版条款](https://platform.qianwenai.com/docs/token-plan/personal/token-plan-personal-overview)、[接入概览](https://platform.qianwenai.com/docs/token-plan/best-practices/integration-overview)、[Token Plan 实时语音接入](https://platform.qianwenai.com/docs/token-plan/best-practices/realtime-voice)、[Realtime API 协议矩阵](https://platform.qianwenai.com/docs/api-reference/realtime-api/overview)。 |
| D-012 | 文件导入白名单和容量限制 | **Accepted（2026-11-09）**：V1 用户主动选择并只读导入 TXT、Markdown、PDF；每个文件最大 10 MB。不得扫描目录或执行文件内容；解析器/格式校验、PDF 资源限制、路径权限和删除策略需在功能启用前做安全 POC。 |
| D-013 | 性能目标数值 | **Accepted（2026-11-09）**：在主力 MacBook Air M1/16 GiB 上，App 启动 P95 ≤5 秒；ASR partial 延迟 P95 ≤500 毫秒；用户停止录音到 final 草稿可用 P95 ≤2 秒。以独立、可复核的 Beta 端到端样本测量；既有合成/CLI 帧推理结果不能替代这些门槛。 |
| D-014 | Embedding 型号和存储格式 | **部分确认（2026-11-10）**：用户决定持久化已确认记忆；先进行离线候选评测，再决定是否启用及产品选型。评测须离线运行并记录模型、维度、存储格式和质量/资源证据；评测完成不自动授权产品启用。FastEmbed/MiniLM 仍只是候选，384 维；POC 当前只在内存保存 Python float tuple，未决定产品存储格式。合成集三次离线质量一致：24 条改写题候选 23/24 top-1、24/24 top-3，FTS5 0/24；12 条词面题候选/FTS5 均 12/12；12 条负例候选无拒答阈值而均返回，FTS5 均拒答。三轮重复资源观察：real 1.48–2.03 秒、中位数 1.57 秒，maximum RSS 909,656,064–911,540,224 bytes；缓存已存在，不代表冷启动或产品规模。分数/资源均只适用于合成工作负载，详见 `docs/poc/phase0-local-embedding.md`；更大且独立复核的平衡人工标注语料、冷启动/产品资源目标和存储决策仍待完成，不据此启用。 |
| D-015 | 导出格式及默认加密 | **DEFERRED（2026-11-10）**：用户决定暂缓通用数据导出，继续只提供加密备份/恢复。不得新增通用导出文件；如重开，须重新确认范围、格式和保护策略。 |

| D-016 | V2 本机日历读取权限 | **Accepted（2026-11-10）**：用户接受 macOS EventKit 完整日历访问权限，因为平台不提供只读授权。日历读取面板只在用户点击后读取未来 30 天事件的标题、时间和日历名称；该面板不创建/修改/删除事件，不持久化或发送模型服务商。D-022 定义独立、逐次审批的事件创建入口。提醒事项是单独的 EventKit 权限，当前未授权/未接入。 |
| D-017 | V2 固定专业助理角色 | **Accepted（2026-11-10）**：先提供项目助理、会议助理和任务规划助理三个固定角色。保持项目自有最小权限，不启用任意工具、后台 Agent 团队或外部写操作；后续 Skills 与外部操作需各自审批边界。 |
| D-018 | V2 本机任务状态迁移 | **Accepted（2026-11-10）**：采用当前已实现迁移图。`PENDING→READY/CANCELLED`；`READY→RUNNING/PAUSED/CANCELLED`；`RUNNING→WAITING/PARTIAL/COMPLETED/FAILED/CANCELLED`；`WAITING→READY/RUNNING/PAUSED/CANCELLED`；`PAUSED→READY/CANCELLED`；`PARTIAL→READY/COMPLETED/FAILED/CANCELLED`；`FAILED→READY/CANCELLED`；`COMPLETED` 与 `CANCELLED` 为终态。相同状态提交幂等，不自动执行任务或后台重试。 |
| D-019 | V3 首版 Skills 权限范围 | **Accepted（2026-11-10）**：首版仅本机保存的固定提示模板，用户逐次显式选择是否附加到当前请求；不注册工具、不执行代码、不做外部写。 |
| D-020 | V2 EventKit 提醒事项读取 | **Accepted（2026-11-10）**：用户接受系统完整提醒事项权限，应用代码保持只读；仅在用户点击后读取到期日为未来 30 天内的未完成提醒及无到期日条目，不创建、修改、完成或删除，不持久化或发送给 Provider。 |
| D-021 | V3 多 Agent 协作边界 | **Accepted / Implemented（2026-11-10）**：仅用户点击触发，在本机 Ollama 上顺序运行用户选择的固定专业助理，再由总助理汇总；云 Provider、后台执行、跨会话记忆读取、工具和外部写均不启用。中间专业助理输出只在单次运行内存中传递。D-022 的事件创建能力独立于多 Agent；协作角色不能直接执行该写操作。 |
| D-022 | V3 首个外部写操作：创建日历事件 | **Accepted（2026-11-10）**：仅支持用户主动打开表单后创建单个非重复事件到 macOS 当前默认日历；用户输入标题/开始/结束时间，可选地点/备注。每次必须显示确切预览并二次确认；无参会者、邀请、重复规则、提醒、读取/修改/删除或后台执行。采用 EventKit write-only 权限；若已有 full access 则复用。明确提示系统可能按该日历账户设置同步。SQLite 加密审计必须在写入前记录 ATTEMPTED，失败关闭；完成后记 SUCCEEDED/FAILED，仅记录 metadata，不写事件内容。多 Agent 不得自动调用。 |

## ADR 状态

ADR-001–ADR-022 的原始定义见 [开发规格 v1.2 §16](../个人AI助理可执行开发规格书%20v1.2.md#16-adr-清单延续-v11)。ADR-020 已 Accepted：V1 使用项目自有轻量 Gateway，不引入开源运行依赖；ADR-021 已 Accepted 为 C-010 所列 V1 本机语音边界；ADR-022 已随用户确认主力设备和最低 macOS 改为 Accepted。ADR-019（持久化静态加密方案）继续 Deferred，直至引入持久数据。延期或范围决策不豁免对应功能的阶段 0 POC/验收证据。
