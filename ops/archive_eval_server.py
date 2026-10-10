"""Read-only evaluation API over an owned, separately restored PostgreSQL snapshot."""

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

import uvicorn

ROOT = Path(__file__).resolve().parents[1]


def owned_container(name, run_id, service_port, host_port):
    data = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
    if data["Config"]["Labels"].get("cyber-memoir-evaluation") != run_id:
        raise ValueError("refusing to use a container not owned by this evaluation")
    bindings = data["NetworkSettings"]["Ports"].get(f"{service_port}/tcp") or []
    if not data["State"]["Running"] or not any(
        row["HostIp"] == "127.0.0.1" and int(row["HostPort"]) == host_port for row in bindings
    ):
        raise ValueError("container does not own the configured loopback endpoint")
    return data["Image"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--search-url", required=True)
    parser.add_argument("--pg-container", required=True)
    parser.add_argument("--search-container", required=True)
    parser.add_argument("--mode", choices=["off", "rerank", "hybrid"], required=True)
    parser.add_argument("--index-only", action="store_true")
    parser.add_argument("--compare-cpu-rerank", action="store_true")
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    if args.compare_cpu_rerank and (args.mode == "off" or args.index_only):
        parser.error("paired CPU profiling requires an enabled reranker API")
    db_url, search_url = urlparse(args.database_url), urlparse(args.search_url)
    if (
        db_url.scheme != "postgresql+psycopg"
        or db_url.hostname not in {"127.0.0.1", "localhost"}
        or db_url.port == 55432
        or db_url.path != "/eval"
    ):
        parser.error("database must be the separate loopback /eval database, not business port 55432")
    if (
        search_url.scheme != "http"
        or search_url.hostname not in {"127.0.0.1", "localhost"}
        or search_url.port == 59200
    ):
        parser.error("search must use a separate loopback service, not business port 59200")
    images = {
        "postgres": owned_container(args.pg_container, args.run_id, 5432, db_url.port),
        "opensearch": owned_container(args.search_container, args.run_id, 9200, search_url.port),
    }
    snapshot = args.snapshot.resolve()
    captured = json.loads((snapshot / "manifest.json").read_text())
    if hashlib.sha256((snapshot / "postgres.dump").read_bytes()).hexdigest() != captured["dump_sha256"]:
        raise ValueError("database dump changed")
    sys.path.insert(0, str(ROOT / "evals"))
    from model_probe import manifest

    embedding, _ = manifest(ROOT / ".data/model-eval/embedder-manifest.json", "embedder")
    reranker, _ = manifest(ROOT / ".data/model-eval/reranker-manifest.json", "reranker")
    from cyber_memoir.config import Settings, settings

    Settings.model_config["env_file"] = None
    os.environ.update(
        {
            "DATABASE_URL": args.database_url,
            "OPENSEARCH_URL": args.search_url,
            "SEARCH_INDEX": f"archive-eval-{args.run_id}",
            "REDIS_URL": "redis://127.0.0.1:1/0",
            "STORAGE_BACKEND": "local",
            "STORAGE_PATH": str(snapshot / "objects"),
            "REVIEWER_TOKEN": secrets.token_urlsafe(32),
            "SUBMITTER_TOKEN": secrets.token_urlsafe(32),
            "EMBEDDING_BACKEND": "local" if args.mode == "hybrid" else "disabled",
            "RERANKER_BACKEND": "disabled" if args.mode == "off" else "local",
            "EMBEDDING_MODEL": embedding["directory"],
            "RERANKER_MODEL": reranker["directory"],
            "EMBEDDING_DEVICE": "cpu",
            "RERANKER_DEVICE": "cpu",
            "EMBEDDING_THREADS": "4",
            "RERANKER_THREADS": "4",
            "LLM_BASE_URL": "",
            "LLM_API_KEY": "",
            "LLM_MODEL": "",
            "AUTO_MEDIA": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
        }
    )
    settings.cache_clear()
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    from cyber_memoir.db import engine
    from cyber_memoir.domain.models import Meme, Revision
    from cyber_memoir.search.indexing import index_meme

    with Session(engine()) as db:
        records = list(db.scalars(select(Meme).where(Meme.status == "published")))
        public = json.loads((snapshot / "public.json").read_text())
        expected = {record["id"]: record["published_revision"] for record in public["records"]}
        if {row.id: row.published_revision for row in records} != expected:
            raise ValueError("restored publication identities differ from captured public snapshot")
        for row in records:
            approved = db.scalar(
                select(Revision).where(
                    Revision.meme_id == row.id,
                    Revision.status == "published",
                    Revision.based_on_revision == row.published_revision - 1,
                )
            )
            if (
                approved is None
                or not approved.reviewed_at
                or not approved.reviewer
                or not approved.review_reason
            ):
                raise ValueError("missing actual publication approval record")
        if args.index_only:
            for number, row in enumerate(records, 1):
                index_meme(db, row.id)
                db.commit()
                print(f"indexed {number}/{len(records)}", flush=True)
            return

    from fastapi.responses import JSONResponse

    from cyber_memoir.api.main import app

    if args.compare_cpu_rerank:
        from rerank_cpu_probe import attach

        from cyber_memoir.adapters.inference import reranker as load_reranker

        app.state.cpu_comparison = attach(load_reranker(), snapshot / "cpu-comparison.jsonl")

    @app.middleware("http")
    async def readonly_snapshot(request, call_next):
        allowed = (
            request.method in {"GET", "HEAD", "OPTIONS"}
            and (
                request.url.path.startswith(("/health/", "/v1/memes", "/v1/evidence/"))
                or request.url.path in {"/v1/stats", "/v1/universe"}
            )
            or request.method == "POST"
            and request.url.path in {"/v1/search", "/v1/answers"}
        )
        if not allowed or request.url.path.startswith("/v1/reviews"):
            return JSONResponse(
                status_code=405,
                content={"detail": "Frozen evaluation snapshot: no publication, edits, jobs or ingestion"},
            )
        response = await call_next(request)
        response.headers["X-Cyber-Memoir-Evaluation"] = args.run_id
        return response

    context = {
        "models": {
            "embedding": {
                "enabled": args.mode == "hybrid",
                "identifier": embedding["repo"] if args.mode == "hybrid" else "disabled",
                **(
                    {"sha256": embedding["files"]["pytorch_model.bin"]["sha256"]}
                    if args.mode == "hybrid"
                    else {}
                ),
            },
            "reranker": {
                "enabled": args.mode != "off",
                "identifier": reranker["repo"] if args.mode != "off" else "disabled",
                **(
                    {"sha256": reranker["files"]["model.safetensors"]["sha256"]} if args.mode != "off" else {}
                ),
            },
            "llm": {"enabled": False, "identifier": "disabled"},
        },
        "configuration": {
            "snapshot_dump_sha256": captured["dump_sha256"],
            "images": images,
            "mode": args.mode,
            "device": "cpu",
            "threads": 4,
            "floor": settings().answer_score_floor,
            "source": "restored approval records, no new approvals",
            "paired_cpu_profiling": args.compare_cpu_rerank,
            "reranker_implementation": "single-pass-cpu" if args.mode != "off" else "disabled",
            **(
                {
                    "comparison_probe_sha256": hashlib.sha256(
                        (ROOT / "evals/rerank_cpu_probe.py").read_bytes()
                    ).hexdigest()
                }
                if args.compare_cpu_rerank
                else {}
            ),
        },
    }
    (snapshot / f"context-{args.mode}.json").write_text(json.dumps(context, indent=2, sort_keys=True))
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
