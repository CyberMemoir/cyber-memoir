#!/usr/bin/env python3
"""Split a gold run's report by the bucket each query came from.

    python evals/run.py evals/gold.jsonl > report.json
    python evals/score_buckets.py report.json

run.py reports one recall and one MRR over every positive case. That average cannot
answer the question the gold set exists to answer, because the buckets are not the same
kind of question:

  canonical / alias / origin_intent   the query IS the meme's name, or its name plus
                                      的出处. Recall here has been 1.00 since the first
                                      run and cannot move; it measures spelling, not
                                      retrieval.
  description                         the curator's own words for the meme, with the
                                      name and every alias forbidden. This is the only
                                      bucket that can show what retrieval is worth, and
                                      the only one a change to the prose can move.

So the two are reported apart. A drafted definition is keyword-rich and uniform where a
hand-written one is terse and idiomatic; if that inflates recall, it inflates it here and
nowhere else, which is why the descriptions had to exist before the first drafted batch
loaded (CLAUDE.md, working agreements).

Cases are joined by query text, not by position: run.py drops a case that errored rather
than recording a zero, so positions shift whenever anything fails.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
# ADR 0002 clause 3, the same floor run.py applies: under eight negatives the abstention
# rate is not reportable on its own.
MIN_NEGATIVES = 8
NAMED = ("canonical", "alias", "origin_intent")


def main(report_path: str, gold_path: str) -> int:
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    gold = [json.loads(line) for line in
            Path(gold_path).read_text(encoding="utf-8").splitlines() if line.strip()]
    bucket_of: dict[str, list[str]] = defaultdict(list)
    for row in gold:
        bucket_of[row["query"]].append(row["bucket"])

    by_bucket: dict[str, list[dict]] = defaultdict(list)
    unmatched = 0
    for case in report.get("cases") or []:
        buckets = bucket_of.get(case["query"])
        if not buckets:
            unmatched += 1
            continue
        by_bucket[buckets.pop(0) if len(buckets) > 1 else buckets[0]].append(case)

    failed = report.get("failed") or []
    if failed:
        print("! %d 个用例请求失败，下面每一栏都缺了它们；不要当成全量。" % len(failed))
        for f in failed[:10]:
            print("    %s  %s" % (f.get("query", "")[:30], f.get("error", "")))
    if unmatched:
        print("! %d 个用例在 gold.jsonl 里找不到，可能报告与金标准不是同一次生成的" % unmatched)

    print("\n%-14s %5s  %-16s %-16s" % ("bucket", "n", "recall@10", "MRR"))
    for bucket in ("canonical", "alias", "origin_intent", "description", "description_model", "negative"):
        cases = by_bucket.get(bucket) or []
        if not cases:
            continue
        if bucket == "negative":
            right = [c for c in cases if c.get("correct_abstention")]
            if len(cases) < MIN_NEGATIVES:
                print("%-14s %5d  反例少于 %d 条，弃答率不单独报告"
                      % (bucket, len(cases), MIN_NEGATIVES))
            else:
                print("%-14s %5d  正确弃答 %d（%.2f）"
                      % (bucket, len(cases), len(right), len(right) / len(cases)))
            continue
        scored = [c for c in cases if c.get("recall_at_10") is not None]
        if not scored:
            continue
        print("%-14s %5d  %-16.3f %-16.3f"
              % (bucket, len(scored),
                 mean(c["recall_at_10"] for c in scored),
                 mean(c["reciprocal_rank"] for c in scored)))

    named = [c for b in NAMED for c in by_bucket.get(b) or []
             if c.get("recall_at_10") is not None]
    free = [c for c in by_bucket.get("description") or []
            if c.get("recall_at_10") is not None]
    if named:
        print("\n查询里含梗名的 %d 条：recall %.3f（只能证明拼写对得上）"
              % (len(named), mean(c["recall_at_10"] for c in named)))
    if free:
        print("不含梗名的 %d 条：recall %.3f  MRR %.3f" %
              (len(free), mean(c["recall_at_10"] for c in free),
               mean(c["reciprocal_rank"] for c in free)))
        missed = [c for c in free if c["recall_at_10"] < 1]
        if missed:
            print("\n没能召回的描述型查询（这才是有信息量的部分）：")
            for c in missed:
                print("  recall %.2f  %s" % (c["recall_at_10"], c["query"]))
    else:
        print("\n没有 description 用例：这一次跑不出任何关于检索质量的结论。")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(args[0], args[1] if len(args) > 1 else str(ROOT / "evals/gold.jsonl")))
