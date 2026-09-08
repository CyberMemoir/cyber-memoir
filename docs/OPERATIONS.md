# 单机运维

## 启动和状态

`make up` 启动 PostgreSQL、Redis、OpenSearch、MinIO、迁移、API、Worker 和 Web。数据在独立的 `cyber-memoir_*` Docker volumes 中；普通 `make down` 不删除 volumes。

```bash
docker compose --env-file .env -f ops/compose/compose.yml ps
make logs
```

`/health/live` 检查进程，`/health/ready` 检查数据库连接。索引及模型是可降级通道，不应因为单一通道故障把整个 API 判为死亡。

## 任务与索引

- Job 保存 `pending/running/succeeded/failed`、尝试次数、运行时间和错误类型。
- 失败最多自动尝试 3 次，延迟退避；超过租约可重新领取。
- Redis 不可用时 Worker 使用 PostgreSQL 轮询继续执行。
- 媒体失败后临时文件清理；重新上传而不是重试已清理的媒体。
- `POST /v1/jobs/{id}/retry` 需要审核令牌，支持终态失败的非媒体任务。
- 审核工作台「重建搜索索引」或 `POST /v1/reviews/reindex` 从 PostgreSQL 重新排队。模型变更后同样执行。
- 重建期间可以短时降级；V1 尚不提供新索引别名原子切换。

## 备份

在 **Compose 部署** 中运行，先停止额外的本地开发 API/Worker：

```bash
make backup
```

脚本暂停正在运行的 API/Worker，导出 PostgreSQL custom-format dump、内容寻址证据对象及 SHA-256 manifest，再恢复原先运行的应用进程。备份在 `.data/backups/<UTC>/`，不进入 Git。

索引与 Redis 可重建，不需要作为事实备份。将备份目录复制到独立持久介质；把 `.env` 放独立的受保护配置备份中，不混入公开仓库。

## 恢复

仅支持**空的目标 PostgreSQL public schema 和空证据存储**，脚本不会清空已有数据。

1. 在新环境生成 `.env`，启动基础设施（`make infra`），构建应用镜像，不运行迁移。
2. 运行 `bash ops/restore.sh /absolute/path/to/backup`。
3. `make up`，检查 Alembic 版本与就绪状态。
4. 审核工作台重建搜索索引；核查至少一个来源、一个 Evidence 哈希、一次问答引用。

若恢复中断，保留现场并在另一个空环境重新恢复；不默认覆盖已恢复了一部分的证据对象。

## 模型与媒体

模型权重不打入代码仓库；使用固定快照或本地模型目录，记录模型、硬件及处理版本。初始精确 pgvector 检索无需 HNSW；先用真实评测集证明瓶颈再添加近似索引。

所有识别任务受文件大小和执行时间限制。临时音视频任务结束即清理；服务崩溃时仍可能留下孤立临时对象，应对 `temporary/` 配置 1 天生命周期清理。正常证据 `sha256/` 不适用临时清理规则。

## 网络和身份

Compose 只绑定本机，未配置公网 TLS。对外提供服务时配置网关、域名、CORS、MCP Host/Origin 白名单、合理的用户级限流和独立的提交/审核凭据。V1 是单审核令牌模型，不宣称具备企业级多租户权限。

URL 入口限制平台与 HTTPS；重定向逐跳校验，阻断非公网地址。平台采集容器还应使用限制内部网段的出站策略作为第二道边界；应用级 DNS 检查不是网络隔离的替代。

## 上线前人工验收

- 选择允许处理的 B站、抖音真实来源，分别检验字幕、缺字幕、失效页面。
- 核对 ASR/OCR 的时间定位及识别误差；不能把测试夹具结果算作模型效果。
- 建立包含别名、多义、来源争议、无答案查询的人工金标准集。
- 演练备份恢复、撤回后的索引可见性、进程中断和 Redis 丢失。
