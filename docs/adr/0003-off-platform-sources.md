# ADR 0003：站外来源与起源角色的表示

状态：提议。

## 背景

`Source` 当前要求 `platform`、`platform_item_id`、非空 `canonical_url`，并对 `(platform, platform_item_id)` 加唯一约束。
这一结构假设每条来源都是可抓取的平台条目。

中文互联网大量梗的起源不在被索引的平台上：影视片段（1994 版《三国演义》）、发布会现场（2015 年"Are you OK?"）、
广告、游戏、直播、已消失的论坛帖、线下事件。这些对象没有 `platform_item_id`，也没有可抓取的 URL，
因而在当前 schema 中无法记录。

后果有两个。其一，系统最有价值的一类回答——"这个梗不起源于 B 站，来自 X"——无法表示。
其二，schema 会把策展人推向把站内最早的搬运或切片标记为起源，这与 ADR 0001 第 5 条
（不以 earliest collected / platform publish timestamp 直接推断 origin）在结果上相互矛盾。

ADR 0002 要求评测集中站外起源不少于 8 个。在本 ADR 落地之前，该评测集无法完成策展。

## 决定

1. `Source` 增加 `source_kind` 判别列：`platform_item` | `external_work` | `offline_event` | `lost_artifact`。
   现有数据全部为 `platform_item`。
2. `platform`、`platform_item_id`、`canonical_url` 改为可空。唯一约束改为部分唯一索引，
   仅在 `platform_item_id IS NOT NULL` 时生效，`platform_item` 类型的既有保证不变。
3. 非 `platform_item` 类型必须填写 `descriptor`：作品或事件名称、发生或发布时间、载体。
   时间精度沿用 `Event.time_precision` 的取值（unknown/year/month/day/second），不伪造精度。
4. 增加可选 `external_identifier` JSON（如豆瓣、IMDb、Wikidata QID）。仅作标识，不触发任何抓取。
5. 站外来源永不进入自动抓取路径。`availability` 固定为 `manual_only`，不写 `last_error`。
6. 站外来源的 Evidence 只能是 `kind="manual"`，由审核者录入；若要支撑 origin 断言，
   必须附至少一条可引用的二级来源（对应 `evidence-rubric.md` 的 C 级）。
   仅凭策展人记忆或"众所周知"不构成起源证据。
7. 新增 Relation 谓词 `popularized_by`，记录扩散者与载体，与 `claimed_origin` 明确区分。
   检索的一跳图扩展纳入该谓词（当前只扩展 `derived_from` 与 `variant_of`）。
8. `origin_status` 语义不变：站外起源同样默认 `unknown`，只有满足第 6 条才可升为 `supported`。
   本 ADR 扩大的是可表示范围，不放宽认定标准。
9. 站外来源一旦录入人工材料，即正常参与检索投影，不做特殊排除。
   用户搜索"鸡你太美 出处"时应当能拿到站外起源条目。

## 代价

- 可空列削弱数据库层约束，需要部分唯一索引，以及按 `source_kind` 分支的 CheckConstraint 与应用层校验。
- 需要一次 schema 迁移。现有迁移刚建立，此刻改动成本最低，越晚越高。
- 站外来源只能人工录入，策展速度显著慢于平台条目。
- 二级来源要求会拒绝一部分广为流传但无从引用的起源说法，短期内 `origin_status=unknown` 的比例会偏高。
  这是保守设计的预期结果，不是缺陷；宁可标注未知，也不把载体当作起源。
