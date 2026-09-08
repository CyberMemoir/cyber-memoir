"""Opt-in real PostgreSQL/pgvector + OpenSearch + Redis + S3 integration.

Uses an isolated schema, index and bucket, deleted after the test. Embedding values
are synthetic: this verifies the vector storage/query path, NOT BGE model quality.
"""

import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.api.main import app
from cyber_memoir.config import settings
from cyber_memoir.db import session
from cyber_memoir.domain.models import Base, Chunk, Job
from cyber_memoir.ingestion import pipeline
from cyber_memoir.mcp import server
from cyber_memoir.search import indexing, retrieval
from cyber_memoir.workers import main as worker

pytestmark = pytest.mark.skipif(os.environ.get("MEMOIR_INTEGRATION") != "1", reason="opt-in real services")


def test_real_stack_publication_indexing_vector_and_retraction(transport, monkeypatch):
    settings.cache_clear()
    cfg = settings()
    identifier = "test_" + uuid4().hex
    monkeypatch.setattr(cfg, "search_index", identifier)
    monkeypatch.setattr(cfg, "s3_bucket", identifier.replace("_", "-"))
    monkeypatch.setattr(cfg, "storage_backend", "s3")
    monkeypatch.setattr(cfg, "embedding_backend", "local")
    monkeypatch.setattr(cfg, "reviewer_token", "live-test-reviewer")
    monkeypatch.setattr(cfg, "submitter_token", "")
    monkeypatch.setattr(cfg, "llm_base_url", "")
    admin = create_engine(cfg.database_url)
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{identifier}"'))
    eng = create_engine(
        cfg.database_url, connect_args={"options": f"-csearch_path={identifier},public"}
    ).execution_options(schema_translate_map={None: identifier})
    Base.metadata.create_all(eng)

    def override():
        with Session(eng) as db:
            yield db

    app.dependency_overrides[session] = override
    monkeypatch.setattr(server, "engine", lambda: eng)
    monkeypatch.setattr(worker, "engine", lambda: eng)
    monkeypatch.setattr(pipeline, "metadata", lambda url: {"title": "合成集成测试来源"})
    vector = [1.0] + [0.0] * 1023
    monkeypatch.setattr(indexing, "embed", lambda texts: [vector for _ in texts])
    monkeypatch.setattr(retrieval, "embed", lambda texts: [vector for _ in texts])
    auth = {"Authorization": "Bearer live-test-reviewer"}
    client = transport
    try:
        source = client.post(
            "/v1/submissions", json={"url": "https://www.bilibili.com/video/BV1TEST00001"}
        ).json()["source"]
        assert worker.run_once()
        response = client.post(
            f"/v1/sources/{source['id']}/materials",
            json={"text": "合成集成测试梗仅用于自动化验收。", "locator": {"note": "synthetic fixture"}},
        )
        assert response.status_code == 201, response.text
        evidence = response.json()
        assert storage.get(evidence["artifact_key"])
        draft = client.post(
            "/v1/reviews/drafts",
            json={
                "canonical_name": "合成集成测试梗",
                "definition": "合成集成测试梗仅用于自动化验收。",
                "claims": [
                    {
                        "key": "definition",
                        "statement": "合成集成测试梗仅用于自动化验收。",
                        "evidence_ids": [evidence["id"]],
                    }
                ],
            },
            headers=auth,
        ).json()
        response = client.post(
            f"/v1/reviews/{draft['id']}/decision",
            json={
                "decision": "approve",
                "reason": "合成数据集成测试",
                "verified_evidence_ids": [evidence["id"]],
            },
            headers=auth,
        )
        assert response.status_code == 200, response.text
        for _ in range(10):
            if not worker.run_once():
                break
        with Session(eng) as db:
            job = db.scalar(select(Job).where(Job.kind == "index"))
            assert job.status == "succeeded", job.error
            assert db.scalar(select(Chunk)).embedding is not None
        result = client.post("/v1/search", json={"query": "合成集成测试梗"}).json()
        assert {"bm25", "vector"} <= set(result["channels"]), result
        assert result["items"][0]["id"] == draft["meme_id"]
        response = client.post(
            f"/v1/reviews/memes/{draft['meme_id']}/retract", json={"reason": "集成测试结束"}, headers=auth
        )
        assert response.status_code == 200, response.text
        result = client.post("/v1/search", json={"query": "合成集成测试梗"}).json()
        assert not result["items"]  # Before the asynchronous index deletion has run.
    finally:
        app.dependency_overrides.clear()
        indexing.client().indices.delete(index=identifier, ignore=[404])
        s3 = storage.client()
        try:
            objects = s3.list_objects_v2(Bucket=cfg.s3_bucket).get("Contents", [])
            for obj in objects:
                s3.delete_object(Bucket=cfg.s3_bucket, Key=obj["Key"])
            s3.delete_bucket(Bucket=cfg.s3_bucket)
        finally:
            eng.dispose()
            with admin.begin() as db:
                db.execute(text(f'DROP SCHEMA "{identifier}" CASCADE'))
            admin.dispose()
            settings.cache_clear()
