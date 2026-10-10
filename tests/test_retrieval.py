import pytest
from sqlalchemy.orm import Session

from cyber_memoir.config import settings
from cyber_memoir.domain.models import Source
from cyber_memoir.search.indexing import index_meme
from cyber_memoir.search.retrieval import rrf


def test_search_and_answer_reuse_scores_but_retraction_is_immediate(client, prepared, monkeypatch, env):
    from test_rerank_concurrency import Recorder

    from cyber_memoir.adapters import inference

    item = prepared(name="合成复用测试")
    with Session(env) as db:
        index_meme(db, item["meme_id"])
        db.commit()
    recorder = Recorder()
    inference._SCORES.clear()
    monkeypatch.setattr(inference, "reranker", lambda: recorder)
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    settings.cache_clear()
    body = {"query": "合成复用测试"}
    assert client.post("/v1/search", json=body).json()["items"]
    assert client.post("/v1/answers", json=body).json()["claims"]
    assert recorder.calls == 1
    response = client.post(
        f"/v1/reviews/memes/{item['meme_id']}/retract",
        headers={"Authorization": "Bearer unit-test-reviewer"},
        json={"reason": "合成测试撤回"},
    )
    assert response.status_code == 200
    assert not client.post("/v1/answers", json=body).json()["claims"]


def test_revision_changed_during_rerank_is_not_scored_as_the_old_revision(client, prepared, monkeypatch, env):
    from cyber_memoir.domain.models import EvidenceLink, Meme
    from cyber_memoir.search import retrieval

    item = prepared(name="合成评分中修订测试")
    with Session(env) as db:
        index_meme(db, item["meme_id"])
        db.commit()

    def revise_while_scoring(query, texts):
        with Session(env) as other:
            meme = other.get(Meme, item["meme_id"])
            meme.published_revision = 2
            meme.definition = "合成新修订，不能复用旧修订的相关性评分。"
            other.add(
                EvidenceLink(
                    meme_id=meme.id,
                    revision=2,
                    evidence_id=item["evidence"]["id"],
                    claim_key="definition",
                    statement=meme.definition,
                    stance="supports",
                )
            )
            other.commit()
        return [0.9] * len(texts)

    monkeypatch.setattr(retrieval, "rerank", revise_while_scoring)
    response = client.post("/v1/search", json={"query": "合成评分中修订测试"})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["items"] == []
    assert "corpus_changed_during_search" in data["degraded"]
    fresh = client.get(f"/v1/memes/{item['meme_id']}").json()
    assert fresh["published_revision"] == 2


def test_public_detail_refreshes_a_preloaded_orm_record(prepared, env):
    from cyber_memoir.application.content import detail
    from cyber_memoir.domain.models import EvidenceLink, Meme

    item = prepared(name="合成会话缓存测试")
    with Session(env) as reader:
        cached = reader.get(Meme, item["meme_id"])
        assert cached.published_revision == 1
        with Session(env) as writer:
            current = writer.get(Meme, item["meme_id"])
            current.published_revision = 2
            current.definition = "合成最新定义，不允许使用旧会话实体。"
            writer.add(
                EvidenceLink(
                    meme_id=current.id,
                    revision=2,
                    evidence_id=item["evidence"]["id"],
                    claim_key="definition",
                    statement=current.definition,
                    stance="supports",
                )
            )
            writer.commit()
        result = detail(reader, item["meme_id"])
        assert result["published_revision"] == 2
        assert result["definition"] == "合成最新定义，不允许使用旧会话实体。"


@pytest.mark.parametrize("url", [False, True])
def test_video_identity_search_preserves_case(client, prepared, env, url):
    upper = prepared(name="大小写视频甲")
    lower = prepared(name="大小写视频乙")
    with Session(env) as db:
        # The fixture initially shares a source; separate the second record's evidence.
        from cyber_memoir.domain.models import Evidence

        source = Source(
            platform="bilibili",
            platform_item_id="BV1test00001",
            canonical_url="https://www.bilibili.com/video/BV1test00001",
            submitted_url="https://www.bilibili.com/video/BV1test00001",
        )
        db.add(source)
        db.flush()
        db.get(Evidence, lower["evidence"]["id"]).source_id = source.id
        db.commit()
    for item, bvid in ((upper, "BV1TEST00001"), (lower, "BV1test00001")):
        query = f"https://www.bilibili.com/video/{bvid}" if url else bvid
        data = client.post("/v1/search", json={"query": query}).json()
        assert [m["id"] for m in data["items"] if m["exact_match"]] == [item["meme_id"]]


def test_chuchu_question_reports_missing_origin_evidence(client, prepared, monkeypatch):
    item = prepared()
    from cyber_memoir.rag import answer as rag

    monkeypatch.setattr(
        rag,
        "search",
        lambda *args: {
            "items": [client.get(f"/v1/memes/{item['meme_id']}").json()],
            "degraded": [],
            "channels": ["exact_alias"],
            "scores_calibrated": False,
        },
    )
    data = client.post("/v1/answers", json={"query": "这个梗的出处是什么"}).json()
    assert any("不足以认定该梗的起源" in text for text in data["uncertainties"])


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


def _reranker(monkeypatch, score: float):
    from cyber_memoir.search import retrieval

    monkeypatch.setattr(retrieval, "rerank", lambda query, texts: [score] * len(texts))


def _indexed(prepared, env):
    """Publish and project into chunks; the score floor only applies to retrieved chunks."""
    item = prepared()
    with Session(env) as db:
        index_meme(db, item["meme_id"])
        db.commit()
    return item


def test_search_reports_scores_without_filtering_them(client, prepared, monkeypatch, env):
    _indexed(prepared, env)
    _reranker(monkeypatch, 0.01)
    result = client.post("/v1/search", json={"query": "仅用于软件测试的虚构表述"}).json()
    assert result["scores_calibrated"]
    # Searching is a presentation job: a weak hit is still shown, with its score attached.
    assert result["items"][0]["retrieval_score"] == pytest.approx(0.01)
    assert result["items"][0]["matches"][0]["score"] == pytest.approx(0.01)


def test_answer_abstains_below_the_score_floor(client, prepared, monkeypatch, env):
    _indexed(prepared, env)
    _reranker(monkeypatch, 0.01)
    data = client.post("/v1/answers", json={"query": "仅用于软件测试的虚构表述"}).json()
    assert data["claims"] == []
    assert "没有足够的已审核证据" in data["answer"]


def test_answer_uses_claims_above_the_score_floor(client, prepared, monkeypatch, env):
    _indexed(prepared, env)
    _reranker(monkeypatch, 0.9)
    data = client.post("/v1/answers", json={"query": "仅用于软件测试的虚构表述"}).json()
    assert data["claims"]


def test_exact_alias_is_identity_not_relevance_so_the_floor_does_not_apply(
    client, prepared, monkeypatch, env
):
    _indexed(prepared, env)
    _reranker(monkeypatch, 0.01)
    data = client.post("/v1/answers", json={"query": "合成测试梗别名"}).json()
    assert data["claims"]


def test_missing_calibrated_scorer_is_declared_not_silently_skipped(client, prepared, env):
    _indexed(prepared, env)
    data = client.post("/v1/answers", json={"query": "仅用于软件测试的虚构表述"}).json()
    # No reranker means nothing to threshold. The run says so instead of pretending it was checked.
    assert "score_floor_unenforced" in data["degraded"]
    assert data["claims"]


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
