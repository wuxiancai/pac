# HANDOFF

## 当前阶段

阶段 0 POC；工作包 0B 本地语音验证进行中，已开始工作包 0C 本机 Gateway 契约。阶段 0 尚未验收，阶段 1 未开始。

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
- 用户实机反馈中文专用 ASR 模型不能识别英文；已确认模型语言边界。双语候选压缩档约 458 MB，本轮未完成下载和评估，英文识别仍未解决。
- 开始本机 Gateway POC：本机 Ollama Adapter、Loopback 校验、LocalOnlyPolicy、统一 generate/stream 契约；同机 qwen3.5:0.8b 的生成与流式 smoke 均成功，Python 全量测试 17 项通过。

## 当前限制

- 麦克风 CLI 已实现但需要用户在交互终端按回车后才会开始；本轮未执行真实采集，因此没有实际麦克风识别结果。
- 尚未验证 SwiftUI 麦克风链路、中英混合识别质量、P50/P95、资源占用、AEC、TTS 与 ASR 同时工作和锁屏/休眠处理。
- Gateway 的真实远程 Provider/能力矩阵/费用/错误/fallback 对照未开始；Consent/Policy、Keychain、静态加密、记忆和备份 POC 未开始。
- 所有产品待决策项继续保持未定；本地 ASR 模型是临时 POC 候选。

## 下一步

工作包 0B：用中英双语模型候选继续验证 ASR（当前英文未解决），并补真实麦克风结果。工作包 0C：在本机完成 Gateway 契约；真实云 Provider 只有在授权/策略设计及用户要求下才能测试。之后推进记忆/安全和集成/恢复 POC。阶段 0 验收前不得进入阶段 1。

## 交接要求

后续每阶段完成或中断时更新本文件，并在报告中列修改文件、设计、测试命令与结果、未决项和验收对照。
