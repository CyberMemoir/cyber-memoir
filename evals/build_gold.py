#!/usr/bin/env python3
"""Generate gold.jsonl from the curation records and _negatives.yaml.

    python evals/build_gold.py

The curation YAMLs are the source of truth; this file is derived, so never edit
gold.jsonl by hand. Positive cases come from each record's gold block, negatives
from _negatives.yaml. A query that names a curated meme is refused as a negative,
because that would score a correct answer as a failed abstention.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "evals" / "curation"
TARGET = ROOT / "evals" / "gold.jsonl"
# must_not_return is a cross-check note, not a case the harness can score.
POSITIVE_BUCKETS = ("canonical", "alias", "origin_intent", "polysemy", "adversarial")


def normalize(text) -> str:
    return " ".join(unicodedata.normalize("NFKC", str(text)).casefold().split())


def main() -> int:
    rows, surfaces, kinds = [], {}, Counter()
    for path in sorted(CURATION.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        name = doc["canonical_name"]
        for value in [name, *(doc.get("aliases") or [])]:
            surfaces[normalize(value)] = name
        for bucket in POSITIVE_BUCKETS:
            for query in (doc.get("gold") or {}).get(bucket) or []:
                rows.append({"query": str(query), "expected_names": [name], "answerable": True})
                kinds[bucket] += 1

    negatives = yaml.safe_load((CURATION / "_negatives.yaml").read_text(encoding="utf-8")) or {}
    for item in negatives.get("negatives") or []:
        query = str(item.get("query", "")).strip()
        hit = surfaces.get(normalize(query))
        if hit:
            print("  ! 跳过反例 %r：它其实是已收录的《%s》" % (query, hit))
            continue
        rows.append({"query": query, "expected_names": [], "answerable": False})
        kinds["negative:" + str(item.get("kind", "?"))] += 1

    seen: dict[str, int] = {}
    unique = []
    for row in rows:
        key = normalize(row["query"])
        if key in seen:
            print("  ! 查询重复，已去重：%r" % row["query"])
            continue
        seen[key] = 1
        unique.append(row)

    TARGET.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in unique), encoding="utf-8"
    )
    positives = sum(1 for r in unique if r["answerable"])
    print("-> %s   %d 条（正例 %d，反例 %d）" % (TARGET.name, len(unique), positives, len(unique) - positives))
    print("   构成：%s" % dict(kinds))
    if len(unique) - positives < 8:
        print("   ! 反例少于 ADR 0002 要求的 8 条，弃答率不可单独报告")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
