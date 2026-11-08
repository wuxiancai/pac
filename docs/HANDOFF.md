### 2026-11-08：0G Python 依赖许可证线索复核

- 核实 `tokenizers==0.23.3` 的本机 Trove classifier 与固定版本 PyPI 页均声明 Apache，发布对应的上游 tag 有 LICENSE 文件。更新 SBOM 报告以明确 metadata 分类来源。
- 54/54 锁定包目前各有初步来源线索；许可证适用范围、通知义务、原生依赖与最终打包闭包仍未审查，不是法律批准。依据：[固定版本 PyPI 页面](https://pypi.org/project/tokenizers/0.23.3/)、[上游 tag LICENSE](https://github.com/huggingface/tokenizers/blob/v0.23.3/LICENSE)。

### 2026-11-08：0B 模拟设备故障注入

- 新增 PortAudio stream open failure 与 callback status error 注入；打开失败被清楚报告并丢弃 PCM 缓冲，callback 状态错误会停止采集、退出 stream context 并清空缓冲。decoder 异常/用户 Ctrl-C 路径继续通过原有测试。
- `tests/test_microphone_buffer.py` 11 项通过；完整 Python 回归 153 项通过。均为 mock 故障，不替代真实麦克风驱动故障测试。阶段 0 仍未验收。

### 2026-11-08：0E 真实系统认证再次成功

- 真实 demo 窗口新状态显示“认证未完成或被系统拒绝”；累计认证成功两次、未认证一次。该按钮路径不访问钥匙串。
- 当前 UI 把用户取消与系统拒绝合并显示，因此不能单靠界面状态确定具体错误原因；按未认证/fail-closed 证据记录。其余未决：异常自动恢复/退避、锁屏/休眠和正式分发。

### 2026-11-08：阶段 0 队列状态校准

- `TASKS.md` 的 0I 项已标记 ASR-final→本机 TTS 合成链路报告完成（5 条样本、7/7 播放成功）；保留独立真人语料/多负载资源、真实 Provider 服务端取消、许可闭包、恢复边界和真实 CI 等缺口。
- 阶段 0 仍未验收，阶段 1 未开始。

### 2026-11-08：0D MemoryStore Embedding 检索集扩展

- 将 disposable MemoryStore 的固定合成评估由 3 条记忆/查询扩为 4 条，新增 Swift 编程语言记忆与 macOS 开发语言 query；不使用私人数据。
- 固定候选权重离线合成检索 4/4 top-1；严格离线输出 `memory_count=4`、`query_count=4`、`top1_matches=4`、来源证据完整，没有输出 query/记忆原文。仍是小型合成集，产品 schema 和默认模型选择保持不变。详见 `poc/phase0-memory-embedding.md`。

### 2026-11-08：0B ASR/TTS 验收缺口复核

- 对照规格书 §13 并新增 manifest 样本 ASR-final → AVSpeechSynthesizer 冒烟脚本；5 条中英/混说系统合成 WAV 共 7/7 得到 final 并正常完成播放，未落盘 transcript。已有独立 AVSpeechSynthesizer 立即打断实测。
- 此证据满足本机候选链路的基本连通性；独立语料、长时/多负载资源稳定性、真实驱动异常和产品性能目标仍未覆盖。`TASKS.md` 已去掉过时的“选择中文或双语模型”建议；当前模型许可只记录公开声明，权利链及转换包许可仍需核验，不隐含产品选型。
- 阶段 0 仍未验收；下一步优先继续 0B 独立真人语料/资源补证或推进其他无外部授权依赖的工作包，不启动麦克风或云请求。

### 2026-11-08：0B/0G 双语 ASR 许可线索复核

- 第一方资料核对发现，归档模型包 README 声明 Apache-2.0 并指向 `pfluo/k2fsa-zipformer-chinese-english-mixed`；sherpa-onnx 官方索引将转换来源列为 `csukuangfj/k2fsa-zipformer-chinese-english-mixed`。两个 Hugging Face 模型页都声明 Apache-2.0，但官方索引只称其使用内部训练数据，权利链未给出可核验细节。
- 修正 ASR 报告中上游归属，新增运行时、sounddevice 与 PortAudio 分层许可线索。结论限于仓库/包维护者声明；不视作训练数据权利审计或正式分发批准。详见 `poc/phase0-model-license-review.md`。
- 用户无需配合；模型仍仅作本机 POC，不据此决定产品打包。

### 2026-11-08：0B 本机 ASR 与 LLM 并发重复测量

- 同一条 6.94 秒合成 WAV + `qwen3.5:0.8b` 新跑三轮，均重叠、35 帧、15 partial/1 final。重叠 0.420–0.553 秒，P50 16.65–20.82 ms、P95 19.55–30.17 ms、峰值帧耗时 35.41–36.90 ms；本机 ASR 与 Ollama 进程 RSS 采样峰值 585,367,552–1,126,219,776 bytes。加上已有一轮，共四轮同样本观察。
- GPU 未测；RSS/CPU 采用 1 秒进程采样，CPU 估算窗口不同且波动，不作横向结论；重复同一音频不是独立语料或产品性能验收。具体范围见 `poc/phase0-local-asr.md`。
- 全量 Python 回归 151 passed；详见报告。

### 2026-11-08：0H 备份 ENOSPC 失败路径

- 在 `backup_to` 复制边界确定性注入 `OSError(ENOSPC)`；安全错误保留可识别 cause，旧备份可用旧密钥检索且完整，源库保持完整，`.partial` 清理。
- 与实际 HFS+/APFS 有界映像写满测试区分：物理目标卷满载下的备份失败尚未实测。该项尝试发现满卷后备份有时仍完成，且 APFS 满载时重开数据库需要可用空间；未将不稳定结果记作通过。
- 窄回归：`UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security --group dev pytest -q tests/test_sqlcipher_enospc_poc.py tests/test_sqlcipher_compat_poc.py`，28 passed。

### 2026-11-08：0I 规格阶段归属复核

- 对照规格书 §13–§14 修正 0B 门禁描述：SwiftUI 麦克风、AEC 与锁屏/休眠语音闭环属于阶段 3，不再误列为阶段 0 的 0B 阻塞项。阶段 0 当前继续核对 ASR/TTS 稳定链路报告、资源证据及总体追踪矩阵。
- 真实设备驱动异常仍未专门注入，作为稳健性补证；云 ASR/TTS 候选受 D-011 延期约束，未擅自选择 Provider/区域。阶段 0 未验收，阶段 1 未开始。

### 2026-11-08：0E GUI 后端多轮启停复测

- 在本机 demo 窗口完成两轮停止→启动→健康检查，UI 每轮均先回到“尚未检查”，再显示“本机服务已连接”；进程表最后只有一个 `pac_poc.local_service` 子进程。
- 真实系统认证成功证据已记录，认证测试不会访问钥匙串。Swift 回归 29 项通过；取消/拒绝认证、锁屏/休眠、异常自动恢复与正式签名分发仍待处理。

### 2026-11-08：0E 真实系统认证测试入口就绪

- 在本机生命周期 demo 加入“测试 macOS 系统认证提示”按钮及结果状态；系统认证 reason 明确告知只验证本机认证，不修改钥匙串。该流程只调用 `SensitiveActionAuthorizing`，不读取或写入 Keychain。
- `swift test` 29 项通过；本机 `.app` 已重新构建并打开。观察到用户完成系统认证后，demo 界面显示“系统认证成功；未访问钥匙串”。未推断认证方式；取消/拒绝结果仍待测。
- 更新 0E 报告、追踪矩阵、任务清单和项目上下文。其他锁屏/休眠、正式分发和异常恢复缺口仍在。

### 2026-11-08：开麦实机双语 partial/final 复测

- 用户澄清前一次无识别输出是因为麦克风未打开。重新开麦后，双语 Streaming Zipformer CLI 观察到多组中文和英文 partial/final，包含中文连续指令和英文短句。
- 记录为一次真实麦克风功能冒烟通过；部分识别词句有误，按用户要求作为后续模型优化项，不作为当前功能冒烟阻断项。合计已有三次实机 CLI 观察到 partial/final。
- 阶段 0 仍未验收；驱动异常、SwiftUI 音频集成、性能与模型许可等缺口仍在。

### 2026-11-08：真实麦克风 Ctrl-C 停止冒烟

- 用户运行双语 Streaming Zipformer 麦克风 CLI，程序进入“正在本机识别”；停止前未显示 partial/final，按 Ctrl-C 后显示正常停止提示并返回 shell。
- 这证明真实设备手动停止路径能返回；用户随后说明当时麦克风未打开，因此该次不计为识别成功。报告、追踪矩阵和任务清单已更新。
- 阶段 0 仍未验收；后续需确认讲话时是否有 partial/final，并继续处理驱动异常、SwiftUI 集成、许可和其他工作包缺口。

### 2026-11-08：0B 用户中断路径清理回归

- 将 mock 麦克风清理回归扩展为两种退出：识别器普通异常时错误向上传递；模拟 `KeyboardInterrupt` 时显示停止提示。两条路径都会退出输入流上下文并清空有界缓冲，没有启动真实麦克风。
- 0B 仍需真实设备上的停止/驱动异常冒烟、SwiftUI 音频链路和其他阶段验收证据。
- 验证通过：`tests/test_microphone_buffer.py` 9 passed；全量 Python 149 passed；compileall、`uv lock --check`、`git diff --check` 通过。

### 2026-11-08：0B 识别器异常时的本地清理回归

- 新增模拟麦克风 callback 与故障 decoder 回归：decoder 抛出异常后，输入流上下文退出，音频缓冲关闭并清空；测试没有启用真实麦克风。
- 真实设备的 Ctrl-C / 驱动异常仍需本机交互冒烟，SwiftUI 音频集成也未覆盖。0C 的陈旧取消/JSON 状态同步已修正；两家 Provider 服务端是否停止生成仍未知。
- 验证通过：麦克风窄回归 8 passed；全量 Python 148 passed；compileall、`uv lock --check`、`git diff --check` 通过。

### 2026-11-08：完成 0C 取消证据对齐与 API Key 提示回归

- 对齐了阶段追踪和 Provider 报告：DeepSeek、OpenRouter 均已各自完成一次 SSE 首片段后客户端取消；Provider 是否停止生成或计费仍无服务端证据。DeepSeek JSON 现记为三次一空两成功。
- 补充 CLI 错误提示回归：401 在所有 capability 出错路径均显示中文 API Key 认证失败和 Keychain 检查指引；403 等其他状态不误标为 Key 错误。
- 验证通过：窄回归 36 passed；全量 Python 148 passed；compileall、`uv lock --check`、`git diff --check` 通过。阶段 0 未验收，0C 剩余缺口仍见追踪矩阵。

### 2026-11-08：Provider API Key 错误分类与 DeepSeek JSON 复核

- 用户再次授权的 DeepSeek JSON 请求成功返回 `{"phase0":"ack"}`，结构匹配，finish_reason=`stop`，tokens=68/28/96。结合前一次成功（68/46/114），此前空正文不是 API Key 错误的证据；空正文根因仍未知。
- 适配器对 HTTP 401 给出凭据认证失败提示，并区分 402 余额、403 权限、429 限流；Keychain 缺失仍是独立提示。`error` probe 只把 HTTP 400/422 作为预期请求校验错误，不会把认证/余额等 4xx 误报为通过。错误响应正文仍丢弃；没有发送验证 Key 的额外远端请求。
- 验证通过：窄回归 34 passed；全量 Python 145 passed；`python -m compileall -q pac_poc scripts`、`uv lock --check`、`git diff --check` 均通过。0C 仍未验收。后续 Provider 请求仍需逐项 Consent。

# HANDOFF

> 文档入口：稳定项目约束见 [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md)，已确认/待决选择见 [DECISIONS.md](DECISIONS.md)，阶段任务与下一步见 [TASKS.md](TASKS.md)，阶段证据见 [追踪矩阵](poc/phase0-traceability.md)。本文件仅作为最近交接摘要；避免在这里重复维护完整任务和决策清单。

最近更新：2026-11-08（Asia/Shanghai）

## 最近交接

### 2026-11-08：OpenRouter SSE 客户端取消实测

- 用户逐次确认 `ALLOW OPENROUTER CANCEL 1` 后，真实 SSE 返回首个片段 `phase0-probe-`，脚本立即关闭 gateway stream。与 DeepSeek 一样，证明客户端取消路径；没有服务端信号说明 Provider 停止生成或计费。
- 两家客户端取消实测均完成；DeepSeek JSON 后续已有第三次观察，三次一空两成功；DeepSeek 服务端仍未提供费用/区域 metadata，取消是否停止 Provider 生成未知。阶段 0 整体仍未验收。

### 2026-11-08：DeepSeek SSE 客户端取消实测

- 用户逐次确认 `ALLOW DEEPSEEK CANCEL 1` 后，真实 SSE 返回首个文本片段 `phase`，脚本立即关闭 gateway stream。此结果验证客户端取消路径；没有服务端信号可确认 Provider 停止生成或停止计费。
- 取消能力的本地资源关闭回归已通过（窄 34、全量 145）；本次真实探测无自动重试。随后用户已完成 OpenRouter `cancel`；见上方最新交接记录。

### 2026-11-08：Provider SSE 首片段后取消探测就绪

- `probe_provider_capability_poc.py` 新增 `cancel` 能力：每次经精确 Consent 发起一条 SSE 请求，收到首个文本 delta 后主动关闭 gateway stream。脚本提示可能计费，并明确只观测客户端关闭，不把它当作 Provider 已停止生成的证明。
- 新增 MockTransport 测试，首片段后关闭 gateway stream 会关闭底层 HTTP 响应体。窄回归 34 项、全量 Python 145 项、compileall、uv lock --check 均通过。
- 下一步可分别逐次确认 `deepseek cancel` 与 `openrouter cancel`。复现命令与证据限制见 `poc/phase0-remote-provider.md`。DeepSeek JSON 目前两次一空一成功，原因/重复一致性未明。

### 2026-11-08：拒绝路径 PID 级 socket 检查完成

- 用户提供的全局 `tcpdump -i en0` 捕获 546 个 TCP/443 窗口包；输出包含已建立的会话，未按 PID 过滤，不能据此归因给测试进程。
- 用真实 HTTPX、无 Consent、凭据读取 tripwire 的 harness 分别运行 OpenRouter 与 DeepSeek；两者都在 Adapter 前拒绝，Keychain credential reads=0。Policy 拒绝后在 harness hold 窗口内通过 PID 运行 `lsof -nP -a -p <PID> -i`，均无活动 socket；loopback 正向对照证明 lsof 能列出进程 TCP socket。
- 当前证据支持这两个拒绝路径未建立网络 socket；限制是 lsof 只观察活动 socket，非完整包级/全系统零流量证明。deny-check、真实 HTTPX harness 和证据边界已记录。
- DeepSeek JSON 增强诊断复测已由用户逐次确认：返回 `{"phase0":"ack"}`，结构检查 True，finish_reason=`stop`，tokens=68/46/114；与此前空正文形成一次成功、一次失败。下一步检查 0C 剩余验收，优先远端流式取消语义与 JSON 重复一致性。

### 2026-11-08：拒绝路径真实 HTTPX 与系统监测准备

- 新增 `backend/scripts/probe_denied_egress_poc.py <provider>`：走真实 HTTPX client、默认无 Consent，并以 credential tripwire 避免读取真实凭据；观察窗口内 OpenRouter 被 Policy 在 Adapter 前拒绝，credential reads=0。无 Provider 请求发出。
- `nettop` PID 过滤在本机未能显示测试进程，loopback 正向对照也未出现，不能作为系统证据；`tcpdump` 存在但打开 BPF 需要 sudo，当前 agent shell 无管理员凭据。系统级抓包仍未完成，需用户在本机终端短时运行 `sudo tcpdump -i en0 -nn -l 'tcp port 443 and (tcp[tcpflags] & tcp-syn != 0)'`，同时运行上述本地 harness，然后停止抓包并提供是否观察到新连接/ SYN 的结果。tcpdump 默认只显示包头，不写 pcap 文件。
- DeepSeek metadata 两次结果已由增强 CLI 后记录；下一项可重新逐次确认 DeepSeek JSON 获取 finish_reason/usage，之后完成系统抓包。

### 2026-11-08：DeepSeek metadata 重复观察完成

- 用户分别确认 DeepSeek metadata 两条请求。两次均报告模型 `deepseek-flash`，服务未返回下游 Provider/区域/费用；token 分别 42/29/71 与 42/16/58。第 1 次 ACK 不匹配，第 2 次匹配；旧 CLI 未输出第 1 次正文，原因未知。
- metadata 探测现会在 ACK 不匹配时显示 JSON 编码的实际正文（转义控制字符）。窄回归 33 项、全量 Python 144 项、compileall、uv lock --check 通过。没有重发远端请求。
- 下一步可用增强后的脚本重新逐次确认 DeepSeek JSON，以观察 finish_reason、usage 与空正文诊断；另需完成系统级拒绝零出站验证。阶段 0 仍未验收。

### 2026-11-08：OpenRouter 费用与区域重复核验

- 用户对 `openrouter metadata --repeat 2` 两次请求分别给出精确确认；两次均精确匹配，均报告 Relace/HKG。Token 分别 42/17/59、42/16/58；cost 分别 USD 0.000008752、0.000008252。小样本只记录观察，不推导定价规律。
- OpenRouter 的费用/区域已完成两次重复观察；DeepSeek metadata 重复观察仍待执行，服务此前未提供实际 Provider/区域/费用。下一项命令为 `deepseek metadata --repeat 2`，会逐次确认两条请求。
- 本轮只更新文档；提交前执行 `git diff --check`。

### 2026-11-08：OpenRouter 错误路径返回 HTTP 400

- 用户逐次确认 OpenRouter `error` 探测后，故意无效的 `response_format` 返回已脱敏 HTTP 400，脚本报告预期 4xx 路径通过。与 DeepSeek HTTP 422 结果一致；每家目前只有一次真实错误路径样本。
- 0C 下一项是 OpenRouter `metadata --repeat 2`，每次请求会分别展示目标并要求确认，用于观察重复费用/区域信息；另需考虑 DeepSeek metadata 是否返回可核验的区域/费用数据。
- 更新 Provider 报告、追踪矩阵和任务状态后提交。

### 2026-11-08：DeepSeek 错误路径返回 HTTP 422

- 用户逐次确认 DeepSeek `error` 探测后，故意无效的 `response_format` 收到 HTTP 422；响应正文与凭据均未输出。初次脚本只接受 400，错误地把该请求记为未通过。
- `RemoteProviderError` 现安全保留 HTTP 状态码，`is_client_error` 将 4xx 识别为预期客户端错误；5xx 和无 HTTP 状态错误不计通过。测试窄回归 32 项、全量 Python 143 项、compileall、uv lock --check 均通过。
- 下一项是 OpenRouter `error`（可能计费，需独立确认），然后费用/区域重复核验。阶段 0 仍未验收。

### 2026-11-08：OpenRouter JSON 实测通过

- 用户逐次确认 `ALLOW OPENROUTER JSON 1` 后，返回 `{"phase0":"ack"}`，结构检查 True，finish_reason=`stop`。模型 `deepseek/deepseek-v4.1-flash-1017`，下游 Relace/HKG，tokens=46/36/82，服务报告费用 USD 0.000018276。
- DeepSeek JSON 仍记录为空正文、原因未知；OpenRouter 单次成功不代表稳定性。下一项为 DeepSeek `error` 探测，故意使用无效 response_format，可能计费；须用户对脚本显示的请求逐次确认。
- 已更新 Provider 报告、阶段追踪矩阵与任务清单；变更待 `git diff --check` 并提交。

### 2026-11-08：DeepSeek JSON 空正文与诊断增强

- 用户逐次确认 `ALLOW DEEPSEEK JSON 1` 后，真实请求返回空 JSON 正文，结构检查失败。旧 CLI 未打印 finish_reason、usage 或路由 metadata，因此原因无法判定；无重试。
- `RemoteCompletion` 现保留 finish_reason，JSON 探测输出 finish_reason、模型/路由、token/cost；增加本地 MockTransport 解析回归。窄回归 31 项、全量 Python 142 项、compileall、uv lock --check 通过。
- 下一步逐次确认运行 OpenRouter JSON 探测，观察结构化响应及诊断字段；不要把 DeepSeek 此次结果标记为支持或 Provider 故障定论。0C 仍未验收。

### 2026-11-08：0C 拒绝边界复核

- 本轮分别运行 DeepSeek 与 OpenRouter `deny-check`。两者均在无 Consent 情况下得到 Keychain reads=0、HTTP transport calls=0；检查未出网。证据是进程内 tripwire，不等同于操作系统级抓包。
- 下一步能力矩阵优先跑 DeepSeek JSON，再 OpenRouter JSON；每条命令会单独展示内容并要求精确确认。随后再考虑可能计费的错误路径、metadata 重复核验。阶段 0 仍未验收。

### 2026-11-08：OpenRouter 工具提案实测通过

- 用户在诊断增强后的脚本中再次独立确认 OpenRouter tools 请求。第三次探测返回 `phase0_echo_synthetic(marker=phase0-probe-ack)`，finish_reason=`tool_calls`，模型 `deepseek/deepseek-v4.1-flash-1017`，下游 Provider `Relace` / `HKG`；提案未执行。
- 前两次已授权请求返回空 proposal（第二次文本为空），原因仍未知；第三次成功证明固定配置有可用端到端路径，不代表稳定性。0C 还需两家 JSON/错误、费用和区域重复核验、拒绝后的系统级零出站证据。详见 `poc/phase0-remote-provider.md`。
- 本轮仅更新实测证据与排程文档；待执行 `git diff --check` 并提交。

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

阶段 0 POC；0B 本地语音实机验证已完成当前可执行项；0C Gateway/Agent Registry/能力注册表模拟已提交；0D 记忆存储/0F SQLCipher 兼容 POC 已提交；0G 候选权重已下载并离线评测，但产品选择/真实检索集未验收；0E SwiftUI demo 已接入 supervisor 并实测启动/握手/停止/退出清理、两轮 GUI 启停及一次真实系统认证成功（未访问钥匙串）；用户取消/拒绝、异常自动恢复/退避、锁屏/休眠和正式分发仍待验收；0H SQLCipher 崩溃/页数耗尽/WAL 恢复与备份故障注入持续补证。阶段 0 尚未验收，阶段 1 未开始。

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
