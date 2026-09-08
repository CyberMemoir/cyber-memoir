"""Isolated browser-test backend. Synthetic fixtures only; never uses deployment data."""

import os
import tempfile
import threading
import time

import uvicorn

with tempfile.TemporaryDirectory(prefix="memoir-e2e-") as directory:
    os.environ.update(
        {
            "DATABASE_URL": f"sqlite:///{directory}/test.sqlite",
            "STORAGE_BACKEND": "local",
            "STORAGE_PATH": f"{directory}/objects",
            "REVIEWER_TOKEN": "e2e-reviewer-only",
            "SUBMITTER_TOKEN": "",
            "REDIS_URL": "redis://127.0.0.1:1/0",
            "OPENSEARCH_URL": "",
            "EMBEDDING_BACKEND": "disabled",
            "RERANKER_BACKEND": "disabled",
            "LLM_BASE_URL": "",
            "LLM_MODEL": "",
        }
    )
    from cyber_memoir.api.main import app
    from cyber_memoir.db import engine
    from cyber_memoir.domain.models import Base
    from cyber_memoir.ingestion import pipeline
    from cyber_memoir.workers.main import run_once

    Base.metadata.create_all(engine())

    def synthetic_metadata(url):
        if url != "https://www.bilibili.com/video/BV1TEST00001":
            raise ValueError("Browser tests accept only the synthetic fixture URL")
        return {"title": "合成浏览器验收来源", "description": "仅用于自动化测试，不是真实互联网文化证据。"}

    pipeline.metadata = synthetic_metadata
    stop = threading.Event()

    def worker():
        while not stop.is_set():
            try:
                run_once()
            except Exception:
                pass
            time.sleep(0.2)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=8101, log_level="warning")
    finally:
        stop.set()
        thread.join(timeout=5)
