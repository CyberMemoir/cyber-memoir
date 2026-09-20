# Baseline: retrieval on queries that do not name the meme (2026-09-20)

**This is a baseline, not a test.** No criteria were written before it, because it does
not decide anything — it records what retrieval is worth on a 26-meme, entirely
hand-written corpus, so that the first drafted batch has something to be compared
against. Read it as a reference point and nothing more.

## Why it had to run now

Every gold query before today was the meme's own name, or its name plus 的出处. Recall
had been 1.00 since the first run and could not move: it measured spelling. On 2026-09-20
Vincent wrote 28 name-free description queries — his own words for each meme, with the
name and every alias forbidden — and the corpus went from 14 memes to 26 in the same
afternoon. Batch 3 will change the corpus *and* introduce model-drafted prose at once, so
a number taken afterwards could not separate the two.

Run: `evals/run.py` over 93 cases, 232 minutes, 0 failures, against 26 published memes
and 107 evidence stars. Split with `evals/score_buckets.py`.

## The numbers

| bucket | n | recall@10 | MRR |
|---|---|---|---|
| canonical | 26 | 1.000 | 1.000 |
| alias | 2 | 1.000 | 1.000 |
| origin_intent | 26 | 1.000 | 1.000 |
| **description** | **28** | **0.893** | **0.781** |
| negative | 11 | correct abstention 11/11 | — |

Aggregate over all 82 positives: recall@10 0.963, MRR 0.925. **Do not quote that number.**
54 of the 82 are the meme's own name and every one lands at rank 1; the average is mostly
a measurement of spelling. The 28 description cases are the only informative ones.

Where the 25 successful description queries landed: rank 1 for 20 of them (80%), rank 2
for 2, rank 3 for 2, rank 5 for 1.

## The three misses are two different faults

**Nothing came back at all** — 刷到焦~ (大狗叫) and 被戏耍了 (老叟戏顽童). The search
returned zero candidates, and the `bge_reranker` channel never ran, because there was
nothing for it to rank. This is a lexical gap, not a ranking failure: BM25 is the only
content channel in this deployment (`degraded: ['vector_disabled']`), so a short query
sharing no tokens with any record retrieves nothing whatsoever.

**The right meme ranked below ten** — 觉得一个东西像 THe Monkey's Paw (许愿柳). Ten
candidates came back and the reranker did run, putting 干瘪瘪的芝士球 first at 0.021 and
许愿柳 nowhere in the top ten. Every score was tiny; nothing matched. The query is an
English literary reference and the corpus holds no English text for it to match on.

Both faults are the same underlying thing from different angles: **with embeddings
disabled, retrieval cannot cross a vocabulary gap.** A reader who half-remembers a sound
(焦), describes the meme in words the archive never uses (被戏耍了), or reaches for a
foreign reference gets nothing.

## What this says about abstention

The abstention score is 11/11, which looks perfect and is not free. Two of the three
misses returned zero candidates, so the archive abstained on questions it can answer —
false abstentions that the negative set cannot see, because the negative set only contains
questions it *should* refuse. The 1.00 measures one direction only.

## What it does not say

- It does not measure whether an answer is *right*, only whether the right meme is
  retrieved. Semantic support still needs a human gold standard (the run's own note).
- `scores_calibrated` is false whenever the reranker does not run, and the score floor
  (0.35) has still never been validated — only argued to sit inside a wide safe margin.
- n = 28, over a corpus of 26. One meme's queries moving changes the third decimal.

## The open question this raises

Embeddings are off by deliberate choice, recorded as "hand curation must not be
contaminated by model output". That reasoning is about *generation* — an LLM writing
definitions — and an embedding used for retrieval writes nothing into the archive. This
run is the first evidence that the vector channel is doing real work by its absence:
all three failures are ones it exists to solve. Whether to turn it on is Vincent's call,
and it would want its own criteria written first, against these 28 queries.
