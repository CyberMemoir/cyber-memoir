"""Evaluate a curator-provided JSONL gold set; never seed cultural facts."""

import argparse
import json
from statistics import mean

import httpx

parser = argparse.ArgumentParser()
parser.add_argument("gold")
parser.add_argument("--api", default="http://localhost:8100")
args = parser.parse_args()
rows = [json.loads(line) for line in open(args.gold) if line.strip()]
results = []
with httpx.Client(base_url=args.api, timeout=120, trust_env=False) as client:
    for row in rows:
        response = client.post("/v1/search", json={"query": row["query"], "limit": 10})
        response.raise_for_status()
        search = response.json()
        names = [x["canonical_name"] for x in search["items"]]
        expected = set(row["expected_names"])
        ranks = [i for i, name in enumerate(names, 1) if name in expected]
        response = client.post("/v1/answers", json={"query": row["query"]})
        response.raise_for_status()
        answer = response.json()
        citations = {x["evidence_id"] for x in answer["citations"]}
        resolvable = all(client.get(f"/v1/evidence/{eid}").status_code == 200 for eid in citations)
        coverage = all(set(x["evidence_ids"]) <= citations and x["evidence_ids"] for x in answer["claims"])
        results.append(
            {
                "query": row["query"],
                "recall_at_10": len(expected.intersection(names)) / len(expected) if expected else None,
                "reciprocal_rank": 1 / min(ranks) if ranks else 0,
                "citations_resolve": resolvable,
                "structural_citation_coverage": bool(coverage),
                "correct_abstention": not answer["claims"] if not row["answerable"] else None,
                "degraded": search["degraded"],
            }
        )
positive = [x for x in results if x["recall_at_10"] is not None]
print(
    json.dumps(
        {
            "cases": results,
            "recall_at_10": mean(x["recall_at_10"] for x in positive) if positive else None,
            "mrr": mean(x["reciprocal_rank"] for x in positive) if positive else None,
            "note": "引用可解析和结构覆盖不等于语义支持率；语义支持与起源判断仍需人工金标准。",
        },
        ensure_ascii=False,
        indent=2,
    )
)
