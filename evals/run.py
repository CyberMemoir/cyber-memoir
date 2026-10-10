"""Evaluate frozen public records and curator queries; never publish or rewrite facts."""

import argparse
import hashlib
import json
import math
import sqlite3
import sys
import time
from contextlib import ExitStack
from pathlib import Path
from statistics import mean
from urllib.parse import urlparse

import httpx
from checkpoint import Checkpoint, collect_public_snapshot, digest, public_snapshot

MIN_NEGATIVES = 8
ROOT = Path(__file__).resolve().parents[1]
METRICS = ("recall_at_10", "mrr", "answer_identity_match_rate", "correct_abstention")


def validate_context(context):
    if (
        not isinstance(context, dict)
        or not isinstance(context.get("configuration"), dict)
        or not context["configuration"]
    ):
        raise ValueError("Run context requires configuration")

    def provider(model, legacy=False):
        if (
            not isinstance(model, dict)
            or not isinstance(model.get("identifier"), str)
            or not model["identifier"].strip()
        ):
            raise ValueError("Model provider requires identity")
        enabled = model.get("enabled", True if legacy else None)
        if type(enabled) is not bool:
            raise ValueError("Model provider requires explicit enabled state")
        if not enabled:
            if model["identifier"] != "disabled" or model.get("sha256"):
                raise ValueError("Disabled providers must not claim a weight artifact")
        elif (
            model["identifier"] == "disabled"
            or len(str(model.get("sha256", ""))) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in str(model.get("sha256", "")))
        ):
            raise ValueError("Active model requires identifier/artifact sha256")

    if "models" in context:
        models = context["models"]
        if not isinstance(models, dict) or set(models) != {"embedding", "reranker", "llm"}:
            raise ValueError("Run context must identify all three model providers")
        for model in models.values():
            provider(model)
    else:
        provider(context.get("model"), legacy=True)


class PacedClient:
    def __init__(self, client, interval):
        self.client, self.interval, self.last = client, interval, None
        self.sleep_seconds, self.post_seconds = 0.0, 0.0
        self.post_timings = []

    def __getattr__(self, name):
        return getattr(self.client, name)

    def post(self, path, **kwargs):
        now = time.monotonic()
        wait = max(0.0, self.interval - (now - self.last)) if self.last is not None else 0.0
        if wait:
            time.sleep(wait)
            self.sleep_seconds += wait
        began = self.last = time.monotonic()
        try:
            return self.client.post(path, **kwargs)
        finally:
            seconds = time.monotonic() - began
            self.post_seconds += seconds
            self.post_timings.append({"path": path, "http_seconds": seconds})


def fold(name: str) -> str:
    return name.strip().casefold()


def names_of(item: dict) -> set[str]:
    return {fold(x) for x in [item["canonical_name"], *(item.get("aliases") or [])] if x and x.strip()}


def code_fingerprint():
    paths = [Path(__file__), Path(__file__).with_name("checkpoint.py")]
    paths += sorted((ROOT / "apps/backend/src/cyber_memoir").rglob("*.py"))
    paths += [ROOT / "apps/backend/pyproject.toml", ROOT / "apps/backend/uv.lock"]
    return digest(
        [(str(p.relative_to(ROOT)), hashlib.sha256(p.read_bytes()).hexdigest()) for p in paths if p.is_file()]
    )


def read_rows(raw):
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("Gold set must contain at least one case")
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("query"), str) or not row["query"].strip():
            raise ValueError("Every case requires a nonempty query")
        names = row.get("expected_names")
        if not isinstance(names, list) or not all(isinstance(n, str) and n.strip() for n in names):
            raise ValueError("expected_names must contain nonempty strings")
        if type(row.get("answerable")) is not bool or bool(names) != row["answerable"]:
            raise ValueError("answerable and expected_names disagree")
    return rows


def evaluate_case(client, row):
    response = client.post("/v1/search", json={"query": row["query"], "limit": 10})
    response.raise_for_status()
    search = response.json()
    response = client.post("/v1/answers", json={"query": row["query"]})
    response.raise_for_status()
    answer = response.json()
    degraded = list(dict.fromkeys([*search.get("degraded", []), *answer.get("degraded", [])]))
    if "corpus_changed_during_search" in degraded:
        raise ValueError("ContextChangedDuringCase")
    item_names = [names_of(item) for item in search["items"]]
    expected = {fold(x) for x in row["expected_names"]}
    ranks = [i for i, names in enumerate(item_names, 1) if names & expected]
    found = {name for names in item_names for name in names & expected}
    citations = {x["evidence_id"] for x in answer["citations"]}
    resolvable = True
    for identifier in sorted(citations):
        response = client.get(f"/v1/evidence/{identifier}")
        if response.status_code == 404:
            resolvable = False
        else:
            response.raise_for_status()
    coverage = all(set(c["evidence_ids"]) <= citations and c["evidence_ids"] for c in answer["claims"])
    return {
        "query": row["query"],
        "bucket": row.get("bucket"),
        "query_source": row.get("query_source", "unattributed"),
        "recall_at_10": len(found) / len(expected) if expected else None,
        "reciprocal_rank": 1 / min(ranks) if ranks else 0,
        "citations_resolve": resolvable,
        "structural_citation_coverage": bool(coverage),
        "citation_count": len(citations),
        "correct_abstention": not answer["claims"] if not row["answerable"] else None,
        "answer_matches_expected": any(fold(c.get("meme_name", "")) in expected for c in answer["claims"])
        if row["answerable"]
        else None,
        "answer_claims": answer["claims"],
        "answer_citations": answer["citations"],
        "degraded": degraded,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("gold", type=Path)
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--run-context", type=Path)
    parser.add_argument("--request-interval", type=float, default=0.0)
    args = parser.parse_args(argv)
    if args.checkpoint and not args.run_context:
        parser.error("--checkpoint requires --run-context with pinned model/configuration identities")
    if args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("--timeout must be finite and positive")
    if args.request_interval < 0 or not math.isfinite(args.request_interval):
        parser.error("--request-interval must be finite and nonnegative")
    api = urlparse(args.api)
    if (
        api.scheme not in {"http", "https"}
        or not api.hostname
        or api.username
        or api.password
        or api.query
        or api.fragment
    ):
        parser.error("API URL must be HTTP(S), without credentials, query parameters or fragments")

    results, failures = [], []
    context, snapshot, checkpoint = None, None, None
    invalidated = False
    try:
        gold_bytes = args.gold.read_bytes()
        rows = read_rows(gold_bytes)
        original_code = code_fingerprint()
        context_bytes = args.run_context.read_bytes() if args.run_context else None
        context = json.loads(context_bytes.decode("utf-8")) if context_bytes else None
        if args.run_context:
            validate_context(context)

        with ExitStack() as stack:
            client = stack.enter_context(
                httpx.Client(base_url=args.api, timeout=args.timeout, trust_env=False, follow_redirects=False)
            )
            client = PacedClient(client, args.request_interval)
            if context is not None:
                collection = collect_public_snapshot(client)
                snapshot = digest(collection)
                public_names = {name for record in collection["records"] for name in names_of(record)}
                missing = {
                    name for row in rows for name in row["expected_names"] if fold(name) not in public_names
                }
                if missing:
                    raise ValueError(
                        "Positive gold targets are not currently public: " + ", ".join(sorted(missing))
                    )
                if args.checkpoint:
                    checkpoint = stack.enter_context(
                        Checkpoint(
                            args.checkpoint,
                            {
                                "operator_context": context,
                                "corpus": snapshot,
                                "api": args.api,
                                "gold": hashlib.sha256(gold_bytes).hexdigest(),
                                "runner_and_backend": original_code,
                                "request_interval": args.request_interval,
                            },
                        )
                    )
            for index, row in enumerate(rows, 1):
                saved = checkpoint.get(index) if checkpoint else None
                if saved is not None:
                    if saved.get("query") != row["query"]:
                        checkpoint.invalidate("SavedCaseChanged")
                        invalidated = True
                        raise ValueError("SavedCaseChanged")
                    results.append(saved)
                    print(f"[{index}/{len(rows)}] resumed {row['query']}", file=sys.stderr, flush=True)
                    continue
                began = time.monotonic()
                print(f"[{index}/{len(rows)}] {row['query']}", file=sys.stderr, flush=True)
                try:
                    sleeping, posting = client.sleep_seconds, client.post_seconds
                    start_request = len(client.post_timings)
                    result = evaluate_case(client, row)
                    result["pacing_seconds"] = client.sleep_seconds - sleeping
                    result["post_http_seconds"] = client.post_seconds - posting
                    result["post_requests"] = client.post_timings[start_request:]
                except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                    changed = str(exc) == "ContextChangedDuringCase"
                    failures.append(
                        {"query": row["query"], "error": "ContextChanged" if changed else type(exc).__name__}
                    )
                    print(f"       x {type(exc).__name__}", file=sys.stderr, flush=True)
                    if changed:
                        invalidated = True
                        break
                    continue
                result["elapsed_seconds"] = time.monotonic() - began
                results.append(result)
                if checkpoint:
                    checkpoint.save(index, result)
            # Even a non-checkpoint run cannot use a changed query file or local scoring code.
            try:
                changed = args.gold.read_bytes() != gold_bytes or code_fingerprint() != original_code
                if args.run_context:
                    changed |= (
                        args.run_context.read_bytes() != context_bytes or public_snapshot(client) != snapshot
                    )
                if changed:
                    failures.append({"query": "<run-context>", "error": "ContextChanged"})
                    invalidated = True
            except (httpx.HTTPError, ValueError, OSError) as exc:
                failures.append({"query": "<run-context>", "error": type(exc).__name__})
            if checkpoint:
                if invalidated:
                    checkpoint.invalidate("ContextChanged")
                else:
                    checkpoint.finish(not failures and len(results) == len(rows))
    except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, httpx.HTTPError) as exc:
        failures.append({"query": "<run-context>", "error": type(exc).__name__, "detail": str(exc)})

    positive = [r for r in results if r.get("recall_at_10") is not None]
    negative = [r for r in results if r.get("correct_abstention") is not None]
    report = {
        "status": "failed" if failures else "complete",
        "cases": results,
        "gold_sha256": hashlib.sha256(gold_bytes).hexdigest() if "gold_bytes" in locals() else None,
        "recall_at_10": mean(r["recall_at_10"] for r in positive) if positive else None,
        "mrr": mean(r["reciprocal_rank"] for r in positive) if positive else None,
        "answer_identity_match_rate": mean(bool(r["answer_matches_expected"]) for r in positive)
        if positive
        else None,
        "correct_abstention": mean(bool(r["correct_abstention"]) for r in negative)
        if len(negative) >= MIN_NEGATIVES
        else None,
        "correct_abstention_n": len(negative),
        "note": "引用可解析、结构覆盖和身份匹配不等于事实正确或语义支持；仍需独立人工核查。",
    }
    if len(negative) < MIN_NEGATIVES:
        report["correct_abstention_note"] = (
            f"反例 {len(negative)} 条，少于 {MIN_NEGATIVES} 条；弃答率不单独报告"
        )
    if args.checkpoint:
        report["checkpoint"] = str(args.checkpoint)
    if context is not None:
        report.update(run_context=context, corpus_sha256=snapshot)
    if failures:
        report["failed"] = failures
        for key in METRICS:
            report[key] = None
        report["note"] = (
            "存在请求或上下文失败，聚合指标作废；保留的完整用例可在相同上下文中恢复，失效检查点需另建。"
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False))
    return 1 if failures else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
