"""Evaluate a curator-provided JSONL gold set; never seed cultural facts."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from statistics import mean

import httpx
from checkpoint import Checkpoint, public_snapshot

# ADR 0002 条款 3：反例少于 8 条时弃答率不可单独报告。
MIN_NEGATIVES = 8

# Windows consoles default to cp1252; both the gold set and this report are Chinese.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def fold(name: str) -> str:
    return name.strip().casefold()


def names_of(item: dict) -> set[str]:
    """Every reviewed name an item answers to, not just the one the curator happened to pick.

    Matching on canonical_name alone charges the metric for naming disagreement between the
    curator and the reviewer, which is not a retrieval failure. Aliases here are the published
    ones on the meme record, so this stays inside the reviewed boundary.
    """
    return {
        fold(x)
        for x in [item["canonical_name"], *(item.get("aliases") or [])]
        if x and x.strip()
    }


parser = argparse.ArgumentParser()
parser.add_argument("gold")
parser.add_argument("--api", default="http://localhost:8100")
# One reranked call scores up to retrieval_candidate_cap pairs through a 568M-parameter
# cross-encoder on CPU at full precision: 50 to 100 seconds each, two per case. The old
# 120s default timed out mid-run and threw away every measurement taken before it.
parser.add_argument("--timeout", type=float, default=600)
parser.add_argument(
    "--checkpoint", type=Path, help="Durable SQLite journal; completed cases are reused"
)
parser.add_argument(
    "--run-context",
    type=Path,
    help="Frozen JSON containing model and configuration identities",
)
args = parser.parse_args()
if args.checkpoint and not args.run_context:
    parser.error(
        "--checkpoint requires --run-context with pinned model/configuration identities"
    )
gold_bytes = Path(args.gold).read_bytes()
rows = [
    json.loads(line) for line in gold_bytes.decode("utf-8").splitlines() if line.strip()
]
results = []
failures = []
with httpx.Client(base_url=args.api, timeout=args.timeout, trust_env=False) as client:
    checkpoint = None
    snapshot = None
    if args.checkpoint:
        context_bytes = args.run_context.read_bytes()
        context = json.loads(context_bytes.decode("utf-8"))
        model = context.get("model")
        if (
            not isinstance(model, dict)
            or not model.get("identifier")
            or len(str(model.get("sha256", ""))) != 64
            or any(
                c not in "0123456789abcdefABCDEF" for c in str(model.get("sha256", ""))
            )
            or not context.get("configuration")
        ):
            parser.error(
                "run context requires model identifier/artifact sha256 and configuration"
            )
        snapshot = public_snapshot(client)
        runner_bytes = (
            Path(__file__).read_bytes()
            + Path(__file__).with_name("checkpoint.py").read_bytes()
        )
        checkpoint = Checkpoint(
            args.checkpoint,
            {
                "operator_context": context,
                "corpus": snapshot,
                "api": args.api,
                "gold": hashlib.sha256(gold_bytes).hexdigest(),
                "runner": hashlib.sha256(runner_bytes).hexdigest(),
            },
        )
    for index, row in enumerate(rows, 1):
        saved = checkpoint.get(index) if checkpoint else None
        if saved is not None:
            results.append(saved)
            print(
                "[%2d/%d] resumed %s" % (index, len(rows), row["query"]),
                file=sys.stderr,
                flush=True,
            )
            continue
        began = time.monotonic()
        # Progress goes to stderr so stdout stays a single JSON document.
        print(
            "[%2d/%d] %s" % (index, len(rows), row["query"]),
            file=sys.stderr,
            flush=True,
        )
        try:
            response = client.post(
                "/v1/search", json={"query": row["query"], "limit": 10}
            )
            response.raise_for_status()
            search = response.json()
            item_names = [names_of(x) for x in search["items"]]
            expected = {fold(x) for x in row["expected_names"]}
            ranks = [i for i, names in enumerate(item_names, 1) if names & expected]
            found = {name for names in item_names for name in names & expected}
            response = client.post("/v1/answers", json={"query": row["query"]})
            response.raise_for_status()
            answer = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            failures.append({"query": row["query"], "error": type(exc).__name__})
            print("       x %s" % type(exc).__name__, file=sys.stderr, flush=True)
            continue
        citations = {x["evidence_id"] for x in answer["citations"]}
        resolvable = all(
            client.get("/v1/evidence/%s" % eid).status_code == 200 for eid in citations
        )
        coverage = all(
            set(x["evidence_ids"]) <= citations and x["evidence_ids"]
            for x in answer["claims"]
        )
        print("       %.0fs" % (time.monotonic() - began), file=sys.stderr, flush=True)
        results.append(
            {
                "query": row["query"],
                "recall_at_10": len(found) / len(expected) if expected else None,
                "reciprocal_rank": 1 / min(ranks) if ranks else 0,
                "citations_resolve": resolvable,
                "structural_citation_coverage": bool(coverage),
                "correct_abstention": not answer["claims"]
                if not row["answerable"]
                else None,
                "answer_matches_expected": any(
                    fold(c.get("meme_name", "")) in expected for c in answer["claims"]
                )
                if row["answerable"]
                else None,
                "answer_claims": answer["claims"],
                "answer_citations": answer["citations"],
                "degraded": search["degraded"],
            }
        )
        if checkpoint:
            checkpoint.save(index, results[-1])
    if checkpoint:
        try:
            if (
                public_snapshot(client) != snapshot
                or Path(args.gold).read_bytes() != gold_bytes
                or args.run_context.read_bytes() != context_bytes
                or Path(__file__).read_bytes()
                + Path(__file__).with_name("checkpoint.py").read_bytes()
                != runner_bytes
            ):
                failures.append({"query": "<run-context>", "error": "ContextChanged"})
        except httpx.HTTPError as exc:
            failures.append({"query": "<run-context>", "error": type(exc).__name__})
        checkpoint.finish(not failures and len(results) == len(rows))
        checkpoint.close()

positive = [x for x in results if x["recall_at_10"] is not None]
refusals = [x for x in results if x["correct_abstention"] is not None]
report = {
    "cases": results,
    "recall_at_10": mean(x["recall_at_10"] for x in positive) if positive else None,
    "mrr": mean(x["reciprocal_rank"] for x in positive) if positive else None,
    "answer_identity_match_rate": mean(
        bool(x["answer_matches_expected"]) for x in positive
    )
    if positive
    else None,
    "note": "引用可解析和结构覆盖不等于语义支持率；语义支持与起源判断仍需人工金标准。",
}
if args.checkpoint:
    report["checkpoint"] = str(args.checkpoint)
    report["run_context"] = context
    report["corpus_sha256"] = snapshot
# ADR 0002 clause 3: fewer than eight negatives and this number is not reportable on its
# own. Suppressing it here rather than in prose means it cannot be quoted by accident.
if len(refusals) >= MIN_NEGATIVES:
    report["correct_abstention"] = mean(
        1.0 if x["correct_abstention"] else 0.0 for x in refusals
    )
    report["correct_abstention_n"] = len(refusals)
else:
    report["correct_abstention"] = None
    report["correct_abstention_note"] = (
        "反例 %d 条，少于 ADR 0002 要求的 %d 条；弃答率不单独报告"
        % (
            len(refusals),
            MIN_NEGATIVES,
        )
    )
if failures:
    # A partial run is not a smaller run: the cases that failed are missing, not zero.
    report["failed"] = failures
    report["recall_at_10"] = None
    report["mrr"] = None
    report["answer_identity_match_rate"] = None
    report["correct_abstention"] = None
    report["note"] = (
        "%d 个用例请求失败，聚合指标全部作废；修好后重跑，不要把部分结果当全量。"
        % len(failures)
    )
print(json.dumps(report, ensure_ascii=False, indent=2))
