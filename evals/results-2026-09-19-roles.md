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
- **Amended 2026-09-19, before any answer existed:** the OCR input is the episode's screen
  as a timeline labelled by position - `解说` for the narrator's subtitle band, `画面` for
  everything else - built from a positioned re-OCR (`prep.py boxes`), instead of the mixed
  materials. Motivated by Vincent's question whether OCR can tell subtitles apart, not by
  any result. The criteria below are unchanged.
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

Run 2026-09-19 by DeepSeek v4.1 flash in a fresh session, from the position-labelled
screens. All 117 rows answered (one `?`). Scored by `evals/score_roles.py` against the key
in commit 2dfbf11.

| # | measure | needed | result | |
|---|---|---|---|---|
| 1 | false origin claims | ≤ 2 of 94 | **3** | FAIL |
| 2 | origin recall | ≥ 17 of 23 | **4** | FAIL |
| 3 | non-origin agreement | ≥ 80 of 94 | **78** | FAIL |

36 disagreements; 1 source ↔ popularized_by swap.

**Outcome, per the criteria written before the run: no role drafting.** `role` stays
Vincent's, and the corpus loop keeps its L-2 human role pass.

### What the failure is made of

The model does not find origins. It caught 4 of 23, calling 7 of Vincent's `source` rows
`derivative` and 6 `reference`, and 5 `popularized_by` rows `derivative`. Reading its
basis lines, the reason is consistent: it judged by where a clip sits in the narration
rather than by what the narration says the clip *is*, so an old work shown as the origin
reads to it as just another cited video.

Not all 36 disagreements are model errors, and the criteria say to read them:

- **你会XXX吗, six rows** (#39, #41–#46): Vincent marked tournament clips `irrelevant`;
  the model called them `derivative`. They are cited in a list of 爆梗 from the same event.
  Worth a second look - if they are derivative works, the key is wrong here, not the model.
- **胆子真是肥嘟嘟的 #47, 宗主第二招 #27**: `irrelevant` vs `reference`. `reference`
  exists for exactly this (shown for context), and Vincent's own role vocabulary allows it.
- **AVGN舞 #14**: the model says the 解说 names this as the source of the meme's music half;
  Vincent marked it `derivative`. One to check against the screen.

Re-scoring after any label change is not allowed: the table above is computed on the key as
committed, and a changed label is reported here with its reason instead.

### What this does not say

It does not say the screen lacks the answer; it says this model did not read it out. A
different prompt, or a model that is shown the four-stage model with worked examples, might
do better - but that would be a second run against a key this run has now seen, so it would
not be blind, and it cannot use these 117 rows again.
