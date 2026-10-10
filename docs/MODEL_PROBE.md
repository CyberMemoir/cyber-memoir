# 真实模型验收：离线定义检索探针

采用 [BEIR 的语料/查询/相关目标分离与多方法对照做法](https://github.com/beir-cellar/beir)，在本地真实加载项目默认的 [BGE-M3](https://huggingface.co/BAAI/bge-m3) 与 [BGE reranker v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3)。这是**离线定义排序组件探针**，不是业务档案的端到端召回、事实正确性、引用质量或生产服务延迟验收。

## 已测结果（2026-10-10）

使用同一个冻结输入：16 份本地 `resolved: true` 且有定义的记录，17 条来自独立 `_descriptions.yaml` 的人工描述查询，11 条本地负例标注。其余 11 条人工查询因没有匹配的本地定义，显式排除并记录原因；不作为检索失败或成功混入指标。17 条正例均未包含语料中的完整梗名或别名。

本地标记不证明条目已发布或定义已被事实核验，作者先后顺序及严格未见测试隔离也未证明。负例的“编造/库外”是本地标注，不声明这些语句在全网不存在。输入与金标准没有修改，没有向 API/业务库导入或发布任何记录。

| 方法 | Top-1 / 17 | Recall@3 | Recall@10 | MRR |
|---|---:|---:|---:|---:|
| 精确名称/别名 | 0 | 0.000 | 0.000 | 0.000 |
| BGE-M3 dense 全语料 | 13 | 0.765 | 0.941 | 0.802 |
| 全 16 份定义交叉重排 | 12 | 0.824 | 0.941 | 0.789 |
| dense 前 10 再重排 | 12 | 0.824 | 0.941 | 0.778 |

**不能据此声称重排提升总体质量**：它改善 Top-3，却将 Top-1 从 13 降到 12；17 条查询与 16 份候选很小，@10 也容易饱和，不能推广到正式档案。缺少原始摘录的定义、含糊查询、候选形成方式都需要继续核对，不能仅归因于模型。

以当前实验下限 `0.35` 探查：只有 **9/17** 预期正例定义超过该分数，**1/11** 本地负例有候选超过下限。这不是 RAG 的正确弃答率：此探针没有发布资格检查、证据 chunk、BM25/关系融合或审核断言选择。本轮不改下限，不把失败查询抄进定义，也不重写负例或人工查询以抬高成绩。

[重排模型用法](https://huggingface.co/BAAI/bge-reranker-v2-m3#using-flagembedding)说明 `normalize=True` 是 sigmoid 分数变换，不等于在本领域做过经验概率校准。API 的历史字段名 `scores_calibrated` 表示有可用于下限的规范化分数，不是事实置信度。

## 真实运行与工件

- ARM64 macOS 开发机，24 GB 内存；显式 CPU、4 个 Torch 线程、FP32；没有用缓存的小模型替代默认模型。
- `FlagEmbedding 1.4.2`、`torch 2.14.0`、`transformers 5.16.1`、`numpy 2.3.5`，来自冻结的 `uv.lock` 与独立 `.data/model-eval-venv`。
- BGE-M3 提交 `5617a9f61b028005a4858fdac845db406aefb181`；权重 SHA-256 `b5e0ce3470abf5ef3831aa1bd5553b486803e83251590ab7ff35a117cf6aad38`。
- 重排器提交 `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`；权重 SHA-256 `d9e3e081faff1eefb84019509b2f5558fd74c1a05a2c7db22f74174fcedb5286`。
- 下载只选固定模型的权重/配置/分词器/线性层文件，不下载远程 Python，不使用个人 Hub token。LFS 文件按上游 SHA-256 校验，其余文件按 Git blob ID 校验；探针运行前后再核对所有文件。
- 冷 embedding（包含模型初始化与 16 文档批处理）约 **10.97 秒**；28 查询批处理约 **0.417 秒**；冷重排首次约 **7.66 秒**；暖态 16 候选/查询中位约 **2.00 秒**；立即重复查询的分数缓存中位约 **0.036 毫秒**。这是组件耗时，非 HTTP 延迟或生产 SLA。
- 另以真实重排器对同一 16 候选执行 6 个并发调用：相同查询实际计算 **1 次**、峰值 **1**，不同查询实际计算 **6 次**、峰值 **1**，观察总耗时约 3.04 / 13.17 秒。只包装真实模型方法计数，未替换模型输出；此并发探针与轻量单元测试有时间重叠，不作独占机器性能结论。

可提交的去路径聚合记录：[results-2026-10-10-model-probe.json](../evals/results-2026-10-10-model-probe.json)。完整本机报告保留在忽略的 `.data/model-eval/probe-20261010-final.json`；其 SHA-256 为 `038443bd7acb6f4d82f1171485a11d7d55ba4d3fd863ab8738911116ac24a0e9`。权重和环境不进入 Git。

## 复现

在仓库根目录执行。首次需要下载约 4.6 GB 模型文件及独立环境；已有固定快照可复用。清单与输出采用新文件名，不覆盖既有工件。

```bash
UV_PROJECT_ENVIRONMENT="$PWD/.data/model-eval-venv" \
  uv sync --project apps/backend --frozen --extra embeddings
MODEL_PY=.data/model-eval-venv/bin/python
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1 "$MODEL_PY" evals/model_assets.py \
  --kind embedder --revision 5617a9f61b028005a4858fdac845db406aefb181 \
  --cache .data/model-cache --manifest .data/model-eval/embedder-manifest.json
HF_HUB_DISABLE_IMPLICIT_TOKEN=1 HF_HUB_DISABLE_XET=1 "$MODEL_PY" evals/model_assets.py \
  --kind reranker --revision 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e \
  --cache .data/model-cache --manifest .data/model-eval/reranker-manifest.json
"$MODEL_PY" evals/model_probe.py \
  --embedding-manifest .data/model-eval/embedder-manifest.json \
  --reranker-manifest .data/model-eval/reranker-manifest.json \
  --out .data/model-eval/probe-new-run.json --threads 4
```

已存在且校验过的 manifest 不必重新下载。探针关闭 `.env` 加载及模型联网，直接使用生产 `inference.embed/rerank`，拒绝未固定提交、不完整清单、变更工件、未知目标、无效/重复查询和不可排名向量。输入或代码在运行中改变时报告 `invalid` 且不汇总指标。

生产可按部署硬件显式设置 `EMBEDDING_DEVICE` / `RERANKER_DEVICE` 与 `EMBEDDING_THREADS` / `RERANKER_THREADS`；设备为空时保留原自动选择。Torch 线程设置在进程内共享，两个模型同时启用时应设为相同线程预算，不把它们当独立配额。设备改变不会复用旧重排分数或模型实例。embedding 冷加载/编码序列化，避免多个冷调用各加载一套权重；返回必须是有限的 1024 维向量。没有新增事实回答缓存。

## 下一项验收

在隔离测试栈固定**实际已批准的公共语料快照**与证据 chunk，再用 [可恢复 API 评测](EVALUATION.md) 对照 exact/BM25/dense/重排、引用可解析和语义支持、无证据弃答、并发与撤回。需要更大、未参与内容起草的人工查询集；这一步不能用本文的离线定义指标替代。

生产新增两秒模型槽等待准入后，本页的离线原始容量探针显式设置 60 秒等待预算并记录到报告，确保测六次串行计算；不把它用于两秒 HTTP 忙碌拒绝验收。见 [INFERENCE_BUSY.md](INFERENCE_BUSY.md)。
