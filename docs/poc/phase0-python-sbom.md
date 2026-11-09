# 阶段 0 POC：Python 锁定依赖 SBOM（工作包 0G）

生成日期：2026-11-09。SBOM 以 `backend/uv.lock` 为输入，覆盖本项目 Python 基础依赖、所有可选 extras（`phase0-security`、`phase0-embedding`）和 `dev` 依赖组。

## 产物与复核

- CycloneDX 1.5 JSON：[`phase0-python-sbom.cdx.json`](phase0-python-sbom.cdx.json)
- 生成工具：uv 0.11.17；格式导出目前使用 `sbom-export` preview feature。
- 依赖覆盖核对：锁文件 55 个非根包与 BOM 的 55 个 component 的 `(name, version)` 集合完全相同；BOM 有 56 个依赖图节点（含项目根）。
- `uv.lock` SHA-256：`735d574aefd982525eb28ab397e8e079357e58fc11c5d3e4b7ab3d98b9817eba`
- 本次 SBOM SHA-256：`3b87f48363873835d8b7f9a78f07364d632b0ad7ca1da0da06cfdc1ec82072cc`

复现命令（从 `backend` 目录）：

```bash
UV_CACHE_DIR=.poc-data/uv-cache uv export \
  --locked \
  --format cyclonedx1.5 \
  --all-extras \
  --all-groups \
  --preview-features sbom-export \
  --output-file ../docs/poc/phase0-python-sbom.cdx.json >/dev/null
```

复核时已解析 JSON、检查 CycloneDX 1.5 标识，并使用 Python `tomllib` 对比 `uv.lock` 的包名/版本集合；55/55 非根依赖匹配。`uv lock --check` 通过，导出过程未修改 lockfile。

## 2026-11-09 可复现性复核

- 使用同一锁文件重新执行上方 `uv export`，临时输出写入忽略目录 `.poc-data/phase0-python-sbom-recheck.cdx.json`；解析临时清单、`uv.lock` 和仓库 BOM 后，CycloneDX `specVersion=1.5`，排除 editable 项目根包后，55 个锁定包与 55 个组件完全匹配；新旧 BOM 的 `(name, version)` 集合完全一致。
- SHA-256 与本报告记录一致：`uv.lock`=`735d574aefd982525eb28ab397e8e079357e58fc11c5d3e4b7ab3d98b9817eba`；仓库 BOM=`3b87f48363873835d8b7f9a78f07364d632b0ad7ca1da0da06cfdc1ec82072cc`。导出没有改动锁文件或仓库 BOM；临时核对文件随后删除。
- 复现命令：

```bash
UV_OFFLINE=1 UV_CACHE_DIR=.poc-data/uv-cache uv export \
  --locked --format cyclonedx1.5 --all-extras --all-groups \
  --preview-features sbom-export \
  --output-file .poc-data/phase0-python-sbom-recheck.cdx.json >/dev/null
```

## 范围与限制

- 这是完整的 **Python 锁定依赖清单**，不包含 Swift Package 依赖、macOS/Xcode 系统组件、下载的模型权重、模型 tokenizer/词表、测试音频或其他外部运行时资产。
- uv 生成的组件条目未附许可证字段，故该 BOM 本身不构成许可证闭包。当前平台已安装包的 metadata 有 50 项提供许可证标识（包括 `License`/`License-Expression` 字段或 Trove license classifier）；另检查 `py-rust-stemmers`、`sqlcipher3` 的随包 `LICENSE` 文本。`tokenizers==0.23.3` 的本机 metadata 通过 Trove classifier 标注 Apache，精确 PyPI 发布页也标注 Apache Software License；对应上游仓库固定 tag 提供 `LICENSE` 文件：[PyPI 0.23.3](https://pypi.org/project/tokenizers/0.23.3/)、[上游 v0.23.3 LICENSE](https://github.com/huggingface/tokenizers/blob/v0.23.3/LICENSE)。macOS 环境未安装的 `colorama==0.4.6` 与 `win32-setctime==1.2.1`，分别由 [PyPI 固定版本页](https://pypi.org/project/colorama/0.4.6/)确认 BSD 3-Clause、[PyPI 固定版本页](https://pypi.org/project/win32-setctime/1.2.1/)确认 MIT。新增 `websockets==17.4` 的本机 metadata 无许可证字段；其[精确 PyPI 发布记录](https://pypi.org/project/websockets/17.4/)标注 SPDX `BSD-3-Clause`。当前 55 个锁定非根包均有初步许可证来源线索；仍需审查许可证适用范围、通知义务、原生依赖和发行打包内容，这不是法律批准。
- `phase0-embedding` 模型权重许可、ASR 模型/音频许可及其数据来源仍按 [`phase0-model-license-review.md`](phase0-model-license-review.md) 单独核验。D-014 仍延期，候选未被批准为产品默认项。
