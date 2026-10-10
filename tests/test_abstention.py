"""Navigation candidates are not evidence claims and cannot weaken the score floor."""

import copy

import pytest
from sqlalchemy.orm import Session

from cyber_memoir.domain.models import Meme
from cyber_memoir.rag import answer as rag


def result(items, degraded=None):
    return {
        "items": items,
        "degraded": degraded or [],
        "channels": ["synthetic-test"],
        "scores_calibrated": True,
    }


def candidate(client, item, score=0.1):
    row = client.get(f"/v1/memes/{item['meme_id']}").json()
    return {**row, "exact_match": False, "retrieval_score": score}


def test_low_relevance_is_not_absent_evidence_and_only_offers_navigation(client, prepared, monkeypatch):
    item = prepared(name="合成相关性候选")
    data = result([candidate(client, item)])
    monkeypatch.setattr(rag, "search", lambda *args: copy.deepcopy(data))
    answer = client.post("/v1/answers", json={"query": "合成模糊描述"}).json()
    assert answer["abstention_reason"] == "low_relevance"
    assert answer["claims"] == [] and answer["citations"] == []
    assert "相关性评分不足" in answer["answer"]
    assert answer["related_memories"] == [
        {"id": item["meme_id"], "canonical_name": "合成相关性候选", "published_revision": 1}
    ]
    assert "definition" not in answer["related_memories"][0]


def test_no_public_matches_does_not_invent_candidates(client, monkeypatch):
    monkeypatch.setattr(rag, "search", lambda *args: result([]))
    answer = client.post("/v1/answers", json={"query": "未收录的合成查询"}).json()
    assert answer["abstention_reason"] == "no_public_matches"
    assert answer["related_memories"] == [] and answer["claims"] == []


def test_unselected_verified_claims_are_distinct_from_no_claims(client, prepared, monkeypatch):
    item = prepared(name="合成选择空结果")
    data = result([candidate(client, item, 0.9)])
    monkeypatch.setattr(rag, "search", lambda *args: copy.deepcopy(data))
    monkeypatch.setattr(rag, "generate_json", lambda *args: {"claim_indices": []})
    answer = client.post("/v1/answers", json={"query": "合成问题"}).json()
    assert answer["abstention_reason"] == "selection_empty"
    assert answer["claims"] == [] and answer["related_memories"]
    data["items"][0]["claims"] = []
    assert (
        client.post("/v1/answers", json={"query": "合成问题"}).json()["abstention_reason"]
        == "no_approved_claims"
    )


@pytest.mark.parametrize("change", ["revision", "retracted", "draft"])
def test_stale_or_private_candidates_never_become_navigation(client, prepared, monkeypatch, env, change):
    item = prepared(name="合成变化候选", publish=change != "draft")
    # The snapshot itself is synthetic; the final public read must independently
    # reject an injected draft or a record changed since retrieval.
    snapshot = (
        {
            "id": item["meme_id"],
            "canonical_name": "合成变化候选",
            "published_revision": 1,
            "claims": [],
            "evidence": [],
            "exact_match": False,
            "retrieval_score": 0.1,
        }
        if change == "draft"
        else candidate(client, item)
    )
    if change != "draft":
        with Session(env) as db:
            row = db.get(Meme, item["meme_id"])
            if change == "revision":
                row.published_revision += 1
            else:
                row.status = "retracted"
            db.commit()
    monkeypatch.setattr(rag, "search", lambda *args: result([snapshot]))
    answer = client.post("/v1/answers", json={"query": "合成旧快照查询"}).json()
    assert answer["abstention_reason"] == "corpus_changed"
    assert answer["related_memories"] == []
    assert "corpus_changed_during_search" in answer["degraded"]


def test_existing_corpus_change_is_not_a_missing_source_prompt(client, monkeypatch):
    monkeypatch.setattr(rag, "search", lambda *args: result([], ["corpus_changed_during_search"]))
    answer = client.post("/v1/answers", json={"query": "合成变化查询"}).json()
    assert answer["abstention_reason"] == "corpus_changed"
    assert "刷新" in answer["answer"] and "提交" not in answer["answer"]


def test_successful_answer_does_not_add_uncertain_navigation(client, prepared, monkeypatch):
    item = prepared(name="合成成功回答")
    monkeypatch.setattr(rag, "search", lambda *args: result([candidate(client, item, 0.9)]))
    answer = client.post("/v1/answers", json={"query": "合成成功问题"}).json()
    assert answer["claims"] and answer["abstention_reason"] is None
    assert answer["related_memories"] == []
