"""Actual HTTP admission/cached-read/retry probe over an owned frozen archive API."""

import argparse
import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
from checkpoint import collect_public_snapshot, digest
from run import code_fingerprint, read_rows, validate_context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("report must be a new file")
    folder = args.snapshot.resolve()
    gold = (folder / "public-gold.jsonl").read_bytes()
    rows = read_rows(gold)
    public_bytes = (folder / "public.json").read_bytes()
    expected = digest(json.loads(public_bytes))
    context_bytes = (folder / "context-hybrid.json").read_bytes()
    context = json.loads(context_bytes)
    validate_context(context)
    if not context["configuration"].get("inference_tracing") or context["configuration"].get(
        "paired_cpu_profiling"
    ):
        raise ValueError("requires normal owned inference tracing")
    code = code_fingerprint()
    probe_bytes = Path(__file__).read_bytes()
    trace_path = folder / "inference-trace.jsonl"

    def call(row, identifier):
        with httpx.Client(base_url="http://127.0.0.1:8103", timeout=180, trust_env=False) as client:
            start = time.perf_counter()
            response = client.post(
                "/v1/search",
                json={"query": row["query"], "limit": 10},
                headers={"X-Cyber-Memoir-Trace": identifier},
            )
            seconds = time.perf_counter() - start
        if (
            response.headers.get("X-Cyber-Memoir-Evaluation") != args.run_id
            or response.headers.get("X-Cyber-Memoir-Trace") != identifier
        ):
            raise ValueError("response ownership/trace identity mismatch")
        body = response.json()
        if response.status_code == 200:
            if body.get("degraded"):
                raise ValueError("accepted request degraded")
        elif response.status_code == 503:
            if body.get("code") != "inference_busy" or "items" in body or "claims" in body:
                raise ValueError("busy rejection substituted unscored content")
            if response.headers.get("Retry-After") != str(body["retry_after_seconds"]):
                raise ValueError("Retry-After does not match typed body")
        else:
            response.raise_for_status()
        return {
            "request_id": identifier,
            "status": response.status_code,
            "http_seconds": seconds,
            "retry_after_seconds": body.get("retry_after_seconds"),
        }

    with httpx.Client(base_url="http://127.0.0.1:8103", timeout=60, trust_env=False) as client:
        response = client.get("/v1/stats")
        response.raise_for_status()
        if response.headers.get("X-Cyber-Memoir-Evaluation") != args.run_id:
            raise ValueError("not the owned API")
        if digest(collect_public_snapshot(client)) != expected:
            raise ValueError("wrong frozen public corpus")
    warm = call(rows[-1], uuid4().hex)
    if warm["status"] != 200:
        raise ValueError("warmup rejected")
    active_id = uuid4().hex
    with ThreadPoolExecutor(max_workers=6) as pool:
        active = pool.submit(call, rows[0], active_id)
        # A start marker inside the actual compute method, under the model lock.
        # An observation timeout never restarts this live request.
        while not active.done():
            events = [json.loads(line) for line in trace_path.read_text().splitlines() if line]
            if any(
                event["request_id"] == active_id and event["stage"] == "reranker_compute_start"
                for event in events
            ):
                break
            time.sleep(0.05)
        else:
            raise ValueError("active request completed before compute could be observed")
        waiting = [pool.submit(call, row, uuid4().hex) for row in rows[1:6]]
        busy = [future.result() for future in waiting]
        if any(row["status"] != 503 for row in busy):
            raise ValueError("load did not trigger the tested admission boundary")
        if active.done():
            raise ValueError("model was not still active for cached-read test")
        cached = call(rows[-1], uuid4().hex)
        if cached["status"] != 200 or active.done():
            raise ValueError("cached query blocked behind the unrelated inference")
        completed = active.result()
    if completed["status"] != 200:
        raise ValueError("admitted inference failed")
    retry = call(rows[1], uuid4().hex)
    if retry["status"] != 200:
        raise ValueError("explicit retry was not admitted after the model became available")
    with httpx.Client(base_url="http://127.0.0.1:8103", timeout=60, trust_env=False) as client:
        if digest(collect_public_snapshot(client)) != expected:
            raise ValueError("public corpus changed")
    if (
        (folder / "public-gold.jsonl").read_bytes() != gold
        or (folder / "public.json").read_bytes() != public_bytes
        or (folder / "context-hybrid.json").read_bytes() != context_bytes
        or code_fingerprint() != code
        or Path(__file__).read_bytes() != probe_bytes
    ):
        raise ValueError("probe inputs/code changed")
    raw = trace_path.read_bytes()
    events = [json.loads(line) for line in raw.decode().splitlines() if line]
    busy_ids = {row["request_id"] for row in busy}
    if any(event["request_id"] in busy_ids and event["stage"] == "reranker_compute" for event in events):
        raise ValueError("rejected requests still ran cross-encoder scoring")
    if any(
        event["request_id"] == cached["request_id"] and event["stage"].endswith("_compute")
        for event in events
    ):
        raise ValueError("cached query was recomputed")
    result = {
        "status": "complete",
        "scope": "actual_owned_HTTP_admission_not_throughput_or_SLA",
        "context": context,
        "corpus_sha256": expected,
        "gold_sha256": hashlib.sha256(gold).hexdigest(),
        "runner_and_backend_sha256": code,
        "probe_sha256": hashlib.sha256(probe_bytes).hexdigest(),
        "trace_sha256": hashlib.sha256(raw).hexdigest(),
        "warmup": warm,
        "admitted": completed,
        "busy": busy,
        "cached_during_unrelated_inference": cached,
        "retry_after_capacity": retry,
        "rejected_requests_ran_no_reranker_compute": True,
        "rejected_request_embedding_computes": sum(
            event["request_id"] in busy_ids and event["stage"] == "embedding_compute" for event in events
        ),
        "cached_reply_finished_before_unrelated_model": True,
    }
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
    print(
        json.dumps(
            {
                "admitted": completed["http_seconds"],
                "busy_seconds": [row["http_seconds"] for row in busy],
                "cached_seconds": cached["http_seconds"],
                "retry_status": retry["status"],
            }
        )
    )


if __name__ == "__main__":
    main()
