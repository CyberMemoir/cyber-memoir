# 可恢复评测与查询来源

人工描述查询位于 `evals/curation/_descriptions.yaml`。它保持独立，生成金标准时不改写原文件。只评测已发布条目：

```bash
python evals/build_gold.py --descriptions-only --out human-descriptions.jsonl
python evals/build_gold.py --out full-gold.jsonl
```

完整集合分别标记 `description`（人工）、`description_model`、`description_unattributed`。缺少来源标记的草稿查询不会默认算人工查询。`score_buckets.py` 单独报告各桶；描述召回检验检索能力，不证明回答的事实正确。引用可解析和结构覆盖也不等于证据语义支持，起源和主张仍需独立复核。

报告还保存每个用例的回答断言与引用，并记录 `answer_matches_expected`：回答是否至少包含目标梗的一条断言。这个身份匹配率可以发现“检索找到了但回答选错对象”的问题，仍然不证明具体断言正确。

## 断点续跑

先固定公开语料、查询集和部署配置。准备本地 `run-context.json`，记录实际模型工件的 SHA-256（示例中的占位值必须替换），以及影响评分的完整配置；不要放入密钥：

```json
{
  "model": {"identifier": "pinned-model-snapshot", "sha256": "replace-with-the-actual-64-character-artifact-sha256"},
  "configuration": {
    "image": "immutable-image-digest",
    "reranker_backend": "local",
    "reranker_threads": 8,
    "retrieval_candidate_cap": 20,
    "answer_score_floor": 0.35,
    "embedding_backend": "disabled",
    "llm_model": "disabled"
  }
}
```

```bash
python evals/run.py full-gold.jsonl --checkpoint audit.sqlite --run-context run-context.json > report.json
# 中断后使用完全相同的命令续跑。
python evals/score_buckets.py report.json full-gold.jsonl
```

每个完整用例提交到 SQLite 后才可复用。文件锁防止两个评测进程同时拥有同一断点，进程退出后锁自动释放；失败或未完成的用例下一次重试。金标准、公开条目及其引用证据、API 地址、模型/配置声明和评测代码不一致时拒绝复用。评测末尾再次检查语料、查询文件、配置声明和代码，变化或请求失败会使本轮聚合指标无效。模型工件和配置声明由部署者核实；工具不能通过公共 API 读取服务器的实际模型权重。评测期间停止发布、撤回和更换模型，并保留不可变模型工件。不要把中途控制台进度当成最终报告。

## 搜索与回答

相同查询及候选文本的重排分数在单进程中复用五分钟，最多保留 64 组。每次仍重新检查当前公开状态、候选、证据和引用；撤回立即生效。查询、候选文本/顺序或模型配置变化时不会复用旧分数。模型路径应指向不可变快照，更换同一路径下的工件后重启服务。

页面先显示检索结果，再整理证据回答。回答失败可单独重试，结果不清空；新查询和取消操作会忽略旧请求的响应。每个阶段等待最多五分钟，部署网关可以更早返回错误。取消等待终止浏览器请求，不承诺中止服务器已经开始的模型计算。
