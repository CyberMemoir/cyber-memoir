# 正常 HTTP 与真实并发等待

2026-10-10，在新的归属标签/tmpfs PostgreSQL/OpenSearch 副本上使用实际 BGE-M3 和 CPU 单次前向 reranker。原批准快照仍为 14 条公开记录、54 证据、143 dense chunk；14 人工描述正例、11 负例。业务栈、原始输入和演示不修改。

与 [CPU 配对测量](CPU_RERANK.md) 不同，本轮 **不运行参考重排路径**。增加只供隔离评测 API 启用的 `--trace-inference`，记录真实模型加载/计算、查询处理和原锁的等待时间；不替换模型输出、不保存查询正文、候选文本或答案。`evals/run.py` 另保存每次 POST 的实际 HTTP 耗时，主动限流等待仍独立计量。

## 单客户端：搜索后回答

25 个用例/50 次 POST 完整完成、无失败或降级。首次搜索包含冷模型/库初始化；其余查询仍是新查询，不是预热全部金标准后测缓存。

| 项目 | 中位数 | 最近秩 P95 | 最大 |
|---|---:|---:|---:|
| 搜索 HTTP（25） | 9.452s | 15.149s | 23.375s |
| 随后回答 HTTP（25） | 0.136s | 0.195s | 0.229s |
| 两次 POST 合计（25） | 9.588s | 15.343s | 23.533s |

P95 用 `ceil(0.95*n)` 最近秩，不对小样本外插。以提交的 JSON 为完整精度依据。此开发机不是专用测试机器；后台有构建/测试活动，localhost 非生产网络，不将这些数字当生产 SLA 或受控 A/B 提速比例。

首次搜索 **23.375s**。加载阶段分别观察到 embedding **4.054s**、reranker **0.648s**；这些不是整次冷请求耗时，不能直接相加代表冷启动全部成本。实际 50 次查询处理产生 **25 次 embedding 编码、25 次 reranker 评分**；随后回答复用向量和分数，但仍重新读公开资格/修订/证据，**不是缓存答案或事实**。各请求的模型 trace 使用独立、不含查询正文的 UUID；实际 50 个请求上下文均被记录。

Recall@10 **14/14**、MRR **0.8512**、回答包含目标 **8/14**、负例正确弃答 **11/11**。每个用例的断言与引用列表同原 hybrid 报告完全一致。引用记录核对未发现串线；16 条去重断言仍未人工评级，六条正例弃答未解决。

## 六并发：不同于六次顺序调用

两种并发场景各使用全新 API 进程，先用另一个原始 gold 查询预热模型，再通过六个客户端、同一 barrier 同时发起查询。没有改写查询、伪造 IP、关闭/放宽限流或减少候选预算。预热查询不在测量的六个请求里；真实 trace 验证缓存 miss 的计算数量，不假定“重启就一定冷”。

| 场景 | embedding / reranker 实际计算 | HTTP 中位 | HTTP 最大/最近秩 P95 | reranker 等待中位 / 最大 |
|---|---:|---:|---:|---:|
| 同一新查询 × 6 | 1 / 1 | 11.172s | 11.174s | 10.493s / 10.495s |
| 六个不同新查询 | 6 / 6 | 31.326s | 54.616s | 22.284s / 44.952s |

两组均成功返回当前公开修订，预期目标均在结果中。六个样本的 P95 就是最大值，不能推广成生产尾延迟。相同查询虽然只计算一次，其余调用仍等第一次完成；不同查询遵守串行计算，排队成为主要成本。**不能宣称并发问题已经解决**。

这为下一步提供实际依据：先做有界排队/明确忙碌响应和缓存命中的快速读取，再测真实模型下的尾部等待；不通过跳过评分、放宽下限或丢掉证据来缩短请求。

## 复现与可审计工件

[去路径聚合报告](../evals/results-2026-10-10-http-latency.json)保存各阶段的配置/镜像/模型/输入/代码/原报告 SHA、实际计算次数、HTTP 和队列数值。上下文现完整记录 candidate cap **50**、channel limit **100**、per-source cap **4** 与 RRF 参数，不再只记录评分下限。原始报告/检查点/trace/语义队列在忽略且权限 700 的 `.data/archive-http-1e858422e0`。

按 [ARCHIVE_EVALUATION.md](ARCHIVE_EVALUATION.md) 的步骤只读捕获、恢复到独立服务并索引，然后在前台启动正常 trace API：

```bash
"$MODEL_PY" ops/archive_eval_server.py --snapshot "$SNAP" --run-id "$RUN" \
  --database-url "$DB" --search-url http://127.0.0.1:59201 \
  --pg-container "$PG" --search-container "$OS" --mode hybrid --trace-inference
# 另一终端：
apps/backend/.venv/bin/python evals/run.py "$SNAP/public-gold.jsonl" \
  --api http://127.0.0.1:8103 --checkpoint "$SNAP/normal.sqlite" \
  --run-context "$SNAP/context-hybrid.json" --request-interval 1.1 > "$SNAP/normal.json"
```

并发场景要停止上一个 API，等待进程真正退出，再对同一已索引测试数据库开启全新进程，使用**新的快照工作目录/trace 文件**（公开快照/附件可只读复用，不能重用旧 trace）。正常命令不包含 `--compare-cpu-rerank`：

```bash
apps/backend/.venv/bin/python evals/http_burst.py --api http://127.0.0.1:8103 \
  --run-id "$RUN" --gold "$SNAP/public-gold.jsonl" --snapshot "$SNAP/public.json" \
  --context "$SNAP/context-hybrid.json" --trace "$SNAP/inference-trace.jsonl" \
  --mode same --out "$SNAP/burst-same.json"
# 另一个新 API/trace 工作目录上再执行 --mode distinct。
```

只允许带正确归属 marker、正常 hybrid trace 的 loopback API。输入/代码/公共 DTO 在前后必须相同；拒绝已存在输出、配对探针、未启用模型、缺少 trace、推理失败或计算次数不符，不以混入缓存的请求冒充全 miss。trace 只用于拥有该快照的评测进程，普通业务 API 不启用。

完成后已经停止三个评测进程，并按归属标签只删除本轮两个 tmpfs 容器。源公共 DTO 与原始输入 SHA 未变；业务仍为原 schema/发布状态，演示 `3102` 保留。
