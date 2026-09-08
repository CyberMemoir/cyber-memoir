# Cyber Memoir / 赛博回忆录

## Architecture overview

面向人类和 AI 的中文互联网文化记忆基础设施。保存梗、来源、语境、时间线、衍生关系和证据，不建设视频搬运站。

采用 **Next.js + FastAPI 模块化单体 + 异步 Worker**。MCP 是同一应用用例的只读协议适配，Search / RAG 不拆成微服务。Docker Compose 优先。

```text
人类 → Web → HTTP API ──┐
                       ├→ application / domain → PostgreSQL
AI   → MCP ────────────┘           ├→ Search → OpenSearch + pgvector + Relation
                                   └→ RAG → 审核断言 + Evidence

URL → 持久任务/Outbox → Redis 提示队列 → Worker → 材料 → 候选 → 人审 → 发布 → 索引
```

### Source of truth

| 存储 | 分工 |
|---|---|
| PostgreSQL | 六类核心对象、证据登记、公开修订、审核、关系、任务/Outbox；结构化状态的唯一权威来源 |
| pgvector | 1024 维 BGE-M3 dense 向量、模型标识；派生数据，可重建 |
| OpenSearch | CJK + BM25、字段权重、平台/时间过滤；可重建投影 |
| Redis | 任务提示、限流；丢失不能导致业务任务丢失，不缓存事实回答 |
| S3-compatible Object Storage | 持久证据工件；内容寻址，保存 SHA-256，与 PostgreSQL 一并备份 |

人工审核确认的是“这份证据是否支持这条断言”，不是承诺全网历史完整。AI 不凭模型记忆认定起源。

## Repository structure

```text
apps/web/                         Next.js / TypeScript：索引、提交、审核、详情
apps/backend/src/cyber_memoir/
  domain/                         核心模型、输入与输出 schemas
  application/                    提交、草稿、审核、发布、撤回、合并
  api/                            HTTP、鉴权、请求限制
  ingestion/                      URL、元数据、字幕、ASR、OCR、候选提取
  search/                         索引、召回、融合、一跳关系、重排
  rag/                            审核断言选择、引用约束、回答组装
  mcp/                            官方 MCP SDK 的只读适配
  workers/                        Outbox 调度、执行、租约、重试
  adapters/                       模型、对象存储
apps/backend/migrations/          Alembic 版本迁移
packages/contracts/              导出的 OpenAPI 和生成的 TS 类型
tests/                           领域、HTTP、MCP、任务及真实服务集成测试
apps/web/e2e/                     隔离数据的浏览器验收
evals/                           检索与引用评测
docs/adr/                        架构决策
docs/design/                     界面参考和视觉验收记录
ops/compose/                     单机基础设施与应用部署
```

## Core data flow

1. **提交 URL**：仅接受 Bilibili / 抖音视频 HTTPS URL；短链逐跳验证；平台 + 内容 ID 去重；B站分 P 保留独立标识和链接。Source 和任务在同一事务登记。
2. **metadata / subtitle**：平台材料适配器获取元数据及可用字幕；SRT、VTT、平台 JSON 规范化为带时间位置的 Evidence。平台失败转 `needs_material`，不伪装成功。
3. **ASR / OCR**：支持人工提交媒体；可选 `AUTO_MEDIA` 在受大小/时长限制的临时视频上执行 Whisper 和抽帧 OCR。完整媒体不进入长期工件库；OCR 帧保留真实 PTS。
4. **meme extraction**：模型仅生成待审候选及证据 ID；未配置模型时生成明确标记的待人工填写草稿，不虚构含义。
5. **review**：核对文字、定位、完整字段支持关系、事件时间和衍生关系。新证据需显式人工确认；有起源主张时需专门 origin 引用和 Source 关系。
6. **indexing**：发布写入持久任务/Outbox；Worker 构造有重叠的 Evidence chunks，生成向量，更新 OpenSearch。稳定文档 ID、修订号和行锁防止旧任务覆盖新事实。
7. **hybrid retrieval / reranking**：多路召回、RRF、一跳关系、当前版本/权限回查、BGE Reranker、按 Meme 聚合。
8. **RAG answer with evidence**：输出已审核断言、证据引用、平台 URL、定位、版本和不确定性；无证据不作来源判断。

### 状态与一致性

- 修订：`pending_review → published / rejected`；已发布条目可 `retracted / merged`。
- 修改先生成 Revision，批准后原子切换 `published_revision`；旧修订及引用保留。
- PostgreSQL `Job` 同时承担小型事务 Outbox 和持久任务状态；Redis 仅加速传递。
- 队列至少一次执行，任务幂等。进程退出后的租约可恢复；失败退避重试，终态失败可人工重试。
- 异步索引最终一致，但读取必须检查 PostgreSQL 当前发布状态。撤回先阻断读取，再清理投影。
- 原始 Evidence 不原地改写；纠错新增 Evidence，使用 `supersedes_id` 关联。撤回证据同时撤回依赖的公开条目。

## Core schemas

| 模型 | 核心字段/约束 |
|---|---|
| Meme | 名称、别名、规范化检索键、定义、语境、origin_status、status、published_revision、merged_into_id |
| Source | platform + platform_item_id 唯一、原始/规范链接、标题、作者 Entity、平台发布时间、availability |
| Evidence | source_id、kind、text、locator、artifact_key、content_hash、artifact_hash、extraction_provenance、verified、retracted、supersedes_id |
| Event | meme_id + revision、类型、描述、时间起止/精度/依据；日期可以未知 |
| Entity | 人物、平台账号、作品、社群等类型、名称、别名、平台标识 |
| Relation | 所属 Meme 修订、predicate、目标 Meme / Source / Entity 三选一的受约束外键、assertion_status |

辅助表：Alias、EvidenceLink、Revision、Chunk、Job。

EvidenceLink 记录 `claim_key + statement + supports/contradicts + evidence_id`，并可关联 Event / Relation。定义和语境必须有覆盖完整字段的支持性引用。数据库外键防止悬空关系；发布用例检查关系端点类型。

`Source.created_at` 是首次登记时间，`Evidence.created_at` 是该证据采集/登记时间；与 `platform_published_at`、Event 发生时间严格区分。`content_hash` 校验规范化证据记录，`artifact_hash` 校验工件字节。

## Service boundaries

| 模块 | 负责 | 不负责 |
|---|---|---|
| Frontend | 产品界面、表单、进度、证据展示 | 直接访问存储或判断起源 |
| Backend | 领域规则、鉴权、审核、版本与应用用例 | HTTP 请求内运行长时媒体处理 |
| Ingestion | 解析、采集、识别、候选 | 自动发布、无依据归因 |
| Search | 召回、过滤、融合、图扩展、重排 | 生成文化事实 |
| RAG | 审核断言选择、引用校验、回答、不确定性 | 把模型输出当成新证据 |
| MCP | 只读工具、结构化输出 | 独立业务规则、任意 SQL/抓取/审核发布 |

### Search

`Exact/Alias + OpenSearch BM25 + pgvector → RRF → PostgreSQL 一跳关系扩展 → 当前状态回查 → BGE Reranker`。

- 精确别名直接查 PostgreSQL，发布后无需等异步索引；同名条目不强行合并。
- Evidence chunk 是跨通道稳定检索单元；BM25 文档包含经审核的梗名、定义和语境。最终按 Meme 聚合，避免两套排序单位漂移。
- 精确匹配权重提升；BM25 与向量原始分数不直接相加。
- 图扩展限已审核 `derived_from / variant_of`、一跳、有限候选；邻接不等于因果。
- 单 Source 候选限额；全部通道使用一致的平台和平台发布时间过滤。
- 暂用精确向量查询，实测瓶颈后再启用 HNSW。换模型必须重建向量，不混用向量空间。
- 模型或检索通道不可用时返回 `degraded`；不返回伪造的向量命中或重排分数。

### API / MCP

HTTP `/v1` 提供提交、材料、任务、内容、检索、问答及受保护的审核接口；以 OpenAPI 为契约。

MCP `/mcp/` 使用 Streamable HTTP；工具为 `search_memes`、`get_meme`、`get_evidence`、`get_timeline`、`get_relations`、`answer_question`。输出经过与 HTTP 相同的 schemas 和发布规则。

## V1 scope / non-goals

V1 包含人工 URL 提交、材料补充、识别适配器、候选、审核、发布、撤回、合并、版本、混合检索、时间线/关系、证据回答、只读 MCP、Compose、测试与备份恢复。

不做：全站爬虫、推荐流追踪、热点自动发现、视频镜像、全量评论弹幕、AI 自动发布、全网起源保证、复杂 GraphRAG、自训模型、社交社区、Kubernetes、Neo4j、Kafka、跨地域高可用。

## Key architecture decisions

1. **Evidence First**：不知道就记录未知；“本库最早可验证记录”不等于“互联网起源”。
2. **模块化单体**：只有 Web / API / Worker 三类应用进程，模型按配置启用。
3. **单一结构化权威**：PostgreSQL 决定公开状态；搜索、向量、缓存均非事实源。
4. **事实锁定的 RAG**：V1 使用 LLM 选择已审核断言、确定性组装回答，不任意改写。模型失败回退到引用型摘录。
5. **薄适配器**：ASR、OCR、Embedding、Reranker、LLM 可替换；不提前建设插件平台。
6. **受限图模型**：V1 关系由 Meme 修订拥有；跨 Source 的通用传播图是后续扩展，而不是引入图数据库的理由。
7. **不缓存事实回答**：先减少撤回失效面，未来有数据证明收益后再增加缓存。
8. **简化索引恢复**：V1 支持全量重排队重建；未来扩展为版本化索引和别名原子切换。

实现边界、运行配置及未进行真实模型验收的部分见 [README](README.md) 和 [验证记录](docs/VERIFICATION.md)。
