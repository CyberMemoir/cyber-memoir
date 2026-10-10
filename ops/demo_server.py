"""Disposable, loopback-only demo backend with all upstream/model access disabled."""

import argparse
import logging
import os
import signal
import tempfile
import threading
from pathlib import Path

import uvicorn
from demo_fixtures import DEMO_SUBMISSION_URL, DEMO_TOKEN, seed


def configure(directory):
    # Environment overrides plus disabling .env loading keep private deployment
    # settings out of this process, including optional credentials and cookies.
    from cyber_memoir.config import Settings, settings

    Settings.model_config["env_file"] = None
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite:///{Path(directory) / 'demo.sqlite'}",
            "STORAGE_BACKEND": "local",
            "STORAGE_PATH": str(Path(directory) / "objects"),
            "REVIEWER_TOKEN": DEMO_TOKEN,
            "SUBMITTER_TOKEN": "",
            "REDIS_URL": "redis://127.0.0.1:1/0",
            "OPENSEARCH_URL": "",
            "EMBEDDING_BACKEND": "disabled",
            "RERANKER_BACKEND": "disabled",
            "LLM_BASE_URL": "",
            "LLM_API_KEY": "",
            "LLM_MODEL": "",
            "S3_ENDPOINT": "",
            "S3_ACCESS_KEY": "",
            "S3_SECRET_KEY": "",
            "PLATFORM_COOKIES_FILE": "",
            "PLATFORM_FETCH_INTERVAL_SECONDS": "0",
            "AUTO_MEDIA": "false",
        }
    )
    settings.cache_clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8102)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")

    with tempfile.TemporaryDirectory(prefix="cyber-memoir-demo-") as directory:
        configure(directory)
        from fastapi import Request
        from fastapi.responses import JSONResponse
        from sqlalchemy.orm import Session

        from cyber_memoir.api.main import app
        from cyber_memoir.db import engine
        from cyber_memoir.domain.models import Base
        from cyber_memoir.ingestion import pipeline
        from cyber_memoir.workers import main as worker_module
        from cyber_memoir.workers.main import run_once

        Base.metadata.create_all(engine())
        with Session(engine()) as db:
            seed(db)

        def synthetic_metadata(url):
            if url != DEMO_SUBMISSION_URL:
                raise ValueError("本地演示不抓取平台；请使用文档中的合成链接或补充文本材料")
            return {
                "title": "合成演示：新提交的材料",
                "description": "本地生成的合成材料，非真实互联网文化证据；请人工编辑待审定义。",
            }

        pipeline.metadata = synthetic_metadata
        original_ingest = worker_module.ingest

        def synthetic_ingest(db, source_id):
            from sqlalchemy import select

            from cyber_memoir.domain.models import Evidence, Source

            original_ingest(db, source_id)
            source = db.get(Source, source_id)
            source.metadata_note = "合成演示：元数据由本地夹具生成，未请求真实平台。"
            for item in db.scalars(select(Evidence).where(Evidence.source_id == source_id)):
                if item.extraction_provenance.get("method") == "yt-dlp":
                    item.extraction_provenance = {
                        **item.extraction_provenance,
                        "method": "synthetic_demo",
                        "not_real_cultural_evidence": True,
                    }

        worker_module.ingest = synthetic_ingest

        @app.middleware("http")
        async def demo_boundary(request: Request, call_next):
            path = request.url.path.rstrip("/")
            if request.method == "POST" and path == "/v1/submissions":
                try:
                    body = await request.json()
                except ValueError:
                    return JSONResponse(status_code=422, content={"detail": "需要 JSON 合成提交"})
                if not isinstance(body, dict) or body.get("url") != DEMO_SUBMISSION_URL:
                    return JSONResponse(
                        status_code=422,
                        content={"detail": f"本地演示仅接受合成链接：{DEMO_SUBMISSION_URL}"},
                    )
            if request.method == "POST" and path.startswith("/v1/sources/") and path.endswith("/media"):
                return JSONResponse(status_code=422, content={"detail": "演示不运行媒体模型，请补充文本材料"})
            response = await call_next(request)
            response.headers["X-Cyber-Memoir-Demo"] = "synthetic-only"
            return response

        stop = threading.Event()

        def worker():
            while not stop.is_set():
                try:
                    run_once()
                except Exception:
                    logging.exception("demo_worker_failed")
                stop.wait(0.2)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="warning"))
        # Uvicorn re-raises captured signals after restoring prior handlers. A
        # terminating default SIGTERM would otherwise skip our outer cleanup.
        signal.signal(signal.SIGTERM, lambda *_: setattr(server, "should_exit", True))
        try:
            server.run()
        finally:
            stop.set()
            thread.join(timeout=5)
            engine().dispose()


if __name__ == "__main__":
    main()
