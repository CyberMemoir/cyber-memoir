# 实际已批准归档：隔离端到端评测

2026-10-10，先只读捕获正在运行的本地业务栈，再在独立 PostgreSQL/OpenSearch 上恢复快照，运行当前生产检索与回答代码。不是将 `resolved` 标记或合成夹具当作实际发布，也没有启动评测 Worker、增加文化审批、重启业务服务或迁移业务库。

## 结果

同一快照：**14 个公开条目、54 份证据、143 个 dense chunk**。独立人工描述中只有 **14 条**目标实际公开；另外 **14 条**因目标未发布而明确排除，不伪装成检索失败。原文件中的 **11 条负例**全部保留。查询与目标来自独立输入，不从模型回答反推。所有模式均完整完成 25 个用例。

| 模式 | Recall@10（正例） | MRR（正例） | 回答含目标身份 | 正确弃答（负例） |
|---|---:|---:|---:|---:|
| BM25/关系，模型关闭 | 13/14 | 0.8274 | 13/14 | 4/11 |
| 上述检索 + 实际 reranker | 13/14 | 0.8214 | 6/14 | 11/11 |
| 上述检索 + 实际 BGE-M3 + reranker | 14/14 | 0.8512 | 8/14 | 11/11 |

**结论是覆盖率提升、回答仍有缺口，不是“模型全面变好”。** hybrid 在六条正例上没有回答，保守的分数下限是后续诊断对象；本轮不降低下限、改写问题或篡改负例来提升指标。没有启用 LLM，回答使用已有批准断言。这个很小、已经用于开发的集合不是严格未见测试集，也不是事实正确率。

实际 CPU、4 线程、FP32，下限 `0.35`。每用例两次 POST 的合计耗时中位数：关闭模型 **0.288s**、rerank **4.943s**、hybrid **18.359s**；含冷加载，不是生产 SLA。请求起点间隔至少 1.1s，主动等待单独计入 `pacing_seconds`，不冒充模型耗时；没有放宽或绕过生产限流。

## 引用核对的边界

已对回答逐条核对条目/公开修订身份、批准的字段/文字/立场/证据绑定，以及证据的 verified/retracted、source ID、内容哈希、定位、原链接和引用文字：

| 模式 | 有回答的用例 | 绑定不匹配 | 引用记录不匹配 | 去重后待语义复核断言 |
|---|---:|---:|---:|---:|
| off | 20 | 0 | 0 | 28 |
| rerank | 6 | 0 | 0 | 14 |
| hybrid | 8 | 0 | 0 | 16 |

弃答的结构检查记 `null`，不算“完美覆盖”。这些检查只证明绑定了批准记录、引用记录没串线，**不证明原文蕴含断言、起源正确或回答切题**。`citation_audit.py` 输出 assessment/reviewer/reason 均未填写的语义复核队列；不自动批准或给文化事实打真值分。

聚合报告：[results-2026-10-10-approved-archive.json](../evals/results-2026-10-10-approved-archive.json)。包含逐用例数值、原报告 SHA、上下文、模型权重 SHA、镜像身份和输入 SHA，不包含私有待审稿、证据全文、密钥或本机目录。完整 dump、原始报告、附件和复核队列留在权限 700 的忽略目录。

## 可复现步骤

仓库根目录运行；先按 [MODEL_PROBE.md](MODEL_PROBE.md) 准备冻结模型环境和两个已验证 manifest。不要把业务 `.env` 带入评测服务。

### 1. 只读捕获与选题

```bash
cd apps/backend && uv sync --frozen && cd ../..
PY=apps/backend/.venv/bin/python
RUN=$(python3 -c 'import secrets; print(secrets.token_hex(5))')
SNAP="$PWD/.data/archive-eval-$RUN"
$PY evals/capture_archive.py --api http://127.0.0.1:8100 \
  --postgres-container cyber-memoir-postgres-1 --source-project cyber-memoir --out "$SNAP"
$PY evals/archive_gold.py --snapshot "$SNAP/public.json" \
  --descriptions evals/curation/_descriptions.yaml --negatives evals/curation/_negatives.yaml \
  --out "$SNAP/public-gold.jsonl" --selection "$SNAP/gold-selection.json"
```

捕获器只允许显式 loopback 公共 API，检查 PostgreSQL 的 Compose 项目/服务身份，用 `pg_dump -Fc --no-owner --no-acl` 的一致性快照；公开记录在捕获前后必须相同，附件逐字节校验哈希。变化时不写有效 manifest。dump 含私有稿件，只用于本地隔离恢复，不提交 Git。API 与数据库必须属于同一部署；捕获器不能仅靠公共 API 证明这一点，恢复后必须再次比对公开 DTO。

### 2. 独立恢复与索引

本机端口 **55433/59201/8103** 必须空闲。使用本次报告中的不可变本机 image ID（其它机器先获取对应镜像并核对 digest）；这里的固定口令只属于全新 tmpfs 测试库。

```bash
PG="memoir-eval-$RUN-pg"; OS="memoir-eval-$RUN-search"
PG_IMAGE=sha256:a36250871de0833b8757561c72f2477ef1ddd1101afa4e617fb552e0de514c6b
OS_IMAGE=sha256:d96afaf6cbd2a6a3695aeb2f1d48c9a16ad5c8918eb849e5cbf43475f0f8e146
docker run -d --rm --name "$PG" --label "cyber-memoir-evaluation=$RUN" \
  --memory 512m --cpus 2 --tmpfs /var/lib/postgresql/data:rw,size=1g \
  -p 127.0.0.1:55433:5432 -e POSTGRES_DB=eval -e POSTGRES_USER=eval \
  -e POSTGRES_PASSWORD=isolated-eval-only "$PG_IMAGE"
docker run -d --rm --name "$OS" --label "cyber-memoir-evaluation=$RUN" \
  --memory 1536m --cpus 2 --tmpfs /usr/share/opensearch/data:rw,size=1g,uid=1000,gid=1000 \
  -p 127.0.0.1:59201:9200 -e discovery.type=single-node \
  -e DISABLE_SECURITY_PLUGIN=true -e DISABLE_INSTALL_DEMO_CONFIG=true \
  -e 'OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m' "$OS_IMAGE"
# 等待两个新服务就绪；pg_isready 与 GET http://127.0.0.1:59201 成功后再继续。
docker exec -i "$PG" pg_restore -U eval -d eval --no-owner --no-acl < "$SNAP/postgres.dump"
DB=postgresql+psycopg://eval:isolated-eval-only@127.0.0.1:55433/eval
MODEL_PY="$PWD/.data/model-eval-venv/bin/python"
DATABASE_URL="$DB" "$MODEL_PY" -m alembic -c apps/backend/alembic.ini upgrade head
"$MODEL_PY" ops/archive_eval_server.py --snapshot "$SNAP" --run-id "$RUN" \
  --database-url "$DB" --search-url http://127.0.0.1:59201 \
  --pg-container "$PG" --search-container "$OS" --mode hybrid --index-only
```

只在新 tmpfs 库迁移；不使用业务数据库 URL，不启动 Worker。服务检查容器归属标签、实际 loopback 端口绑定、dump/模型哈希和原有批准审计；索引只重建派生数据，不能增加审批。原业务库保持旧 schema。本次恢复后的公开 DTO 与捕获快照 SHA 完全一致。

### 3. 分模式运行与检查

一次只开一种模式；前台启动以下服务，另一终端执行 runner。完成后 `Ctrl+C` 停该评测 API，再分别替换 `MODE=rerank`、`MODE=hybrid`。

```bash
MODE=off
"$MODEL_PY" ops/archive_eval_server.py --snapshot "$SNAP" --run-id "$RUN" \
  --database-url "$DB" --search-url http://127.0.0.1:59201 \
  --pg-container "$PG" --search-container "$OS" --mode "$MODE" --port 8103
# 另一终端设置相同 SNAP/MODE/PY 后：
$PY evals/run.py "$SNAP/public-gold.jsonl" --api http://127.0.0.1:8103 \
  --checkpoint "$SNAP/$MODE.sqlite" --run-context "$SNAP/context-$MODE.json" \
  --request-interval 1.1 > "$SNAP/report-$MODE.json"
$PY evals/citation_audit.py --report "$SNAP/report-$MODE.json" --snapshot "$SNAP/public.json" \
  --gold "$SNAP/public-gold.jsonl" --out "$SNAP/audit-$MODE.json" \
  --review-queue "$SNAP/semantic-$MODE.jsonl"
```

服务禁用 `.env`、LLM、Redis、自动媒体和所有写入 HTTP 路由，模型 CPU 离线运行。明确区分三个 provider：关闭模型没有虚构权重 SHA。runner 的上下文、代码和数据冻结规则见 [EVALUATION.md](EVALUATION.md)。审计拒绝错误快照、错误 gold、重复引用和未完成报告。新查询选择器已逐字节再现本次原始 gold。

### 4. 精确清理

停止上述评测 API；保留私有快照用于复核。检查本次两个容器的归属后才清理，不使用 `compose down` 或 prune：

```bash
for name in "$PG" "$OS"; do
  owner=$(docker inspect -f '{{index .Config.Labels "cyber-memoir-evaluation"}}' "$name")
  test "$owner" = "$RUN" && docker stop "$name"
done
```

`--rm` 删除本次 tmpfs 容器，不删除业务卷、公开证据或演示库。

## 下一步

1. 人工逐条核对 hybrid 的 16 条独特断言，记录语义支持、精确来源和不确定细节；不要仅凭批准状态判真。
2. 分析六条正例弃答、离题的附加断言和每阶段耗时；先保留现有阈值，并用独立扩充的人工集验证任何策略变动。
3. 优化重复 query embedding/候选推理成本，以真实模型和相同冻结归档比较延迟及输出；不得用 mock 得到的速度替代模型测量。
