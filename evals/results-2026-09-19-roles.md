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

---

## Afterwards: three labels revised, and a different question (2026-09-19)

### The label changes the criteria asked for

Reading the disagreements, as the section above requires, Vincent reversed three of his
own labels. In each, the narration names the clip as where **one component** of the meme
came from, and he ruled that a component's origin is an origin:

| row | meme | id | was | now |
|---|---|---|---|---|
| #14 | AVGN舞 | BV1YoZ6BUEZ2 | derivative | source |
| #108 | 大狗叫 | BV1eG4y1r72j | derivative | source |
| #113 | 大狗叫 | BV1ic411D7xo | derivative | source |

These were all three of the run's false origins. **The table above is not re-scored** —
it is the result on the key as committed, and it stands. For the record only: with these
labels, criterion 1 would have passed with 0 false origins, and criteria 2 and 3 would
still have failed (origin recall 7 of 26, non-origin agreement 78 of 91 against a bar of
80). The outcome is unchanged. The rule is now in `role_task.txt` as O-4, with these
three as its worked examples.

The 你会XXX吗 rows were left as `irrelevant`.

### Two of the three faults were in the prompt

- **`reference` is not a role Vincent uses.** Zero of 137 judged rows. I offered it
  anyway; the model spent 12 of its 36 wrong answers there, 7 of them origins. Dropped.
- **I asked for caution and then scored recall.** The prompt said a false origin costs
  more than a lost one, which is true, and the criteria then demanded 17 of 23. The
  model was conservative because I told it to be.

### The third fault was the shape of the question

Measured on the 117 rows afterwards:

- An episode cites about 6 videos and states an origin in **one or two sentences**: 32
  such sentences across 21 episodes, against 117 cited ids. Asking 117 times "is this
  the origin?" spends almost every question on a video that plainly is not.
- **The id follows the sentence.** Vincent, from watching: the narrator names the origin,
  then cuts to the clip with its BV id burned on. Offsets from sentence to id: median
  +11s, range -20s to +41s (one outlier at -108s). So the window is lopsided,
  `[-20s, +45s]`, not centred.
- **Position in the episode is not a signal**, contrary to intuition: only 8 of the 27
  memes have their origin as the first id shown, and the first three ids of each meme
  hold just 13 of 21 origins.
- **5 of 21 episodes never state an origin at all.** Their citations are all derivative,
  and no reading recovers what the episode does not say.

`evals/feasibility/origin_cues.py` turns an episode into its origin sentences with the
ids that appear under each. On this set it puts **22 of the 25 origins in front of the
reader inside 50 rows of 117**, and all 3 it misses are unreachable rather than missed:
2 are episodes that never state an origin, and 1 was never on screen. Two cue words
(源头, 火了) were added after being caught missing, which is one more turn of fitting on
spent data.

**That number is fitted, not a result.** The cue words were written by reading these
same episodes and the window was tuned on these same rows. It is a description of the
data it came from. Per the rule above, these 117 rows are spent and cannot test this.

### Criteria for the next batch, written now

The next batch processed under L-1b is the test. Vincent additionally skims the sheet's
"默认 derivative" list once, which he otherwise never reads, so recall is observable that
one time.

1. **Precision** — of the origins DeepSeek proposes, Vincent keeps **≥ 4 in 5**.
2. **Recall** — origins he finds in the leftover list: **≤ 1 per 10 episodes**.
3. **Form** — `origin_cues.py --check` refuses **0** rows of the submitted file.

Failing 1 means the sentences are being over-read and the model should propose fewer.
Failing 2 means the cue list or the window is too narrow and both need widening before
the corpus grows further on them. Failing 3 means the quoting discipline did not hold,
and nothing else in the run can be trusted.
