# 阶段 0 POC：SQLite/SQLCipher 合成工作负载对照

状态：`IN_PROGRESS`。本报告只记录 2026-11-07 本机观察值，不设产品阈值，不构成 ADR-019 选型或性能承诺。

## 方法

- 设备：Apple M1 MacBookAir10,1，16 GiB，macOS 26.5.1；Python 3.12；SQLite 3.50.4；SQLCipher 4.12.0 Community。
- 对照：普通 SQLite + FTS5 与 SQLCipher + FTS5；两边均使用相同的临时 `poc_memories`/`poc_memories_fts` 结构和确定性合成文本。
- 每轮写入 2,000 条、约 788 字符的合成记录，执行 100 次分词命中 FTS5 查询；每条查询均返回非空结果。
- 连续测量 3 轮，每轮都新建数据库；不控制或清理系统文件缓存。写入计时包含 Python 合成内容生成和事务内 memory/FTS 插入；查询计时包括查询字符串生成和 `count(*)`。
- 备份计时两端都包含数据库备份 API、同目录 staging、完整性检查、关闭连接和原子替换；SQLCipher 备份使用独立临时密钥。每轮临时数据库/备份在报告生成后删除，stdout 不含记录正文或密钥。

## 观察结果

| 指标 | SQLite + FTS5 | SQLCipher + FTS5 |
| --- | ---: | ---: |
| 2,000 条写入（每轮范围） | 15.50–18.09 ms | 25.91–26.39 ms |
| 100 次 FTS5 查询（每轮范围） | 1.129–1.594 ms | 1.181–1.239 ms |
| 校验并替换备份（每轮范围） | 14.33–15.08 ms | 148.58–290.26 ms |
| 源数据库文件大小 | 3,584,000 bytes | 3,616,768 bytes |
| 备份文件大小 | 3,584,000 bytes | 3,616,768 bytes |
| 查询成功数 | 每轮 100/100 | 每轮 100/100 |

备份路径的 SQLCipher 范围波动较大，保留三轮范围，不选取单值或据此推算倍数。数据库体积只有本合成记录结构的观察值。

## 复现

```bash
cd backend
UV_CACHE_DIR=.poc-data/uv-cache TMPDIR=.poc-data/tmp uv run --locked --extra phase0-security python scripts/benchmark_sqlcipher_poc.py --records 2000 --queries 100 --repeats 3
```

## 限制与未决项

- 小型合成工作负载、同一台机器、连续三轮；未控制冷/热缓存，也未测量 CPU、RSS、并发 writer/reader、WAL、长期运行、Embedding 或实际用户数据。
- SQLite 是未加密性能基线，不是可替代的安全产品候选。两端备份流程具备 staging/校验/replace，但 SQLCipher 端还包含加密与密钥处理，因此结果只描述此 POC 实现的端到端用时，不分离加密算法成本。
- 尚无用户确认的 P50/P95、吞吐或启动时限门槛，不据此判断产品可接受性；没有评估 SEE 或 CryptoKit 容器性能。
- SQLCipher 仍是已验证候选，不是已冻结决策；ADR-019 未定案。Keychain 密钥生命周期、打包、真实 ENOSPC、断电和外接盘/NAS 仍需独立验证。

本机结果支持继续做候选验证，不能替代目标设备/真实数据负载验收。
