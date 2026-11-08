# 决策记录

最后核对：2026-11-08（Asia/Shanghai）

本文件只记录已确认的边界和决策状态，不替产品负责人补做规格书中的待决选择。正式架构决策按规格书 §16 的 ADR 编号追踪；证据和阶段完成度见 [阶段 0 追踪矩阵](poc/phase0-traceability.md)。

## 已确认

| 编号 | 决策 | 依据 / 影响 |
|---|---|---|
| C-001 | 本机是软件开发、测试和运行设备；这不排除未来由本机客户端连接云 Provider。 | 用户澄清；真实远端请求仍须单独满足 C-002。 |
| C-002 | 任何远端 Provider 请求都必须经 Consent Manager 与 Policy Engine 明确授权；默认拒绝，凭据只从 Keychain 取得。 | 用户澄清及规格书 ADR-012、FR-SEC；现有 POC 仅证明策略边界，不证明真实供应商链路。 |
| C-003 | 原中文专用 ASR 模型不覆盖英语不属于代码缺陷；新增 Qwen3-ASR 候选已做随包音频的离线中/英检查，但尚未完成流式/麦克风验收或模型选型。不得静默改用云 ASR。 | 用户澄清及 2026-11-08 离线 POC；详见 `phase0-local-asr.md`。 |
| C-004 | POC 证据不能替代产品验收或未决产品决策。阶段 0 原门禁仅适用于完整 V1/正式发布；单用户测试版按 C-007 分批推进。 | 原规格书 §13 门禁由 2026-11-08 用户明确收敛：测试版先交付核心可用闭环，后期能力开发时再做验证；安全与隐私底线仍适用。 |
| C-005 | 当前 Agent Registry 是模拟接口；权限取父权限交集，不在此阶段交付 Agent 团队或任意工具执行器。 | 规格书阶段 0 范围及现有 POC 报告。 |
| C-006 | 阶段 0 的交互式云模型 POC 测试默认优先使用千问；任何真实请求仍要求逐次 Consent/Policy 放行，不启用自动 fallback。 | 用户 2026-11-08 指定。Token Plan 文本兼容端点暂用 `qwen3.8-flash`、北京区域，限交互式测试；阿里云官方说明 Token Plan 不能用于后端服务，因此不将 Token Plan Key 接入产品后端。ASR/TTS/实时语音使用各自协议和接口，不视作 OpenAI chat 兼容。此项是测试默认，不等同于 D-010 的 V1 Provider 决策；产品后端所需计费方案仍待确认。 |
| C-007 | 开始建设单用户 macOS 测试版；阶段 0 未完成的验证不再整体阻塞可用测试版。 | 用户 2026-11-08 明确希望先交付可使用的软件，后期功能先留扩展接口，待功能开发时再完成相应验证。当前优先本机闭环；非测试版必需的 CI 远端运行、广泛负载/独立语料、未来云语音、服务端取消/区域费用核验、许可与正式分发闭环等转为按功能启用/发布前的任务。延期项不得表述为已验证；本机优先、逐次远端 Consent、Keychain、L3 默认拒绝等安全底线不延期。 |

## 待决产品事项

以下事项沿用规格书 §15，状态以该规格和追踪矩阵为准；除非用户明确决定，不作为实现默认值：

| 编号 | 待决事项 | 当前记录 |
|---|---|---|
| D-001 | 主力 Mac 型号、内存、磁盘 | **DEFERRED（2026-11-08，用户要求延期未决事项）**。观测快照仍为 MacBook Air `MacBookAir10,1`、M1/16 GB；尚未确认是产品主力设备。 |
| D-002 | 最低 macOS | **DEFERRED（2026-11-08）**；发布目标确认时再定。 |
| D-003 | 对话、日志、缓存和备份保留期限 | **DEFERRED（2026-11-08）**。 |
| D-004 | 音频缓冲上限及异常清理 | **DEFERRED（2026-11-08）**。 |
| D-005 | 月 API 预算、币种、软/硬阈值 | **DEFERRED（2026-11-08）**。 |
| D-006 | 备份 RPO/RTO、份数和目的地 | **DEFERRED（2026-11-08）**。 |
| D-007 | 静态加密方案 | **DEFERRED（2026-11-08）**；ADR-019 同步延期。 |
| D-008 | 外接盘能否作为活动数据目录 | **DEFERRED（2026-11-08）**；若恢复该范围，需补介质 POC。 |
| D-009 | 固定专业 Agent 属于 V2 还是 V3 | **DEFERRED（2026-11-08）**。 |
| D-010 | V1 首批 Provider | **DEFERRED（2026-11-08）**；用户提供 DeepSeek 与 OpenRouter 两家测试候选，并确认 DeepSeek 按中国处理、OpenRouter 使用 Global 路由。是否将它们定为 V1 首批组合仍待决。两家各有一次经用户逐次确认的 L1 合成文本请求成功；详见 `poc/phase0-remote-provider.md`。 |
| D-011 | 云 ASR/TTS 供应商与区域 | **阶段 0 交互式 POC 候选已确认（2026-11-08）**：优先千问 Token Plan，北京区域；截图所列候选为 `qwen-audio-3.0-asr-flash`（非实时 ASR）、`qwen-audio-3.0-realtime-plus`（实时语音对话）和 `qwen-audio-3.0-tts-plus`（TTS）。接口实现和真实请求尚未验证。官方说明 Token Plan 仅供 AI 工具交互式使用、不能用于后端服务；产品后端需另选允许后端调用的百炼计费方案/API Key。见[Base URL 范围](https://help.aliyun.com/zh/model-studio/base-url)、[接入概览](https://help.aliyun.com/zh/model-studio/token-plan-integration-overview)、[语音识别](https://help.aliyun.com/zh/model-studio/token-plan-speech-recognition)、[语音合成](https://help.aliyun.com/zh/model-studio/token-plan-speech-synthesis)、[实时语音对话](https://help.aliyun.com/zh/model-studio/token-plan-realtime-voice)。 |
| D-012 | 文件导入白名单和容量限制 | **DEFERRED（2026-11-08）**。 |
| D-013 | 性能目标数值 | **DEFERRED（2026-11-08）**；当前测量仅作为观察值。 |
| D-014 | Embedding 型号和存储格式 | **DEFERRED（2026-11-08）**。 |
| D-015 | 导出格式及默认加密 | **DEFERRED（2026-11-08）**。 |

## ADR 状态

ADR-001–ADR-022 的原始定义见 [开发规格 v1.2 §16](../个人AI助理可执行开发规格书%20v1.2.md#16-adr-清单延续-v11)。**按用户 2026-11-08 指示，未决事项先延期：ADR-019（静态加密）、ADR-020（Gateway 运行依赖）、ADR-021（音频协议/AEC/插话）、ADR-022（主力 Mac/最低 macOS）均记录为 DEFERRED，等待后续恢复决策。** 其他 ADR 状态按基线记录，不因该指示自动变更。延期是产品决策状态，不豁免阶段 0 明确要求的 POC/验收证据。
