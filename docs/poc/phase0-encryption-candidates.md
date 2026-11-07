# 阶段 0 POC：静态加密候选方案对照

状态：`IN_PROGRESS`。本报告补充 ADR-019 的候选证据，**未作产品选型**；SQLCipher 继续是已验证候选，不是已冻结的 V1 依赖。

## 候选对照

| 候选 | 数据库/FTS访问方式 | 当前证据 | 主要待验证项 |
| --- | --- | --- | --- |
| SQLCipher Community | 透明加密 SQLite 页面；SQLCipher 文档说明 WAL 与 rollback journal 页面也使用数据库密钥加密。当前仓库已在 Apple Silicon/Python 3.12 验证 SQLCipher、FTS5、SQLAlchemy、Alembic、独立密钥备份恢复、WAL 和故障注入。 | 本机临时 POC 有实际测试证据；详见 `phase0-sqlcipher-compat.md` 和 `phase0-failure-recovery.md`。 | 产品 Keychain 密钥生命周期、WAL 并发策略、macOS App 打包/签名、其他平台兼容、实际负载性能；Community 版本分发须包含许可证与版权通知。 |
| SQLite SEE | SQLite 官方加密扩展，可读写加密数据库；可将 SEE amalgamation 编译为应用使用的 SQLite。SQLite FTS5 可通过编译选项加入，但本项目尚未对 SEE 构建或测试 FTS5。SEE 官方资料说明源码仅向 licensee 提供，需单独许可。 | 仅第一方资料调查，无本机集成或密钥/备份/迁移测试。 | 许可采购和交付条件、Apple Silicon 构建、Python/SQLAlchemy/Alembic 绑定、FTS5、加密备份与恢复、性能。 |
| CryptoKit AES.GCM 加密容器 | Apple CryptoKit 提供 AES-GCM 密封与认证解封 API。它本身不是 SQLite 的透明加密 VFS；若把整个 SQLite 文件作为加密容器，SQLite 查询/FTS 不能直接对密文执行。**推论**：要保留标准 SQLite 随机访问，需要另行实现并审计加密 VFS，或设计受控明文工作副本及其清理/崩溃语义。 | 仅第一方 API 文档调查；未实现容器、VFS 或明文工作副本。 | 完整性/随机访问设计、明文临时数据生命周期、并发/崩溃恢复、FTS5/迁移、性能、备份密钥生命周期。 |

## 依据与边界

- SQLCipher 将数据库页面透明加/解密，并在 WAL 与 rollback journal 中加密页面；Community 版分发需包含许可证及版权通知。[SQLCipher 设计说明](https://www.zetetic.net/sqlcipher/design/)、[SQLCipher Community 许可说明](https://www.zetetic.net/sqlcipher/license/)。
- SQLite SEE 的官方构建说明介绍了 SEE 替换 SQLite amalgamation 的集成方式；其官方站点说明源码需要 licensee 账号。FTS5 是 SQLite 编译时可启用的扩展，但 SEE + FTS5 在本机的兼容性尚未实测。[SEE 编译与许可说明](https://www.sqlite.org/see/doc/release/www/readme.wiki)、[SQLite FTS5 编译选项](https://www.sqlite.org/compile.html#enable_fts5)、[SEE 源码访问说明](https://www.sqlite.org/see/doc/release/www/index.wiki)。
- Apple CryptoKit 文档定义 AES.GCM 的密封与解封 API；将其包装为 SQLite 文件存储并支持随机页访问的困难是本项目的工程推论，不是 Apple 对 SQLite 的声明。[Apple CryptoKit AES.GCM](https://developer.apple.com/documentation/cryptokit/aes/gcm)。
- 规格书要求应用层静态保护、密钥与备份分离，且 FileVault 不能替代应用级保护。本报告不改变该要求，不把任何候选的算法文档当作 Keychain/授权/备份生命周期的完成证据。

## 暂定结论

SQLCipher 是目前唯一完成本机 FTS5、ORM/migration、加密备份恢复及部分故障注入的候选；这说明它拥有最多本项目实测证据，**不等于已选定**。SQLite SEE 需要先确认许可和构建成本；CryptoKit 容器需要先证明随机访问、明文临时数据和崩溃恢复设计可满足基线。ADR-019 仍 `Deferred / POC Required`，V1 加密方案须在候选验证、密钥生命周期、性能与发布形态证据齐备后再确认。

## 下一步验证

1. 不下载/引入其他实现前，先完成当前 SQLCipher POC 的 macOS 打包、WAL 并发/备份、密钥生命周期与性能缺口盘点。
2. 若产品负责人认为 SEE 有商业/许可评估价值，再单独建立授权和构建 POC；未获许可不拉取受限源码。
3. CryptoKit 容器/VFS 仅在形成明文临时文件、随机访问、崩溃恢复及密钥边界设计后再开 POC。

阶段 0 和 ADR-019 均未因此通过；不得据此进入阶段 1。
