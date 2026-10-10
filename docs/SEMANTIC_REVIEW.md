# 固定语料的语义复核记录

引用能解析、记录经过发布审核，不等于证据文本支持每个断言。本轮为 `citation_audit.py` 的未评级队列增加独立的准备/校验流程，不修改文化记录，也不自动给16条真实断言填写结论。

选择器借鉴 [W3C Web Annotation 的 Text Quote / Text Position](https://www.w3.org/TR/annotation-model/#selectors) 原则：摘录必须绑定资源与具体位置。这里是本库的简化 JSON 格式，**不宣称完整 JSON-LD/W3C Annotation 兼容**。

## 准备待复核文件

原审计 JSONL 队列只读；同一证据 ID 不能在队列里对应不同文本/来源。工具核对断言ID、正整数公开修订、独立证据绑定、verified/retracted 和来源标识；仅接受未评级队列，拒绝把已有结论清空后冒充新任务。这些是冻结文件的结构检查，不证明当前发布状态或来源真实性。

```bash
PY=apps/backend/.venv/bin/python
QUEUE=.data/archive-eval-8d7545877e/semantic-hybrid-v2.jsonl
$PY evals/semantic_review.py prepare --queue "$QUEUE" \
  --out .data/archive-eval-8d7545877e/human-review-new.json
```

模板用原队列完整字节 SHA-256 绑定上下文。每条初始 `assessment/reviewer/reviewed_at/reason` 均为空、`quotes=[]`，没有预选“支持”、计算概率或自动署名。输出须是新文件，不能覆盖队列或已有复核；新目录权限700、文件600（POSIX）。复核文件含姓名/理由时应继续保留私有，不提交Git。

## 逐条填入实际复核

也可使用 [本地可视化复核工作台](SEMANTIC_WORKSPACE.md)：导入相同队列、选择原文摘录并导出复核文件，再用下述CLI独立校验。页面不连接业务审批，不自动填结论。

原保存证据在对应队列的 `evidence` 中，复核文件只存判定与引用位置。五种结论分别统计，不把部分支持算作完整支持：

| 结论 | 使用含义 |
|---|---|
| supported | 复核者认为保存文本支持该断言 |
| partial | 支持部分内容；在reason明确哪些细节尚不足，宜拆分断言 |
| unsupported | 复核者未找到支持；不自动认定断言在现实中为假 |
| contradicted | 保存文本有相反表述；不能仅用“有一条反对性来源”推定最终真相 |
| unverifiable | 当前保存材料无法核对，比如缺原始帧、OCR误识别或缺少上下文 |

已评级条目必须同时有非空 reviewer/reason 和带时区的 reviewed_at。时间/身份是记录者的**自述归属**，文件校验不认证身份、判断工作是否由人完成或证明真实时间先后。

`supported/partial/contradicted` 至少附一个 literal quote，例子只用于软件测试：

```json
{
  "evidence_id": "synthetic-evidence",
  "content_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "start": 1,
  "end": 2,
  "exact": "😀"
}
```

对于保存字符串 `星😀合成测试原文。`，`[1:2]` 的确是该emoji。位置是**Python Unicode码点**，不是字节、JS UTF-16 code unit 或视频毫秒；end不包含末尾。实际复核要替换成真实ID/哈希/原文位置。选中的文本必须与保存证据逐字一致、处于同一证据哈希下，不能跨证据移植、重复选择或凭空写摘录。

unsupported/unverifiable 可没有quote，但仍要给完整理由/归属；“没有quote”不自动成为这两种结论。未复核条目保持全部空，可保留模板或从文件中省略，都会计为pending；半填的署名/结论拒绝作为完成记录。

## 校验与汇总

```bash
$PY evals/semantic_review.py validate --queue "$QUEUE" \
  --reviews .data/archive-eval-8d7545877e/human-review-new.json \
  --out .data/archive-eval-8d7545877e/semantic-summary-new.json
```

队列/复核输入在处理前后必须字节一致。严格拒绝错队列、未知/重复断言、未知结论、额外字段、无归属、naive时间、错证据/哈希、越界/布尔位置或不匹配摘录；不默认合并/rebase旧文件。已做过的评估应在原冻结上下文保留，材料变化后另建新上下文并明确复核，不能直接沿用旧结论。

输出只汇总 total/assessed/pending、五类计数及归属记录。只有pending=0才叫 `status=complete`，这意味着**此份队列的记录填全且通过结构校验**，不是文化真值、事实精度、专家共识、当前发布资格或发布审批通过。没有自动“语义正确率”数字，没有数据库连接/HTTP写入/模型调用，不改定义/审核/撤回/发布。

## 本轮实际状态

对原 hybrid 的16条独立断言实际准备并校验了一份模板：**16 pending、0 assessed、五类计数全0、status=partial**。没有把软件测试里的合成结论套到真实数据上，原队列/人工查询不变。实际私人工作文件在忽略目录，不将证据全文、归属信息或未经复核的判断推送GitHub。

37项新回归采用合成材料，覆盖五类独立统计、码点/emoji、摘要/资源绑定、未完成归属、队列变动/重复/额外字段、证据冲突、原文件保护、私有权限和处理中的输入变更。它们检验流程约束，**不是37条真实语义判断**。

下一步：复核者实际阅读队列及原始材料，逐条填写并核验；如需改文化记录，再走已有条件写入/人工审批流程。本工具不取代该流程。
