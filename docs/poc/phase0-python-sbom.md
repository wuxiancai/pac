# 阶段 0 POC：Python 锁定依赖 SBOM（工作包 0G）

生成日期：2026-11-08。SBOM 以 `backend/uv.lock` 为输入，覆盖本项目 Python 基础依赖、所有可选 extras（`phase0-security`、`phase0-embedding`）和 `dev` 依赖组。

## 产物与复核

- CycloneDX 1.5 JSON：[`phase0-python-sbom.cdx.json`](phase0-python-sbom.cdx.json)
- 生成工具：uv 0.11.17；格式导出目前使用 `sbom-export` preview feature。
- 依赖覆盖核对：锁文件 54 个非根包与 BOM 的 54 个 component 的 `(name, version)` 集合完全相同；BOM 有 55 个依赖图节点（含项目根）。
- `uv.lock` SHA-256：`b201746ba92d2ec757b88c7d21e5a3cc5491b419e251da289f8c3b651f20a895`
- 本次 SBOM SHA-256：`a00b2181a8d33ff23e9969e090d69f9b9a9ad32b5a8cbd27dad38a9a55af14de`

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

复核时已解析 JSON、检查 CycloneDX 1.5 标识，并使用 Python `tomllib` 对比 `uv.lock` 的包名/版本集合；54/54 匹配。`uv lock --check` 通过，导出过程未修改 lockfile。

## 范围与限制

- 这是完整的 **Python 锁定依赖清单**，不包含 Swift Package 依赖、macOS/Xcode 系统组件、下载的模型权重、模型 tokenizer/词表、测试音频或其他外部运行时资产。
- uv 生成的组件条目未附许可证字段，故该 BOM 本身不构成许可证闭包。当前平台已安装包的 metadata 有 50 项提供许可证标识；另检查 `py-rust-stemmers`、`sqlcipher3` 的随包 `LICENSE` 文本。macOS 环境未安装的 `colorama==0.4.6` 与 `win32-setctime==1.2.1`，分别由 [PyPI 固定版本页](https://pypi.org/project/colorama/0.4.6/)确认 BSD 3-Clause、[PyPI 固定版本页](https://pypi.org/project/win32-setctime/1.2.1/)确认 MIT。54 个锁定包现均有一个初步许可证来源线索；仍需审查许可证适用范围、通知义务、原生依赖和发行打包内容，这不是法律批准。
- `phase0-embedding` 模型权重许可、ASR 模型/音频许可及其数据来源仍按 [`phase0-model-license-review.md`](phase0-model-license-review.md) 单独核验。D-014 仍延期，候选未被批准为产品默认项。
