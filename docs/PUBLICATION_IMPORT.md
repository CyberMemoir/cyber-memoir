# 跨平台交付导入

将已采集、可审阅的 JSONL 交付变成本站的待审修订，而不是再次抓取平台或自动发布。支持 Bilibili、抖音、小红书和网页来源。现有 `/v1/submissions` 自动采集入口仍只支持 B站和抖音。

## 借鉴的做法

- 借鉴 [Wikidata QuickStatements](https://www.wikidata.org/wiki/Help:QuickStatements) 的批量操作预览：先看到每条操作，再明确执行。在这里，执行仅生成待审稿，发布仍是另一项人工决定。
- 借鉴 [Zotero 的条目/附件管理](https://www.zotero.org/support/adding_items_to_zotero) 与[重复检测](https://www.zotero.org/support/duplicate_detection)：来源身份、材料和梗记录分开；遇到同名歧义交给人，不用名称强行合并。
- 界面是现有工作台的小范围扩展，沿用 `DESIGN.md` 的黑色星空、薄荷色控件、衬线标题、细线列表和手机单栏，不复制第三方品牌、图片或页面文案。

## 数据包

同一目录包含 `manifest.json` 与 UTF-8 `entries.jsonl`。清单须提供：

```json
{
  "schema_version": 1,
  "groups": 1,
  "new_groups": 1,
  "existing_groups": 0,
  "meme_source_associations": 1,
  "entries_sha256": "<entries.jsonl 原始字节的 SHA-256>",
  "automatic_import": false
}
```

每行提供 `canonical_name`、`operation`、`sources`，以及交付的溯源字段。来源需要 `platform`、完整 HTTPS `url` 和非空 `text_parts`；`original_records` 可保留观察信息与外部材料引用。

- `create_new` 必须有待审 `definition`，可提供 `usage_context`、`aliases`、`origin_status`。导入器不推断它们由哪份材料支持；人工选择后才能发布。
- `append_derivatives` 不能携带定义、使用语境、别名或起源状态的替换字段。`origin_verified` 仅作为交付溯源保留，不改变本站状态；`preserve_existing_fields` 不构成发布授权。
- 来源在同一条目中不能重复，不同梗可以共享来源。来源关联数不是独立作品数。
- 原实例的 `published_meme_id`、`published_revision_id` 仅是溯源，绝不作为本实例的目标 ID。
- `query_evidence` 保留在私有交付快照中，不自动变成别名、人工查询金标准或实际搜索日志。

清单上限 100 KB，JSONL 上限 8 MB / 100 组，每组最多 100 个来源。校验原始字节，不做 CRLF/LF 转换。不会读取、上传或下载 `original_records` 中的本机路径、截图或媒体；保存的证据只是包内文本摘录，原附件引用不等于附件已归档。

## 先迁移，再启动新版后端

新增迁移 `e4f5a6b7c8d9`（基于当前 main 的 `c2d3e4f5a6b7`）只增加 `import_records` 回执表：

```sh
make migrate
```

回执持久保存条目指纹与本站 ID 映射；进程重启后重放相同条目仍不增加修订，不会恢复已拒绝或撤回的记录。后续整合来源观测 PR #22 时，需要为两条新增迁移建立 Alembic 合并节点；本分支没有合并该 PR 或修改其迁移。

## 工作台

1. 连接「审核工作台」，展开「导入已采集的数据」。
2. 选择同一交付的清单与 JSONL，点击「校验并预演」。此步骤不写数据库或对象存储。
3. 查看新增、追加、重复与冲突。追加目标必须是本实例中唯一且有效公开的同名条目，并且没有其他待审修订。
4. 点击「确认生成待审稿」。全部冲突通过后整包提交；预演与确认之间数据包或目标版本变化时，要求重新预演。
5. 在队列逐条核查材料与事件。新增稿选择支持字段的证据；追加稿的原字段只读，旧断言、事件、关系及其证据绑定在后端也受到保护。填写理由并人工确认，才可发布。

没有追加基础条目的空库不能重建追加项，导入器不会为它们虚构定义。2026-10-08 的交付可离线校验为 15 组（8 新增 / 7 追加）、83 个关联、78 个独立来源；在线导入前须先恢复那 7 个已有条目的基础版本。

## CLI

使用后端的 Python 环境。`validate` 只校验文件，不连接数据库或 API；`dry-run` 和 `import` 使用环境中的审核令牌，不接受明文令牌命令行参数。

```sh
cd apps/backend
uv run python -m cyber_memoir.cli.import_publication validate /path/to/publication
uv run --env-file ../../.env python -m cyber_memoir.cli.import_publication dry-run /path/to/publication
uv run --env-file ../../.env python -m cyber_memoir.cli.import_publication import /path/to/publication --plan-hash <预演返回的plan_hash>
```

默认 API 为 `http://127.0.0.1:8100`，可通过 `--api` 指定 HTTPS 远端。在线预演有冲突时退出码为 2，文件/HTTP 失败为 1，成功为 0。导入命令不执行批准操作。

## 接口与一致性

均需要审核令牌：

- `POST /v1/reviews/sources`：人工登记完整链接，不解析 DNS、不跟随短链、不创建采集任务。重复登记不覆盖已有标题或发布时间。
- `POST /v1/reviews/imports/validate`：请求 `{manifest, entries_jsonl}`，返回计划、计数、冲突和 `plan_hash`。
- `POST /v1/reviews/imports?expected_plan_hash=...`：请求相同数据包，返回本站来源、证据和修订 ID；只生成待审稿。

B站 BV 大小写及分 P 被保留；小红书按完整笔记 ID 去重；网页保留可能标识页面的查询参数，只移除片段。不支持小红书/网页自动刷新；不会把采集失败解释为下架。

发布继续使用既有审核接口、证据确认和版本冲突规则。导入不标记证据已核查、不排入提取任务、不产生公开索引。数据库写入整体提交；对象存储不参与数据库事务，后续存储/数据库故障可能留下无数据库引用的内容寻址工件，但不会留下部分导入的公开记录。工件与数据库仍应一起备份。

## 验证范围

自动化测试仅用明确标记的合成材料：校验摘要与数量、无副作用预演、幂等回执、源 ID 映射、同名歧义、撤回防复活、追加保护、时间偏移恢复、存储故障回滚、CRLF CLI 读取和增量迁移。浏览器验收覆盖上传—预演—待审—人工核对—平台检索及追加只读字段，且使用临时 SQLite 与对象目录，不接触业务数据库。

视觉检查按 1505×1045 桌面与 390×844 手机进行：沿用现有工作台参考态，检查文案、字号、颜色、布局、控件和来源证据列表。新增导入区域使用细线而非卡片网格；手机文件控件与预演行改单栏，修正原管理操作按钮被挤成竖排文字的问题。内置 IAB 不可用，使用 Playwright Chromium 及截图逐张检查。

2026-10-09 本轮结果：后端 141 项通过、真实服务集成 1 项按环境跳过；完整浏览器套件 23 项通过；Ruff、TypeScript、Next.js production build、OpenAPI/TS 契约生成和差异格式检查通过。增量迁移在隔离 SQLite 上验证升级/回退，并成功生成完整 PostgreSQL 离线迁移 SQL；未执行业务数据库迁移或 Docker/真实 PostgreSQL 并发验收。

| 视觉对照 | 结果 / 修正 |
| --- | --- |
| 导航与首屏文案 | 原导航、标题和副标题保持不变；仅新增声明的导入入口与平台筛选，无新增营销徽标或虚构统计 |
| 布局与容器 | 复用工作台宽度、沟槽与细线；桌面文件双栏、手机单栏，不增加卡片网格 |
| 字体与层级 | 复用衬线标题、正文和控件字号；摘要为小号等宽文字，不抢主任务层级 |
| 配色与图标 | 保留黑色星空、薄荷色交互和原生展开标记，不借用证据阶段色做装饰 |
| 控件与间距 | 复用按钮、输入框与 22px 间距；手机管理按钮修正为两列，避免竖排文字 |
| 响应式 | 320/390/768/1440px 首页无页面溢出；新增平台标签可在窄屏内部横向滚动 |

设计依据是已有 `DESIGN.md`，不是另起视觉主题。通过 `view_image` 对工作台参考态与最新桌面/手机截图逐张对照；剩余有意差异仅为上述新增功能。开发模式截图中的 Next.js 调试标记以及原生文件选择器的本地化文案由运行环境提供，不作为本站品牌元素。临时截图与 SQL 不作为交付数据保留。
