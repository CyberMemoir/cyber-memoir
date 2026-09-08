# Cyber Memoir / 赛博回忆录

**记住一个梗，也记住它从哪里来。**

面向人类与 AI 的中文互联网文化记忆与检索基础设施。第一阶段支持 **Bilibili、抖音**，保存梗、语境、来源、传播事件、衍生关系和证据，不托管完整视频。

> V1 alpha：可运行的人工提交—审核—检索闭环。默认空库，不预装虚构文化事实。模型能力按配置启用，平台可获取性及中文模型效果需要部署者用真实样本验收。

## 可以做什么

- 提交视频 URL、展开平台短链、去重、查看任务状态。
- 获取可用元数据/字幕，或人工补充定位摘录、字幕、截图、短媒体材料。
- Whisper ASR / PaddleOCR、BGE-M3 embedding、BGE reranker、兼容 Chat Completions 的 LLM 适配器。
- 人工编辑和审核候选；完整字段引用、显式证据核查、版本冲突检查。
- 名称/别名 + BM25 + Vector + 一跳关系扩展 + Reranker。
- 来源、语境、时间线、关系、证据工件下载；条目合并、撤回和证据级撤回。
- 只使用已审核断言的引用型回答，以及六个只读 MCP 工具。
- Docker Compose、Alembic、持久任务/Outbox、重试、索引重建、备份恢复和自动化测试。

## 快速启动

需要 Docker / Docker Compose、Python 3；首次镜像构建需要联网。

```bash
git clone https://github.com/CyberMemoir/cyber-memoir.git
cd cyber-memoir
make configure   # 生成独立密码和审核令牌，不覆盖已有 .env
make up
```

| 服务 | 地址 |
|---|---|
| Web | http://localhost:3100 |
| API 文档 | http://localhost:8100/docs |
| MCP | http://localhost:8100/mcp/ |
| MinIO 管理界面 | http://localhost:59001 |

审核工作台使用 `.env` 中的 `REVIEWER_TOKEN`；令牌只保存在当前页面内存，不写入浏览器存储。`SUBMITTER_TOKEN` 为空时允许公开提交，但公开索引仍必须经过审核。

所有映射端口默认只绑定 `127.0.0.1`；该 Compose 是单机部署基线，公网服务需另外配置 TLS、网关、访问策略和备份目的地。OpenSearch 安全插件仅在这个本地网络基线中关闭。

## 第一次使用

1. 打开「提交来源」，登记 B站或抖音视频链接。
2. 平台材料不完整时，补充原文及时间定位/核查说明；不会绕过平台访问限制。
3. 打开「审核工作台」，填写令牌，编辑名称、定义、别名和语境，勾选支持它们的证据。
4. 填写审核理由并确认已核查证据，批准发布。
5. 返回索引页搜索。勾选「基于证据回答」获得有引用的回答。

未配置 LLM 时，提取阶段建立待人工填写的草稿；**不会自行生成梗含义**。未配置 BGE 时，实际启用的通道与降级原因会出现在搜索响应中。

## 启用模型

默认轻量镜像不携带大型模型权重；文字材料、审核、BM25、别名查询、关系和引用型回答无需模型密钥即可工作。

在 `.env` 中设置：

```dotenv
INSTALL_MODELS=true
EMBEDDING_BACKEND=local
RERANKER_BACKEND=local
ASR_MODEL=small
# 可选：无字幕时临时获取受限大小的视频，执行 ASR / 抽帧 OCR
AUTO_MEDIA=false
```

再运行 `make up`。模型会在第一次调用时下载；需足够内存、磁盘及可访问的模型仓库。启用向量后，在审核工作台执行「重建搜索索引」。生产环境应使用固定模型快照/本地模型路径，并记录版本；改变模型路径后重建索引。

可选 LLM 配置：`LLM_BASE_URL`（以 `/v1` 结尾的兼容端点）、`LLM_MODEL`、`LLM_API_KEY`。不配置时仍可使用审核断言摘录型回答；配置后模型只负责候选提取及已审核断言选择。密钥只放部署环境，不提交 Git。

自动媒体分析默认关闭，上限为 **16 MiB / 15 分钟**，最多抽取 **10 帧**；不是全量视频归档。手工上传音视频也只临时处理。FunASR、独立模型服务、GPU 调度可后续替换薄适配器，V1 默认 ASR 为 faster-whisper。

## 本地开发

需要 Node.js 22、[uv](https://docs.astral.sh/uv/)。

```bash
make configure                 # 仅首次执行
make infra
cd apps/backend
uv sync --python 3.12
uv run --env-file ../../.env alembic upgrade head
uv run --env-file ../../.env uvicorn cyber_memoir.api.main:app --host 127.0.0.1 --port 8100
```

另两个终端分别运行：

```bash
cd apps/backend
uv run --env-file ../../.env python -m cyber_memoir.workers.main
```

```bash
cd apps/web
npm ci
npm run dev
```

避免同时运行占用 3100/8100 端口的容器应用和本地开发进程。

## 测试与契约

```bash
make test                       # 单元/HTTP/MCP 测试；真实服务测试默认跳过
make check                      # Python lint、格式、TypeScript、Next.js build
make contracts                  # 导出 OpenAPI 并生成前端 TS 类型
cd apps/web && npx playwright test  # 自动启动独立临时测试后端和 Web
```

真实服务集成验收：

```bash
make infra && make migrate
cd apps/backend
MEMOIR_INTEGRATION=1 uv run --env-file ../../.env pytest -q ../../tests/test_live_stack.py
```

集成测试在独立 PostgreSQL schema、OpenSearch index 和 S3 bucket 内运行，结束后清理。它用**合成向量验证真实 pgvector 通路**，不冒充 BGE 模型效果评测。浏览器测试仅使用临时目录中的合成材料，不写部署数据库。

## API / MCP

HTTP API 以 `/v1` 为前缀；契约见 [OpenAPI](packages/contracts/openapi.json)。审核接口使用 `Authorization: Bearer <reviewer-token>`。

MCP 使用 Streamable HTTP，连接 `http://localhost:8100/mcp/`：

```text
search_memes(query, platform?, limit?)
get_meme(meme_id)
get_evidence(evidence_id)
get_timeline(meme_id)
get_relations(meme_id)
answer_question(question, platform?)
```

所有工具只读，返回结构化数据。客户端若使用远程域名，需要在服务端 MCP Host/Origin 白名单中显式允许该域名，不应关闭 DNS rebinding 防护。

## 数据和运维

- PostgreSQL 是结构化事实/审核状态的唯一权威来源；Object Storage 保存证据字节。
- Redis、OpenSearch、向量索引可重建，不作为唯一备份。
- 任务失败与重试见 API；查看运行日志：`make logs`。
- 备份与恢复步骤：[OPERATIONS.md](docs/OPERATIONS.md)。
- 原平台失效时仍标识来源状态和已保存的证据版本，不补造历史。
- 代码 MIT 开源；第三方平台材料与模型权利不随代码许可证转授。

## 文档

[架构](ARCHITECTURE.md) · [关键决策](docs/adr/0001-evidence-first.md) · [验证记录与边界](docs/VERIFICATION.md) · [贡献指南](CONTRIBUTING.md)
