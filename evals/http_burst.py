"""Six real concurrent search requests against an owned, normally traced evaluation API."""

import argparse
import hashlib
import json
import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from checkpoint import collect_public_snapshot, digest
from run import code_fingerprint, names_of, read_rows, validate_context


def timing_summary(values):
    if not values or any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("timings must be nonempty, finite and nonnegative")
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {
        "n": len(values),
        "median": median,
        "p95_nearest_rank": ordered[math.ceil(0.95 * len(values)) - 1],
        "max": ordered[-1],
    }


def validate_burst_context(context):
    validate_context(context)
    if (
        not context["configuration"].get("inference_tracing")
        or context["configuration"].get("paired_cpu_profiling")
        or not all(
            context.get("models", {}).get(role, {}).get("enabled") for role in ["embedding", "reranker"]
        )
    ):
        raise ValueError("requires normal hybrid inference tracing, not paired profiling")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--mode", choices=["same", "distinct"], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    probe_bytes = Path(__file__).read_bytes()
    url = urlparse(args.api)
    if url.scheme != "http" or url.hostname not in {"127.0.0.1", "localhost"} or url.username or url.password:
        parser.error("only the explicitly owned loopback evaluation API is allowed")
    if args.out.exists():
        parser.error("report must be a new file")
    gold = args.gold.read_bytes()
    rows = read_rows(gold)
    context_bytes = args.context.read_bytes()
    context = json.loads(context_bytes)
    validate_burst_context(context)
    snapshot_bytes = args.snapshot.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    expected = digest(snapshot)
    code = code_fingerprint()
    if len(rows) < 7 or len({row["query"] for row in rows}) != len(rows):
        raise ValueError("requires at least seven distinct original gold queries")
    selected = [rows[0]] * 6 if args.mode == "same" else rows[:6]

    def checked(response, identifier=None):
        response.raise_for_status()
        if response.headers.get("X-Cyber-Memoir-Evaluation") != args.run_id:
            raise ValueError("response is not from the requested owned evaluation")
        if identifier and response.headers.get("X-Cyber-Memoir-Trace") != identifier:
            raise ValueError("request trace identity was not propagated")
        return response

    with httpx.Client(base_url=args.api, timeout=180, trust_env=False) as client:
        checked(client.get("/v1/stats"))
        if digest(collect_public_snapshot(client)) != expected:
            raise ValueError("live snapshot differs from the frozen input")
        warmup_id = uuid4().hex
        started = time.perf_counter()
        warmup = checked(
            client.post(
                "/v1/search",
                json={"query": rows[-1]["query"], "limit": 10},
                headers={"X-Cyber-Memoir-Trace": warmup_id},
            ),
            warmup_id,
        ).json()
        warmup_seconds = time.perf_counter() - started
        if warmup.get("degraded"):
            raise ValueError("warmup inference degraded")
    gate = threading.Barrier(6)
    burst_started = time.perf_counter()
    public = {row["id"]: row["published_revision"] for row in snapshot["records"]}

    def request(index):
        row = selected[index]
        identifier = uuid4().hex
        with httpx.Client(base_url=args.api, timeout=180, trust_env=False) as client:
            gate.wait(timeout=30)
            start = time.perf_counter()
            response = checked(
                client.post(
                    "/v1/search",
                    json={"query": row["query"], "limit": 10},
                    headers={"X-Cyber-Memoir-Trace": identifier},
                ),
                identifier,
            )
            elapsed = time.perf_counter() - start
            result = response.json()
        if result.get("degraded") or any(
            public.get(item["id"]) != item["published_revision"] for item in result["items"]
        ):
            raise ValueError("concurrent request degraded or returned an invalid public revision")
        expected_names = {name.strip().casefold() for name in row["expected_names"]}
        return {
            "index": index + 1,
            "request_id": identifier,
            "http_seconds": elapsed,
            "start_offset_seconds": start - burst_started,
            "query_sha256": hashlib.sha256(row["query"].encode()).hexdigest(),
            "target_retrieved": any(names_of(item) & expected_names for item in result["items"])
            if expected_names
            else None,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        cases = list(pool.map(request, range(6)))
    with httpx.Client(base_url=args.api, timeout=180, trust_env=False) as client:
        checked(client.get("/v1/stats"))
        if digest(collect_public_snapshot(client)) != expected:
            raise ValueError("public snapshot changed")
    if (
        args.gold.read_bytes() != gold
        or args.context.read_bytes() != context_bytes
        or args.snapshot.read_bytes() != snapshot_bytes
        or code_fingerprint() != code
        or Path(__file__).read_bytes() != probe_bytes
    ):
        raise ValueError("benchmark input or code changed")
    trace_raw = args.trace.read_bytes()
    events = [json.loads(line) for line in trace_raw.decode().splitlines() if line]
    identifiers = {case["request_id"] for case in cases}
    measured = [event for event in events if event["request_id"] in identifiers]
    if not measured or any(not event["ok"] for event in measured):
        raise ValueError("missing or failed inference trace")
    for case in cases:
        own = [event for event in measured if event["request_id"] == case["request_id"]]
        for stage in ["embedding_lock_wait", "reranker_lock_wait", "embedding_total", "reranker_total"]:
            entries = [event for event in own if event["stage"] == stage]
            if len(entries) != 1:
                raise ValueError("missing or duplicate per-request inference stage")
            case[stage + "_seconds"] = entries[0]["seconds"]
    counts = {
        stage: sum(event["stage"] == stage for event in measured)
        for stage in ["embedding_compute", "reranker_compute"]
    }
    target = 1 if args.mode == "same" else 6
    if any(count != target for count in counts.values()):
        raise ValueError("process was not fresh or misses were not deduplicated")
    report = {
        "status": "complete",
        "scope": "six_owned_real_search_requests_not_SLA",
        "mode": args.mode,
        "context": context,
        "snapshot_sha256": expected,
        "gold_sha256": hashlib.sha256(gold).hexdigest(),
        "trace_sha256": hashlib.sha256(trace_raw).hexdigest(),
        "runner_and_backend_sha256": code,
        "probe_sha256": hashlib.sha256(probe_bytes).hexdigest(),
        "warmup_http_seconds": warmup_seconds,
        "actual_model_calls": counts,
        "cases": cases,
        "http": timing_summary([case["http_seconds"] for case in cases]),
        "reranker_queue_wait": timing_summary([case["reranker_lock_wait_seconds"] for case in cases]),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, sort_keys=True)
    print(
        json.dumps(
            {
                "mode": args.mode,
                "http": report["http"],
                "queue": report["reranker_queue_wait"],
                "actual_calls": counts,
            }
        )
    )


if __name__ == "__main__":
    main()
