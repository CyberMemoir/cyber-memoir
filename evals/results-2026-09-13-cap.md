# Capping rerank candidates: 50 → 20

Written before the capped run, and committed before it started, so the criteria below
cannot have been fitted to its result.

## Why

The 14-meme gold run took 81 minutes, median 107s per case, slowest 332s. Each
reranked call scores up to `retrieval_candidate_cap` pairs through a 568M-parameter
cross-encoder on CPU at full precision, and each case makes two. At 40 memes an eval
run would take most of a day, and the likely failure is not the wall but that we stop
running it.

## The change

`RETRIEVAL_CANDIDATE_CAP=20`, set in `.env`. Nothing else changes: same image, same
weights, same gold set (`evals/gold.jsonl`, 30 positive, 10 negative), same corpus.

Twenty is twice the reported window (`limit=10`), and with `retrieval_per_source_cap=4`
it can still hold at least five distinct sources.

## Pass criteria

- recall@10 stays 1.00 and MRR stays 1.00
- correct_abstention stays 10/10
- no case gains a `degraded` entry it did not have at cap 50

If any of these moves, cap 20 is rejected. The criteria are not revised.

## What this run can and cannot show

It measures the time saved reliably. **It cannot measure the quality cost, and passing
it is not evidence that there is none.**

A lower cap can only hurt when the right chunk ranks between 21 and 50 in fusion and
the reranker would have lifted it into the top ten. On this gold set that never
happens: every positive query contains the meme's own name, exact-alias matching pins
that meme first before the reranker runs, and so recall is 1.00 at any cap. Abstention
is no test either - fewer candidates means fewer chances for a weak chunk to clear the
floor, so it can only hold or improve.

The harm the cap could do is only visible to queries that do not name their answer.
The gold set has none yet. Until it does, cap 20 is a speed decision taken on trust
about quality, and should be recorded as that.

## Baseline

`results-2026-09-13-cap50.json`: recall@10 1.00, MRR 1.00, correct_abstention 1.00
(n=10), 81 minutes, median 107s.

## Result (added after the run)

`results-2026-09-13-cap20.json`. **Every criterion holds**, so cap 20 is accepted:
recall@10 1.00, MRR 1.00, correct_abstention 1.00 (n=10), no per-case metric changed, no
case gained a `degraded` entry. As stated above, that is not evidence the cap costs no
quality on queries that do not name their answer.

**Time, and a contamination.** The full test suite and a contract regeneration ran on
the same machine during cases 2 to 5, so those timings are upper bounds and are left out
of the comparison. On the clean cases 6 to 40, paired against the same cases at cap 50:

| | cap 50 | cap 20 |
|---|---|---|
| total | 65.7 min | 52.3 min (−20%) |
| median case | 85 s | 83 s |
| median per-case ratio | | 0.75 |

Single cases moved as much as +42% the wrong way (熊大回眸 85 → 121 s), so run-to-run
noise is of the same order as the saving. The biggest savings were on the queries with
the most candidates (闹吃VS古振兴 146 → 100 s).

**Why so little.** The reranker measured inside the container costs 2.3 to 3.5 s per
pair on this machine (5.1 s for a single pair; 20 pairs 45.8 s), and every case calls it
twice, through `/v1/search` and `/v1/answers`. Most queries never produce twenty
candidates, so the cap only bites on the few that do. Time tracks candidates actually
scored: 才是王道 returned one meme in 61 s of search, 才是王道的出处 returned six in 163 s.

The cap is not the lever. The per-pair cost is. The container sees 16 CPUs with torch on
8 threads, so it is not CPU-starved; the Docker VM has 8 GB for a 2.3 GB fp32 model
beside OpenSearch and PostgreSQL, and memory pressure is the next suspect - unverified.
