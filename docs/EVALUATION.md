# 可恢复评测与查询来源

本轮继续选择性适配 [PR #14](https://github.com/CyberMemoir/cyber-memoir/pull/14) 的评测实现，未合并其数据或其他改动。检查点采用 [SQLite 的事务提交机制](https://www.sqlite.org/atomiccommit.html)保存完整用例，用上下文管理器确保异常时关闭数据库并释放文件锁。

人工描述查询位于 `evals/curation/_descriptions.yaml`。它保持独立，生成金标准时不改写原文件，也禁止把 `--out` 指向原输入 YAML。构建器只选择本地记录标记已发布且有定义的条目；这不是对当前部署状态的保证。开启固定运行上下文后，runner 会先核对所有正例目标是否仍在当前公开语料中，缺失目标不能作为一次检索失败混入指标：

```bash
python evals/build_gold.py --descriptions-only --out human-descriptions.jsonl
python evals/build_gold.py --out full-gold.jsonl
```

完整集合分别标记 `description`（独立文件中的人工查询）、`description_model`、`description_unattributed`。记录自称 `description_source: human` 也不能代替独立人工文件；未知来源不会默认算人工查询。`score_buckets.py` 单独报告所有出现的桶，包括多义和对抗查询。历史 JSONL 缺少人工来源标记时按未归属描述处理，不事后假定其独立性。描述召回检验检索能力，不证明回答的事实正确。引用可解析和结构覆盖也不等于证据语义支持，起源和主张仍需独立复核。

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

每个完整用例提交到 SQLite 后才可复用。文件锁防止两个评测进程同时拥有同一断点，进程退出后锁自动释放；构造数据库失败或网络/响应异常也会释放资源。失败或未完成的用例下一次重试，已提交用例不重复请求。

金标准原字节、公开条目及其证据 DTO、API 地址、模型/配置声明、runner/checkpoint 和本地后台 Python/依赖文件的指纹不一致时拒绝复用。API 地址不接受 URL 内凭据，HTTP 客户端不采用环境代理或自动跟随重定向。模型工件与远端部署代码仍由部署者用不可变镜像/模型工件核实；本地代码指纹不是远端实际代码证明，工具也不能通过公共 API 读取服务器的真实权重。

评测末尾再次检查语料、查询、配置和代码。发现变动或 API 返回 `corpus_changed_during_search` 时，检查点标为 `invalid`，即便随后恢复旧输入也不能复用，须另建文件。单纯请求或最终快照读取失败时，输出失败报告但保留完整用例，下一次在相同上下文核查后可续跑。无检查点运行也检查查询文件与本地代码在评测中未变；有 `--run-context` 时额外固定公开语料，即使不写检查点。

退出码为 0（完整成功）、1（请求/响应/上下文失败）、2（命令行参数错误）。报告的 `status` 明确标识 complete/failed；失败时所有聚合指标置空。`score_buckets.py` 对失败、缺项、重复、查询不匹配或 gold SHA-256 不一致的报告返回 1，不能从部分成功案例重新算出貌似正常的分桶指标。反例少于 8 条时继续不单独报告弃答率。记录了每例耗时与断言/引用供复核，身份匹配率仍不是事实正确率。

评测期间停止发布、撤回、元数据编辑和更换模型，并保留不可变工件。开始/结束快照不是逐请求数据库快照隔离，不能排除被人为短暂改变又恢复的外部状态；它不替代冻结运行条件。不要把控制台进度当作最终报告。检查点、锁与 SQLite 日志不提交 Git，模型/配置清单不包含密钥。

## 搜索与回答

相同查询及候选文本的重排分数在单进程中复用五分钟，最多保留 64 组。每次仍重新检查当前公开状态、候选、证据和引用；撤回立即生效。查询、候选文本/顺序或模型配置变化时不会复用旧分数。模型路径应指向不可变快照，更换同一路径下的工件后重启服务。

页面先显示检索结果，再整理证据回答。回答失败可单独重试，结果不清空；新查询和取消操作会忽略旧请求的响应。每个阶段等待最多五分钟，部署网关可以更早返回错误。取消等待终止浏览器请求，不承诺中止服务器已经开始的模型计算。

## 本轮验收（2026-10-10）

评测部分新增 25 项回归测试：包含真正中断子进程后的恢复、锁释放、失败引用请求、运行上下文/公共语料变化、失效检查点拒绝重用、人工描述来源隔离和部分结果拒绝汇总。全项目本地结果为 183 项后端通过、1 项真实服务集成跳过、39 项浏览器通过；详见 [验证记录](VERIFICATION.md)。

原金标准和策展 YAML 的字节未修改。临时生成人工描述集得到 17 条，仅验证构建流程；本轮没有真实模型/真实部署评测，不能据此声称语义召回或延迟改善。

后续已完成默认 BGE-M3 / reranker 的**真实离线定义组件探针**，不是公共档案端到端评测；固定工件、结果、失败与范围见 [MODEL_PROBE.md](MODEL_PROBE.md)。保留上述历史记录，不把新的组件结果改写成当时的部署结果。
