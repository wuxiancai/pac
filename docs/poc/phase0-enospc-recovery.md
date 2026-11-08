# 阶段 0 POC：SQLCipher 受限卷 ENOSPC 恢复

状态：`IN_PROGRESS`。本报告记录 2026-11-07 在本机创建的 48 MiB HFS+ 与 128 MiB APFS 临时磁盘映像观察，不代表真实系统卷、外接盘或正式 App 的完整介质故障验收。

## 方法与边界

- 只在仓库 `backend/.poc-data/` 下创建临时磁盘映像和挂载点；脚本拒绝写入该根目录以外的路径，也拒绝通过符号链接逃逸。支持 `HFS+`（32–256 MiB）和 `APFS`（64–256 MiB）临时映像。
- 在映像内创建 SQLCipher + FTS5 源库，写入一条合成基线记录，并先生成独立密钥加密备份。
- 用填充文件消耗映像空间，保留约 512 KiB 后尝试插入较大的合成记录，观察数据库是否返回明确的 SQLite `SQLITE_FULL`。
- 删除填充文件后重开源库和既有备份，检查 `integrity_check`、原记录和失败事务记录。随机源库/备份密钥仅在进程内存中，不输出、不保存。
- 退出时 detach 磁盘映像并删除临时挂载目录和映像。测试只对固定临时映像填满，不写满系统卷。

## 结果

- 48 MiB HFS+ 映像成功触发 SQLCipher 写入 `OperationalError`（`SQLITE_FULL`）；源库事务回滚，合成溢出记录未提交。
- 重开源库：`integrity_check=ok`，基线记录 1 条，溢出记录 0 条。
- 重开先前生成的加密备份：`integrity_check=ok`，基线记录 1 条。
- 填充文件写入 48,562,176 bytes。脚本 JSON 只输出状态、异常类型和行数/完整性统计，不输出记录正文或密钥。
- macOS 端到端自动化测试覆盖此 bounded image 路径；另有路径约束、符号链接逃逸和错误分类单元测试。
- 新增 128 MiB APFS 映像验证：实际触发 SQLCipher `SQLITE_FULL`；源库与先前独立密钥加密备份完整，失败记录未提交。填充器在 APFS 写到可用空间边界时观察到文件级 `ENOSPC`，现按该错误正常结束填充，再单独验证数据库写入失败；成功写入填充数据 129,499,136 bytes。APFS 和 HFS+ 均由自动化子进程测试运行。
- 新增备份复制目标 ENOSPC 场景：128 MiB APFS 临时映像中先生成独立密钥旧备份，再扩展源库至 11,743,232 bytes、将映像填至剩余约 4 MiB，真实备份 staging 收到 SQLCipher `database or disk is full`。释放填充文件后，源库的基线和 12 条合成扩展记录仍在，旧备份仍可用旧密钥解密并检索基线，两者 `integrity_check=ok`，失败 staging 已清理。仅表示本机有界映像结果，不代表真实目标卷、外接盘或断电行为。

## 复现

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security python scripts/run_sqlcipher_enospc_poc.py --image-size-mb 48
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security python scripts/run_sqlcipher_enospc_poc.py --filesystem APFS --image-size-mb 128
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security python scripts/run_sqlcipher_enospc_poc.py --scenario backup-copy --image-size-mb 128
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security pytest -q tests/test_sqlcipher_enospc_poc.py
```

## 限制与未决项

- HFS+ 与 APFS 临时 disk image 的 ENOSPC 是有界文件系统分配耗尽，但不能代表实际 APFS 系统卷、外接盘、网络文件系统、WAL 并发写入或正式 App 数据目录的所有行为。
- 本报告的满卷映像已验证 SQLCipher 单写事务和备份复制目标 ENOSPC 后的旧备份保全；后者使用本机 APFS 临时映像，见 `phase0-failure-recovery.md`。真实系统卷/外接备份目标满载、断电、设备移除、文件系统损坏或映像挂载/卸载中断仍未验证。
- 测试密钥是临时随机值，未评估 Keychain 生命周期、密钥轮换、备份密钥分离用户流程或丢失密钥恢复。
- 本 POC 不改 schema，不执行 Alembic migration，也不形成静态加密方案 ADR。
