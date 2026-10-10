"""Offline real BGE query-vector equality, timing and concurrency probe; not a RAG quality test."""

import argparse
import hashlib
import json
import os
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from model_probe import manifest
from run import code_fingerprint, read_rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--embedding-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("report must be a new file")
    raw = args.gold.read_bytes()
    probe_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    model, manifest_sha = manifest(args.embedding_manifest, "embedder")
    from cyber_memoir.config import Settings, settings

    Settings.model_config["env_file"] = None
    os.environ.update(
        {
            "EMBEDDING_BACKEND": "local",
            "EMBEDDING_MODEL": model["directory"],
            "EMBEDDING_DEVICE": "cpu",
            "EMBEDDING_THREADS": "4",
            "RERANKER_BACKEND": "disabled",
            "LLM_BASE_URL": "",
            "LLM_MODEL": "",
            "LLM_API_KEY": "",
            "DATABASE_URL": "sqlite://",
            "OPENSEARCH_URL": "",
            "AUTO_MEDIA": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
    settings.cache_clear()
    from cyber_memoir.adapters import inference
    from cyber_memoir.domain.schemas import normalize

    queries = [normalize(row["query"]) for row in read_rows(raw)]
    if len(queries) < 6 or len(set(queries)) != len(queries):
        raise ValueError("probe requires at least six distinct normalized queries")
    code = code_fingerprint()
    began = time.perf_counter()
    inference.embed([queries[0]])
    cold = time.perf_counter() - began
    actual = inference.embedder()
    original = actual.encode
    counters = {"calls": 0, "active": 0, "peak": 0}
    guard = threading.Lock()

    def tracked(*args, **kwargs):
        with guard:
            counters["calls"] += 1
            counters["active"] += 1
            counters["peak"] = max(counters["peak"], counters["active"])
        try:
            return original(*args, **kwargs)
        finally:
            with guard:
                counters["active"] -= 1

    actual.encode = tracked
    cases = []
    try:
        for index, query in enumerate(queries):
            inference._QUERY_VECTORS.clear()
            started = time.perf_counter()
            baseline = inference.embed([query])[0]
            baseline_seconds = time.perf_counter() - started
            started = time.perf_counter()
            miss = inference.embed_query(query)
            miss_seconds = time.perf_counter() - started
            started = time.perf_counter()
            hit = inference.embed_query(query)
            hit_seconds = time.perf_counter() - started
            delta = max(abs(a - b) for a, b in zip(baseline, miss, strict=True))
            if delta != 0 or miss != hit:
                raise ValueError("query cache changed actual BGE vectors")
            cases.append(
                {
                    "index": index + 1,
                    "baseline_seconds": baseline_seconds,
                    "miss_seconds": miss_seconds,
                    "hit_seconds": hit_seconds,
                    "max_absolute_difference": delta,
                }
            )
            print(f"query {index + 1}/{len(queries)}", file=sys.stderr, flush=True)
        concurrency = {}
        for name, inputs in [("same", [queries[0]] * 6), ("distinct", queries[:6])]:
            inference._QUERY_VECTORS.clear()
            counters.update(calls=0, active=0, peak=0)
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=6) as pool:
                outputs = list(pool.map(inference.embed_query, inputs))
            expected_calls = 1 if name == "same" else 6
            if counters["calls"] != expected_calls or counters["peak"] != 1:
                raise ValueError("unexpected actual encoding concurrency")
            if name == "same" and any(vector != outputs[0] for vector in outputs):
                raise ValueError("concurrent vectors differ")
            concurrency[name] = {
                "actual_encode_calls": counters["calls"],
                "peak": counters["peak"],
                "seconds": time.perf_counter() - started,
            }
    finally:
        actual.encode = original
        inference._QUERY_VECTORS.clear()
    if (
        args.gold.read_bytes() != raw
        or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != probe_sha
        or code_fingerprint() != code
        or manifest(args.embedding_manifest, "embedder")[1] != manifest_sha
    ):
        raise ValueError("probe inputs, code or model changed; no valid report")
    result = {
        "status": "complete",
        "scope": "offline_real_query_vector_component_not_http_or_RAG",
        "gold_sha256": hashlib.sha256(raw).hexdigest(),
        "runner_and_backend_sha256": code,
        "probe_sha256": probe_sha,
        "model": {
            "identifier": model["repo"],
            "revision": model["revision"],
            "sha256": model["files"]["pytorch_model.bin"]["sha256"],
        },
        "configuration": {
            "device": "cpu",
            "threads": 4,
            "fp16": False,
            "cache_limit": inference._QUERY_VECTOR_LIMIT,
            "ttl": inference._QUERY_VECTOR_TTL,
        },
        "cold_seconds": cold,
        "cases": cases,
        "concurrency": concurrency,
        "medians": {
            key: statistics.median(row[key] for row in cases)
            for key in ["baseline_seconds", "miss_seconds", "hit_seconds"]
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps({"cases": len(cases), "medians": result["medians"], "concurrency": concurrency}))


if __name__ == "__main__":
    main()
