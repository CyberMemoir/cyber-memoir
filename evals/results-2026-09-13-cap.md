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
