"""Offline definition-ranking probe using real production BGE adapters, not a public archive."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import statistics
import sys
import time
from pathlib import Path

import yaml
from model_assets import COMMON, MODELS, digest

ROOT = Path(__file__).resolve().parents[1]


def normalized(text):
    from cyber_memoir.domain.schemas import normalize

    return normalize(text)


def inputs(directory: Path):
    documents, hashes, records = [], {}, {}
    for path in sorted(directory.glob("*.yaml")):
        raw = path.read_bytes()
        hashes[path.name] = hashlib.sha256(raw).hexdigest()
        row = yaml.safe_load(raw.decode("utf-8"))
        if not isinstance(row, dict):
            raise ValueError(f"curation input must be a mapping: {path.name}")
        records[path.name] = row
        if path.name.startswith("_"):
            continue
        if row.get("resolved") is True and str(row.get("definition") or "").strip():
            name = row["canonical_name"]
            aliases = row.get("aliases") or []
            if (
                not isinstance(name, str)
                or not name.strip()
                or not isinstance(row["definition"], str)
                or not isinstance(row.get("usage_context") or "", str)
                or not isinstance(aliases, list)
                or any(not isinstance(value, str) or not value.strip() for value in aliases)
            ):
                raise ValueError("corpus names, aliases and definition fields must be text")
            documents.append(
                {
                    "name": name,
                    "aliases": aliases,
                    "text": "\n".join(
                        [name, " / ".join(aliases), row["definition"], row.get("usage_context") or ""]
                    ),
                    "file": path.name,
                    "drafted_by": (row.get("curation") or {}).get("drafted_by"),
                    "confirmed_by": (row.get("curation") or {}).get("confirmed_by"),
                }
            )
    names = {row["name"] for row in documents}
    if not documents or len({normalized(name) for name in names}) != len(documents):
        raise ValueError("corpus must have unique nonempty locally resolved definitions")
    descriptions = records["_descriptions.yaml"]
    cases, excluded = [], []
    for name, queries in descriptions.items():
        if not isinstance(queries, list):
            raise ValueError("each independent description entry must be a query list")
        for query in queries or []:
            if not isinstance(query, str) or not query.strip():
                raise ValueError("independent human queries must be nonempty strings")
            if name not in names:
                excluded.append({"name": name, "query": query, "reason": "no locally resolved definition"})
            else:
                cases.append({"query": query, "expected_names": [name], "kind": "human_description"})
    for row in records["_negatives.yaml"].get("negatives", []):
        query = row["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("negative queries must be nonempty strings")
        surfaces = [value for doc in documents for value in [doc["name"], *doc["aliases"]]]
        if normalized(query) in {normalized(value) for value in surfaces}:
            raise ValueError("a local corpus name cannot be a negative probe")
        if row["kind"] not in {"fabricated", "out_of_corpus"}:
            raise ValueError("unknown local negative annotation")
        cases.append(
            {"query": query, "expected_names": [], "kind": "negative", "negative_label": row["kind"]}
        )
    if not any(case["kind"] == "human_description" for case in cases):
        raise ValueError("no independent human queries match this corpus")
    if len({normalized(case["query"]) for case in cases}) != len(cases):
        raise ValueError("duplicate or conflicting query labels require explicit adjudication")
    return documents, cases, excluded, hashes


def manifest(path: Path, kind: str):
    raw = path.read_bytes()
    data = json.loads(raw)
    if data["kind"] != kind:
        raise ValueError("wrong model manifest kind")
    repo, weight = MODELS[kind]
    required = COMMON | {weight}
    if kind == "embedder":
        required |= {"colbert_linear.pt", "sparse_linear.pt"}
    if (
        data.get("repo") != repo
        or not re.fullmatch(r"[0-9a-f]{40}", data.get("revision", ""))
        or set(data["files"]) != required
    ):
        raise ValueError("manifest must pin the complete expected BGE snapshot")
    directory = Path(data["directory"]).resolve()
    for name, expected in data["files"].items():
        if Path(name).name != name:
            raise ValueError("manifest file names must be flat")
        target = directory / name
        if target.stat().st_size != expected["bytes"] or digest(target) != expected["sha256"]:
            raise ValueError(f"model artifact changed: {name}")
    return data, digest(path)


def cosine(left, right):
    if len(left) != len(right) or not left:
        raise ValueError("vector dimensions differ")
    if not all(math.isfinite(x) for x in [*left, *right]):
        raise ValueError("nonfinite vector")
    denominator = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right))
    if not denominator:
        raise ValueError("zero vector cannot rank a query")
    return sum(x * y for x, y in zip(left, right, strict=True)) / denominator


def order(scores, documents):
    if len(scores) != len(documents) or not all(math.isfinite(value) for value in scores):
        raise ValueError("rank scores must be finite and complete")
    return sorted(range(len(documents)), key=lambda i: (-scores[i], documents[i]["name"]))


def metrics(ranking, documents, expected):
    if not expected or not set(expected) <= {doc["name"] for doc in documents}:
        raise ValueError("positive targets must exist in this corpus")
    ranks = [i + 1 for i, doc in enumerate(ranking) if documents[doc]["name"] in expected]
    return {
        "recall_at_1": sum(rank <= 1 for rank in ranks) / len(expected),
        "recall_at_3": sum(rank <= 3 for rank in ranks) / len(expected),
        "recall_at_10": sum(rank <= 10 for rank in ranks) / len(expected),
        "reciprocal_rank": 1 / min(ranks) if ranks else 0.0,
    }


def summarize(cases):
    positives = [case for case in cases if case["expected_names"]]
    return {
        method: {
            key: statistics.mean(row[method][key] for row in positives)
            for key in ["recall_at_1", "recall_at_3", "recall_at_10", "reciprocal_rank"]
        }
        for method in ["exact_alias", "dense", "full_corpus_rerank", "dense_top10_rerank"]
    }


def configure(embedding, reranker, threads):
    from cyber_memoir.config import Settings, settings

    Settings.model_config["env_file"] = None
    os.environ.update(
        {
            "EMBEDDING_BACKEND": "local",
            "EMBEDDING_MODEL": embedding["directory"],
            "RERANKER_BACKEND": "local",
            "RERANKER_MODEL": reranker["directory"],
            "EMBEDDING_DEVICE": "cpu",
            "RERANKER_DEVICE": "cpu",
            "EMBEDDING_THREADS": str(threads),
            "RERANKER_THREADS": str(threads),
            # Offline capacity probe intentionally observes six serial computes,
            # unlike the production HTTP admission policy tested separately.
            "INFERENCE_QUEUE_TIMEOUT_SECONDS": "60",
            "LLM_BASE_URL": "",
            "LLM_API_KEY": "",
            "LLM_MODEL": "",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
    settings.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=ROOT / "evals/curation")
    parser.add_argument("--embedding-manifest", type=Path, required=True)
    parser.add_argument("--reranker-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--floor", type=float, default=0.35)
    args = parser.parse_args()
    if (
        args.out.exists()
        or args.out.suffix != ".json"
        or args.threads < 1
        or not math.isfinite(args.floor)
        or not 0 <= args.floor <= 1
    ):
        parser.error("use a new .json output, positive threads and finite floor in [0,1]")
    documents, rows, excluded, hashes = inputs(args.corpus)
    embedding, ehash = manifest(args.embedding_manifest, "embedder")
    reranker, rhash = manifest(args.reranker_manifest, "reranker")
    configure(embedding, reranker, args.threads)
    from cyber_memoir.adapters import inference

    code_paths = [
        Path(__file__),
        ROOT / "evals/model_assets.py",
        ROOT / "apps/backend/src/cyber_memoir/adapters/inference.py",
        ROOT / "apps/backend/src/cyber_memoir/config.py",
        ROOT / "apps/backend/uv.lock",
    ]
    code = {str(path.relative_to(ROOT)): digest(path) for path in code_paths}
    start = time.perf_counter()
    vectors = inference.embed([doc["text"] for doc in documents])
    corpus_seconds = time.perf_counter() - start
    start = time.perf_counter()
    queries = inference.embed([row["query"] for row in rows])
    query_seconds = time.perf_counter() - start
    results = []
    for position, (row, query_vector) in enumerate(zip(rows, queries, strict=True)):
        dense = order([cosine(query_vector, vector) for vector in vectors], documents)
        start = time.perf_counter()
        scores = inference.rerank(row["query"], [doc["text"] for doc in documents])
        score_seconds = time.perf_counter() - start
        start = time.perf_counter()
        repeated = inference.rerank(row["query"], [doc["text"] for doc in documents])
        cache_seconds = time.perf_counter() - start
        if scores != repeated:
            raise ValueError("identical repeated scores changed")
        ranked = order(scores, documents)
        candidates = set(dense[:10])
        limited = [i for i in ranked if i in candidates]
        exact = [
            i
            for i, doc in enumerate(documents)
            if normalized(row["query"]) in {normalized(v) for v in [doc["name"], *doc["aliases"]]}
        ]
        mentions = [
            v
            for doc in documents
            for v in [doc["name"], *doc["aliases"]]
            if normalized(v) and normalized(v) in normalized(row["query"])
        ]
        result = {
            **row,
            "surface_mentions": sorted(set(mentions)),
            "ranking": [{"name": documents[i]["name"], "score": scores[i]} for i in ranked],
            "score_seconds": score_seconds,
            "score_cache_seconds": cache_seconds,
            "cold_reranker": position == 0,
            "dense_ranking": [documents[i]["name"] for i in dense],
            "dense_top10_rerank_ranking": [documents[i]["name"] for i in limited],
        }
        if row["expected_names"]:
            for key, ranking in [
                ("exact_alias", exact),
                ("dense", dense),
                ("full_corpus_rerank", ranked),
                ("dense_top10_rerank", limited),
            ]:
                result[key] = metrics(ranking, documents, row["expected_names"])
            result["expected_passes_experimental_floor"] = any(
                scores[i] >= args.floor
                for i, doc in enumerate(documents)
                if doc["name"] in row["expected_names"]
            )
        else:
            result["any_document_passes_experimental_floor"] = max(scores) >= args.floor
        results.append(result)
        print(
            f"case {position + 1}/{len(rows)} {row['kind']} {score_seconds:.3f}s", file=sys.stderr, flush=True
        )
    valid = hashes == {path.name: digest(path) for path in args.corpus.glob("*.yaml")} and code == {
        str(path.relative_to(ROOT)): digest(path) for path in code_paths
    }
    valid &= (
        manifest(args.embedding_manifest, "embedder")[1] == ehash
        and manifest(args.reranker_manifest, "reranker")[1] == rhash
    )
    report = {
        "schema_version": 1,
        "scope": "offline_definition_probe",
        "status": "complete" if valid else "invalid",
        "not_measured": [
            "public archive eligibility",
            "chunk/BM25/graph fusion",
            "factual citation support",
            "RAG abstention",
            "production latency",
            "held-out generalization",
        ],
        "corpus_provenance": "local resolved curation markers, not proof of publication or factual approval",
        "query_provenance": "independent _descriptions.yaml labels; author chronology and held-out isolation not proven",
        "documents": documents,
        "excluded_human_queries": excluded,
        "input_sha256": hashes,
        "code_sha256": code,
        "models": {"embedding": embedding, "reranker": reranker},
        "runtime": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "device": "cpu",
            "threads": args.threads,
            "inference_queue_timeout_seconds": 60,
            "versions": {
                package: importlib.metadata.version(package)
                for package in ["FlagEmbedding", "torch", "transformers", "numpy"]
            },
            "embedding_batch_size": 8,
            "embedding_max_length": 1024,
            "reranker_score_transform": "sigmoid, not empirical probability calibration",
        },
        "latency": {
            "corpus_embedding_cold_seconds": corpus_seconds,
            "query_batch_embedding_seconds": query_seconds,
            "reranker_cold_seconds": results[0]["score_seconds"],
            "reranker_warm_median_seconds": statistics.median(r["score_seconds"] for r in results[1:])
            if len(results) > 1
            else None,
            "cache_median_seconds": statistics.median(r["score_cache_seconds"] for r in results),
        },
        "experimental_floor": args.floor,
        "cases": results,
        "metrics": summarize(results) if valid else None,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as output:
        json.dump(report, output, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "documents": len(documents),
                "positive_queries": sum(bool(row["expected_names"]) for row in rows),
                "negative_queries": sum(not row["expected_names"] for row in rows),
                "metrics": report["metrics"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
