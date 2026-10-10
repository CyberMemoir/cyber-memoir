# CPU 重排：消除丢弃的整批推理

本轮阅读 [FlagEmbedding 的 encoder-only 重排实现](https://github.com/FlagOpen/FlagEmbedding/blob/master/FlagEmbedding/inference/reranker/encoder_only/base.py)，并以冻结环境中实际安装的 **1.4.2** 代码为依据。原实现先对最长的一批做模型前向，测试 batch size；成功后丢弃这些 logits，再在正式循环里对同一批做前向。公开档案本次每组 29–37 个候选，少于默认 batch size 128，所以每次模型实际处理整组两遍。

## 实现与边界

- 新 `adapters/cpu_reranker.py` 在**显式 `RERANKER_DEVICE=cpu`** 时替换内部单设备评分方法，保留上游外层的查询/正文指令处理、模型加载和 `compute_score` 接口。
- 保留同一 tokenizer、query 384 / pair 512 默认 token 上限、`only_second` 截断、按长度排序、batch size、补齐、原始顺序恢复和相同 sigmoid。没有缩短候选、减少候选预算、量化模型、改阈值或换权重。
- 只删除丢弃结果的 batch-size 探测，每批前向一次。CPU 推理仍 FP32/no-grad/eval，外层串行锁、校验、分数缓存及公开资格复核都不变。
- 自动设备、MPS、CUDA 和其它非 CPU 配置继续原上游路径；不替它们删除内存适配逻辑。CPU 错误直接交给既有 `reranker_unavailable` 处理，不无限重试或把失败伪装成有效分数。
- 适配依赖当前冻结锁文件的上游准备流程。未来升级 FlagEmbedding/tokenizer/模型时须重做配对验收，不据本次结果保证不同版本等价。按上游 MIT 许可保留 [第三方声明](../THIRD_PARTY_NOTICES.md)，没有修改虚拟环境中的依赖源码。

## 实际批准归档上的配对结果

使用 [ARCHIVE_EVALUATION.md](ARCHIVE_EVALUATION.md) 相同的只读快照：14 公开条目、54 证据、143 dense chunk、14 人工描述正例和 11 负例。恢复到本轮单独标签/tmpfs 的 PG/OpenSearch；只对副本迁移、索引。CPU/4 线程/FP32，固定 BGE-M3 和 reranker 权重，下限仍 0.35。

在同一次实际检索获得的候选上，依次执行上游参考路径和优化路径；包装实际 Torch 前向计数，不替换输出。25 组、**822 个候选分数全部逐元素完全一致**，两条路径的 token batch shape 也完全一致：

| 项目 | 上游参考 | CPU 单次前向 |
|---|---:|---:|
| 实际前向总次数 | 50 | 25 |
| 每组评分阶段耗时中位数 | 18.045s | 8.591s |
| 原始分数、排序与 0.35 取舍 | — | 每组与参考完全相同 |

评分阶段中位耗时约减少 **52%**。这是同候选的配对组件测量，不是生产 SLA：参考先运行，机器非专用，含 tokenization/padding 等阶段；**这次 HTTP 故意运行了两条路径，不能将 HTTP 耗时当正常优化后延迟**。

25 个实际 API 用例完整完成，无降级：Recall@10 **14/14**、MRR **0.8512**、回答包含目标 **8/14**、负例正确弃答 **11/11**。每个用例的回答断言与引用列表还与此前 hybrid 原始报告完全一致。引用记录核对仍无串线，但 **16 条去重断言的语义支持尚未人工评级**，六条正例依旧弃答；此次是效率改进，不是质量问题已解决。

去路径聚合报告：[results-2026-10-10-cpu-rerank.json](../evals/results-2026-10-10-cpu-rerank.json)。提交各组候选数、batch shape、阶段耗时、严格相等结果、原始报告/输入/代码/模型 SHA，不提交查询候选全文、私有稿件或数据库 dump。

## 复现

按归档评测步骤捕获、选题并恢复到**独立**服务，完成索引；使用本地模型环境，显式 CPU。沿用该文档的 `MODEL_PY/SNAP/RUN/DB/PG/OS` 变量：

```bash
"$MODEL_PY" ops/archive_eval_server.py --snapshot "$SNAP" --run-id "$RUN" \
  --database-url "$DB" --search-url http://127.0.0.1:59201 \
  --pg-container "$PG" --search-container "$OS" --mode hybrid --compare-cpu-rerank
# 另一终端：
apps/backend/.venv/bin/python evals/run.py "$SNAP/public-gold.jsonl" \
  --api http://127.0.0.1:8103 --checkpoint "$SNAP/paired.sqlite" \
  --run-context "$SNAP/context-hybrid.json" --request-interval 1.1 > "$SNAP/report-paired.json"
```

`cpu-comparison.jsonl` 必须是新文件，每个实际重排缓存 miss 保存一行；重复命中不重复跑参考。配对差异会记录失败并使重排失败，不静默放过。仅允许启用 reranker 的 API，不能与 `--index-only` 或 off 模式混用。正常评测/服务不加这个选项，不执行参考路径或安装前向 hook。

本轮捕获的源公共 DTO 与评测副本前后 SHA 相同；源库仍 c2 schema、53 草稿/14 公开、0 待运行任务。结束后只停止本次 API 并按归属标签删除两个 tmpfs 容器；业务服务/卷、原 gold 和 `3102` 演示保持不变。模型关闭的演示不会展示这项模型推理加速。

下一步：在相同冻结语料上测正常单路径 HTTP 延迟和并发尾部等待，再诊断六条正例弃答、扩充独立人工集并复核断言语义。

接续已完成正常单路径与六并发 HTTP 测量：见 [HTTP_LATENCY.md](HTTP_LATENCY.md)，没有将本页的配对请求耗时冒充正常延迟。
