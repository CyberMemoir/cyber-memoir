# Can a model draft `role`? — criteria, written before the run

**Status: criteria committed, run not yet made.** The results section is filled in after
the run; nothing above it changes once DeepSeek has answered.

## Why this test exists

Vincent proposed on 2026-09-19 that DeepSeek fill the `role` column of `lineage.csv`, with
Vincent confirming. Until now roles were his alone (CLAUDE.md working agreements).

Roles are not all equal. `source` and `popularized_by` become published relations with
`assertion_status: supported` — the archive's origin claims, the thing it exists to get
right. `derivative` becomes a dated remix event; `irrelevant` is dropped. A wrong origin is
a false claim. A wrong derivative is a misplaced small star.

There is exactly one clean answer key: the **117 roles Vincent judged by hand** before any
model touched roles — 85 derivative, 16 source, 7 popularized_by, 9 irrelevant, over 21
episodes. Once roles are model-drafted, no such key exists again. So the test runs now.

## Setup

- DeepSeek, in a **fresh session** (the loop session has read `lineage.csv`), gets
  `ai_context/role_calibration/rows.csv` — episode, meme name, BV id, `seen_at`, upload
  date, title — with `role` and `notes` removed, plus the episode's OCR materials.
  Task: `ai_context/role_calibration/task.txt`.
- Allowed answers: the five roles, or `?` when the screen does not decide.
- Claude scores against `lineage.csv` as it stands at commit time.

## Criteria

Origin roles = `source`, `popularized_by`. `?` never counts as an origin label.

| # | measure | pass |
|---|---|---|
| 1 | **false origin claims** — rows Vincent marked derivative or irrelevant (94) that DeepSeek labels source or popularized_by | **≤ 2** |
| 2 | **origin recall** — of Vincent's 23 origin rows, how many DeepSeek labels source or popularized_by | **≥ 17** |
| 3 | **non-origin agreement** — of the 94 derivative/irrelevant rows, exact matches (`?` is a miss) | **≥ 80** (85%) |

Reported, no threshold: source ↔ popularized_by swaps; count of `?`; every disagreement
listed individually.

## What each outcome means

- **1, 2 and 3 pass** → DeepSeek drafts every role. Vincent confirms each origin row one by
  one; derivative/irrelevant rows are reviewed by skim.
- **1 fails** → DeepSeek may not propose origins. It fills derivative/irrelevant only and
  marks any candidate origin `?` for Vincent.
- **3 fails** → no role drafting.
- **only 2 fails** → drafting may go ahead, but it saves Vincent no reading: a missed origin
  looks like an ordinary derivative, so every row still needs his eyes. Decide with him.

## Rules for reading the result

- The key is Vincent's judgement, not ground truth; he has corrected his own roles before
  (宗主第二招). Disagreements get read, not just counted.
- If he changes a key label after seeing DeepSeek's answer, the score above is still
  computed on the key as committed, and the changed rows are reported separately with his
  reason. The key is never quietly updated to raise the score.
- Two rows have no `seen_at`, and two carry fused names (`A&B`); they stay in the count.

## Results

_Not yet run._
