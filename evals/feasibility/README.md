# 讲解号可行性测试

判断一件事：**把梗讲解类账号（如 梗指南）当作素材来源，产出的断言够不够用。**

不建任何东西，不改 schema，不入库。一天，出一个结论。

前置立场：讲解视频在 `evidence-rubric.md` 里最高只到 C 级，多数是 D 级。
所以本测试记录的单位不是「梗的起源」，而是**有出处、有时间、可核查的说法**——
「某账号在某时间对多少人说了什么」是事实，「那个说法是对的」不是。

## Part A：素材里到底有什么

### Step 0 —— 闸门

```bash
python evals/feasibility/prep.py videos BV1xxxxxxxxx BV1yyyyyyyyy BV1zzzzzzzzz
```

打印每个视频的字幕轨道，并写出 `<BV>.transcript.txt`（`mm:ss  正文`）和 `<BV>.meta.json`。

没有字幕就要走 ASR/OCR，单条成本大幅上升。这一步两分钟，可能直接改变结论。

### Step 1 —— 选片

三个视频，**刻意选不同形态**：一个单梗深挖、一个多梗合集、一个近期。
形态决定产出密度，别取三个同类。

### Step 2 —— 人工标注

打开 `annotations.csv`（Excel 可直接开，UTF-8 BOM），**删掉 EXAMPLE 行**，
对着 transcript 逐条填。一条断言一行。

| 列 | 含义 |
|---|---|
| `video_id` | BV 号 |
| `span_start` | 断言出现的时间点，`mm:ss`。单梗视频也要填 —— Evidence 的 locator 需要它，否则以后要重看一遍 |
| `meme` | 视频里说的那个表述，原样写 |
| `claim_type` | `origin` / `version` / `fork` / `mutation` / `spread` / `definition` / `usage` |
| `claim_text` | 断言内容，尽量贴近原话 |
| `names_source` | 有没有点名一个具体出处（作品、事件、账号）— y / n |
| `gives_date` | 有没有给时间点或时间段 — y / n |
| `verifiable` | 你能不能在 10 分钟内对着原始材料核实 — y / n / unsure |
| `video_cites` | 视频自己有没有展示或点名可核查的来源 — y / n |
| `notes` | 存疑、矛盾、循环引用等 |

四轴的区分（沿用 Cyber Memoir 的既有语义）：

- **version** 同一个梗、不同表述（鸡你太美 / 只因你太美 / ikun）
- **fork** 衍生出去、并且能脱离母梗独立使用
- **mutation** 表述没变、**含义变了**（当前 schema 表达不了，这是新轴）
- **spread** 跨平台或跨圈层的扩散

**手工标，不要用模型。** 本测试要量的就是素材里真实存在多少东西。

## Part B：比竞品多出什么

```bash
python evals/feasibility/prep.py cnmeme 鸡你太美 尊嘟假嘟
```

cnmeme.wiki 有公开只读 API，无需 key。对你标注到的每个梗拉一份，人工回答三个问题：

1. 有没有**可核查的引用**？
2. 日期有没有**依据**，还是直接断言？
3. 分不分**起源**与**走红**？

若答案系统性为「否」，你的差异化就是被测出来的，而不是被假设的。

参考量级：cnmeme.wiki 约 6226 条，每月新增约 1700 条，2026 年 4 月起。
体量上打不过，也不该打。

## 判定

```bash
python evals/feasibility/prep.py summarize evals/feasibility/annotations.csv
```

阈值固定在 `prep.py` 的 `THRESHOLDS`，**测试前就写死**，事后不许改：

| 指标 | 阈值 | 含义 |
|---|---|---|
| 每视频良构断言 | ≥ 5 | 良构 = specific 且 verifiable。低于此，不如一次一梗地策展 |
| specific 占比 | ≥ 30% | specific = 既点名出处又给时间。低于此，存的多是模糊断言 |
| mutation + spread 占比 | ≥ 10% | 低于此，四轴方向没有素材支撑，收敛回 origin + version |

引用率低**不算失败**。它只是把证据层级钉死在「有出处的说法」，
那就在 ADR 里写明，别让 `verified` 标记看起来像事实核查。

## 产出

- `annotations.csv` —— 新口径下 gold set 的第一批行，不浪费
- summarize 的输出
- Part B 的三个问题的人工结论
- 一页结论：做 / 不做 / 收敛到哪个范围

阈值是外部建议值，可以调，但必须**在跑之前**调。
