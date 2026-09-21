# Aliases: what 64 of them bought (2026-09-21)

## Written before the run

64 aliases were proposed blind by DeepSeek (37 seen on screen, 27 guessed) and every one
was kept by Vincent, taking the corpus from 3 memes with an alias to 21. Since
2026-09-20 aliases are also searched by BM25 (`aliases^3`, index memoir-v2); before that
they matched only a whole-string query.

Measured against the 2026-09-20 baseline (description recall@10 0.893, MRR 0.781, 11/11
abstention), on the 28 description cases and the 11 negatives. The 54 name queries are
not re-run: they sit at rank 1 through the exact_alias channel and are not what aliases
can move. That is an assumption, stated here rather than tested.

This is a measurement, not a decision, so there is no pass mark for recall. There is one
for harm, because aliases widen what matches:

- **Regression**: any negative answered instead of refused. Short generic aliases
  (霓虹, 大阪, 佛得角, 蔡徐坤, Notch, 妙脆角, 章鱼哥) are the risk.
- **Reported apart**: two description queries now contain their own meme's alias
  verbatim - 佛得角是怎么跟强队打平的 (佛得角) and 蔡徐坤跳舞 (蔡徐坤). They were written before
  the aliases existed and DeepSeek never saw them, so this is not leakage, but a hit on
  them says less than a hit on a query that shares nothing with an alias. Recall is
  given with and without them.

## Result

Run: 39 cases (28 description, 11 negative), 0 failures, after all 26 records were
reloaded with their aliases and the index confirmed to hold them (叮咚鸡是什么 now finds
大狗叫 through the alias field alone: 13 chunks).

| | baseline 2026-09-20 | with aliases |
|---|---|---|
| description recall@10 | 0.893 | **0.893** |
| description MRR | 0.781 | **0.810** |
| negatives refused | 11/11 | **11/11** |

**No regression**: every negative is still refused.

**No miss was recovered.** The same three queries fail: 刷到焦~, 被戏耍了, and 觉得一个东西像
THe Monkey's Paw. None of the 64 aliases covers their words - 大狗叫 gained 叮咚鸡 and
大狗叫叫叫 but not 焦, 老叟戏顽童 gained nothing near 戏耍, and 许愿柳 gained One Wish Willow,
not Monkey's Paw.

**The entire MRR gain is one query.** 蔡徐坤跳舞 moved from rank 5 to rank 1, because 蔡徐坤
is now an alias of 宗主第二招. Set aside the two queries that contain one of their own
meme's aliases verbatim, as this file said before the run it would, and the other 26 are
identical to the baseline: recall 0.885, MRR 0.795, before and after.

## What this says

Aliases do what they are built for: a reader who types another *name* for a meme now
finds it, where before they found nothing unless they typed the name alone. That is real
and was verified directly, but this gold set barely measures it - its `alias` bucket has
two cases.

They do nothing for a reader who *describes* a meme, which is what the 28 description
queries are and what all three misses are. Those are vocabulary gaps between the reader's
words and the archive's, and a list of names cannot anticipate them: nobody would write
焦 or 戏耍 or Monkey's Paw as an alias of anything. That leaves the question the baseline
raised exactly where it was, with one option now measured and excluded. What remains
is a retrieval channel that compares meaning rather than bigrams - embeddings - with its
own criteria written first, against these same 28 queries.

## Caveats

- n = 28 description queries; one query moving is 0.029 of MRR.
- The negatives contain none of the short generic aliases (霓虹, 大阪, 佛得角, 蔡徐坤,
  Notch, 妙脆角, 章鱼哥), so 11/11 says those aliases did no harm *here*, not that they
  cannot capture an unrelated search.
- 蔡徐坤 and Notch are real people's names now published as 也叫 of a meme. That is the
  curator's call and he made it; it is recorded here because a search for either person
  will now return a meme.
- `load_curation.py` was run once with an empty file list (a shell quoting error), which
  re-revises every record. Harmless - memes are found by name and evidence dedups by
  content hash - but every meme gained one extra revision on 2026-09-21.
