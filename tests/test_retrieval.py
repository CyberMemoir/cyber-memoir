import pytest
from sqlalchemy.orm import Session

from cyber_memoir.config import settings
from cyber_memoir.domain.models import Source
from cyber_memoir.search.indexing import index_meme
from cyber_memoir.search.retrieval import rrf


def test_rrf_uses_rank_not_incomparable_raw_scores():
    scores = rrf([(["a", "b", "a"], 1), (["b", "c"], 1)])
    assert scores["b"] > scores["a"] > scores["c"]
    assert scores["a"] == pytest.approx(1 / 61)


def test_exact_alias_works_before_async_index(client, prepared):
    item = prepared()
    response = client.post("/v1/search", json={"query": "合成测试梗别名"}).json()
    assert response["items"][0]["id"] == item["meme_id"]
    assert response["items"][0]["exact_match"]


def test_platform_filter_applies_to_exact_channel(client, prepared):
    prepared(platform="bilibili")
    result = client.post("/v1/search", json={"query": "合成测试梗", "platform": "douyin"}).json()
    assert not result["items"]


def test_date_filter_does_not_substitute_capture_time(client, prepared, env):
    item = prepared()
    assert client.post("/v1/search", json={"published_after": "2000-01-01T00:00:00Z"}).json()["total"] == 0
    from datetime import UTC, datetime

    with Session(env) as db:
        db.get(Source, item["source"]["id"]).platform_published_at = datetime(2020, 1, 1, tzinfo=UTC)
        db.commit()
    assert client.post("/v1/search", json={"published_after": "2000-01-01T00:00:00Z"}).json()["total"] == 1


def test_degradation_is_explicit_not_fake_vector_search(client, prepared, env):
    item = prepared()
    with Session(env) as db:
        index_meme(db, item["meme_id"])
        db.commit()
    data = client.post("/v1/search", json={"query": "合成测试梗"}).json()
    assert "vector_disabled" in data["degraded"]
    assert "vector" not in data["channels"]
    assert "reranker_disabled" in data["degraded"]


def test_untrusted_bm25_ids_cannot_expose_draft(client, prepared, monkeypatch, env):
    item = prepared(publish=False)
    settings().opensearch_url = "http://search.invalid"

    class FakeSearch:
        def search(self, **kwargs):
            return {"hits": {"hits": [{"_id": item["meme_id"]}]}}

    from cyber_memoir.search import retrieval

    monkeypatch.setattr(retrieval, "client", lambda: FakeSearch())
    result = client.post("/v1/search", json={"query": "合成测试梗"}).json()
    assert not result["items"]


def test_one_hop_graph_expansion_requires_reviewed_relation(client, prepared, auth, env):
    parent = prepared("合成父梗")
    child = prepared("合成子梗", publish=False)
    payload = {
        **child["payload"],
        "relations": [
            {
                "predicate": "derived_from",
                "target_type": "meme",
                "target_id": parent["meme_id"],
                "evidence_ids": [child["evidence"]["id"]],
            }
        ],
    }
    assert client.put(f"/v1/reviews/{child['revision']['id']}", json=payload, headers=auth).status_code == 200
    assert (
        client.post(
            f"/v1/reviews/{child['revision']['id']}/decision",
            json={
                "decision": "approve",
                "reason": "合成关系人工核查",
                "verified_evidence_ids": [child["evidence"]["id"]],
            },
            headers=auth,
        ).status_code
        == 200
    )
    with Session(env) as db:
        index_meme(db, parent["meme_id"])
        index_meme(db, child["meme_id"])
        db.commit()
    ids = {x["id"] for x in client.post("/v1/search", json={"query": "合成父梗"}).json()["items"]}
    assert ids == {parent["meme_id"], child["meme_id"]}


def test_no_evidence_no_answer(client):
    data = client.post("/v1/answers", json={"query": "不存在的梗起源"}).json()
    assert not data["claims"] and not data["citations"]
    assert "没有足够" in data["answer"]


def test_rag_citations_resolve_to_reviewed_evidence(client, prepared):
    item = prepared()
    data = client.post("/v1/answers", json={"query": "合成测试梗"}).json()
    assert data["citations"][0]["evidence_id"] == item["evidence"]["id"]
    assert data["claims"][0]["statement"] == item["payload"]["definition"]
    assert data["mode"] == "extractive"


def test_rag_rejects_hallucinated_claim_indices(client, prepared, monkeypatch):
    prepared()
    from cyber_memoir.rag import answer as rag

    monkeypatch.setattr(rag, "generate_json", lambda *args: {"claim_indices": [9999], "answer": "虚构首创者"})
    result = client.post("/v1/answers", json={"query": "合成测试梗"}).json()
    assert "虚构首创者" not in result["answer"]
    assert "llm_unavailable_or_invalid" in result["degraded"]


def test_mcp_lists_only_read_only_tools(client):
    headers = {"Accept": "application/json, text/event-stream"}
    response = client.post(
        "/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}, headers=headers
    )
    assert response.status_code == 200, response.text
    tools = response.json()["result"]["tools"]
    assert {x["name"] for x in tools} == {
        "search_memes",
        "get_meme",
        "get_evidence",
        "get_timeline",
        "get_relations",
        "answer_question",
    }
    assert all(x["annotations"]["readOnlyHint"] for x in tools)


def test_mcp_and_http_share_publication_boundary(client, prepared):
    prepared(publish=False)
    response = client.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "search_memes", "arguments": {"query": "合成测试梗"}},
        },
        headers={"Accept": "application/json, text/event-stream"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["result"]["structuredContent"]["total"] == 0
