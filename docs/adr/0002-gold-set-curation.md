# ADR 0002：金标准评测集的策展标准

状态：提议。

## 背景

`evals/run.py` 已实现，但 `evals/gold.example.jsonl` 只有两行，其中一行是合成夹具。
`docs/VERIFICATION.md` 明确声明：没有把合成测试结果当作真实梗检索 Recall、语义引用支持率或起源判断正确率。
后端 56 项自动化测试验证代码行为，不验证检索质量。因此当前没有任何手段回答：
换嵌入模型、关闭 OpenSearch、调整融合权重之后，系统是变好还是变差。

金标准评测集是人工判断的载体，无法由代码或模型生成，必须由策展人建立。

## 决定

1. 评测集只使用真实存在的梗与真实平台记录。不创建文化事实示例，与 `run.py` 文档字符串和 `docs/design/SPEC.md` 一致。
2. V1 规模为 20 个梗。按五个维度分层，不按个人偏好挑选：
   - 起源位置：站内 / 站外（影视、广告、游戏、直播、论坛、线下）。站外起源不少于 8 个。
   - 别名负载：单一表述 / 多变体表述。多变体不少于 6 个。
   - 材料路径：平台字幕 / ASR / OCR / 人工补料。四类各不少于 2 个。
   - 平台：Bilibili 与抖音都要覆盖，抖音不少于 6 个。
   - 类型：参照 `internet-meme-radar-skill` 的 `references/taxonomy.md`，至少覆盖 catchphrase、audio、visual template、linguistic play 四类。
3. 用例分五类，目标分布约为：canonical 20、alias 20、origin-intent 10、negative 8、adversarial 6。
   - canonical：以规范名检索。
   - alias：不同表述、相同 `expected_names`。这是唯一能衡量别名表与向量通道价值的用例。
   - origin-intent：查询包含 出处/起源/最早/谁先/首创，检验是否正确输出「现有证据不足以认定该梗的起源」。
   - negative：不存在的梗，`answerable: false`。只有这一类会计入 `correct_abstention`，因此不得少于 8 条。
   - adversarial：用梗 A 的查询命中梗 B 材料中出现的词，检验重排是否给出自信的错误结果。
4. 策展档案（`evals/curation/*.yaml`）是事实来源，`gold.jsonl` 由其生成，不手工维护两份。
   每个梗记录：`canonical_name`、`aliases`、`taxonomy`、`origin_type`、`origin_ref`、`origin_status`、
   `earliest_artifact_url`、`top_amplifier_url`、`derivatives`、`material_path`、`notes`。
   `run.py` 目前不读取这些字段；保留它们是为了让起源正确率在未来可被独立度量。
5. 语料必须经过真实的 提交 → 抓取 → 审核 流程入库，禁止直接写数据库。评测集与生产路径共用同一条管线。
6. 评测集按版本冻结。发布一次评测结果就冻结一次 `gold.jsonl`，此后只允许新增用例，不允许为提升分数修改或删除既有用例。
   任何修改必须在本 ADR 的后续版本或提交说明中记录原因。
7. 每次评测记录必须同时保存 `degraded` 通道列表。关闭向量或 OpenSearch 的运行结果与开启时不可直接比较。
8. Recall 与弃答率分开报告，不合并为单一分数。`recall_at_10` 只在 `expected_names` 非空的用例上取平均，
   `correct_abstention` 只在 `answerable: false` 的用例上计算。
9. 策展开始前先在空库上跑一次基线并记录，用于确认管线连通与结果可读。
10. 评测集只保留昵称与公开发布记录，不收录其它个人信息，与项目既有立场一致。

## 代价

- 策展速度慢，20 个梗的完整闭环预计需要数周，且无法并行加速。
- 20 个梗的样本量不足以支撑统计显著性。小于若干百分点的分数差异应视为噪声，不得据此做架构决策。
- 冻结评测集意味着它会逐渐偏离真实用户查询分布，需要按周期新增用例而非重写。
- `expected_names` 曾按 `canonical_name` 精确匹配，使评测集与审核时确定的规范名强耦合。
  `evals/run.py` 现已同时匹配条目的已发布别名（归一化首尾空白与大小写），命名分歧不再计为检索失败。
  代价是别名表的宽窄会直接影响 Recall：一个过宽的别名可以让错误条目算作命中。
  这与 ADR 0004 第 4 条的 `exact_match` 豁免是同一个风险，都把压力转移到别名审核的严格程度上。
