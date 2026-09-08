import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from cyber_memoir.api.main import _limits, app
from cyber_memoir.config import settings
from cyber_memoir.db import session
from cyber_memoir.domain.models import Base


@pytest.fixture
def env(tmp_path, monkeypatch):
    for key, value in {
        "REVIEWER_TOKEN": "unit-test-reviewer",
        "SUBMITTER_TOKEN": "",
        "STORAGE_BACKEND": "local",
        "STORAGE_PATH": str(tmp_path / "artifacts"),
        "OPENSEARCH_URL": "",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "EMBEDDING_BACKEND": "disabled",
        "RERANKER_BACKEND": "disabled",
        "LLM_BASE_URL": "",
        "LLM_MODEL": "",
    }.items():
        monkeypatch.setenv(key, value)
    settings.cache_clear()
    _limits.clear()
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)

    def override():
        with Session(eng) as db:
            yield db

    app.dependency_overrides[session] = override
    from cyber_memoir.mcp import server
    from cyber_memoir.workers import main

    monkeypatch.setattr(server, "engine", lambda: eng)
    monkeypatch.setattr(main, "engine", lambda: eng)
    yield eng
    app.dependency_overrides.clear()
    eng.dispose()
    settings.cache_clear()


@pytest.fixture(scope="session")
def transport():
    with TestClient(app, base_url="http://localhost:8100", raise_server_exceptions=True) as client:
        yield client


@pytest.fixture
def client(env, transport):
    return transport


@pytest.fixture
def auth():
    return {"Authorization": "Bearer unit-test-reviewer"}


@pytest.fixture
def prepared(client, auth):
    def create(name="合成测试梗", platform="bilibili", publish=True, **extra):
        url = (
            "https://www.bilibili.com/video/BV1TEST00001"
            if platform == "bilibili"
            else "https://www.douyin.com/video/1234567890123456789"
        )
        response = client.post("/v1/submissions", json={"url": url, "title": "合成测试来源，非真实文化事实"})
        assert response.status_code == 202, response.text
        source = response.json()["source"]
        material = client.post(
            f"/v1/sources/{source['id']}/materials",
            json={
                "text": f"{name} 是仅用于软件测试的虚构表述。",
                "locator": {"note": "合成测试材料，不可引用为真实历史", "start_ms": 1000},
            },
        )
        assert material.status_code == 201, material.text
        evidence = material.json()
        statement = f"{name} 是仅用于软件测试的虚构表述。"
        payload = {
            "canonical_name": name,
            "aliases": [f"{name}别名"],
            "definition": statement,
            "claims": [{"key": "definition", "statement": statement, "evidence_ids": [evidence["id"]]}],
            **extra,
        }
        draft = client.post("/v1/reviews/drafts", json=payload, headers=auth)
        assert draft.status_code == 201, draft.text
        revision = draft.json()
        if publish:
            approved = client.post(
                f"/v1/reviews/{revision['id']}/decision",
                json={
                    "decision": "approve",
                    "reason": "仅用于自动化测试的人工核对模拟",
                    "verified_evidence_ids": [evidence["id"]],
                },
                headers=auth,
            )
            assert approved.status_code == 200, approved.text
        return {
            "source": source,
            "evidence": evidence,
            "revision": revision,
            "meme_id": revision["meme_id"],
            "payload": payload,
        }

    return create
