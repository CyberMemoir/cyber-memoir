"""Reference destinations must carry the claim's own revision, even for shared evidence."""

from review_requests import matching_revision

from cyber_memoir.domain.responses import AnswerOut
from cyber_memoir.rag import answer as rag


def test_answer_claims_keep_their_own_published_revision(client, auth, prepared, monkeypatch):
    first = prepared(name="合成共享材料甲")
    second = prepared(name="合成共享材料乙")
    # Two published memes intentionally share one source and one evidence record.
    payload = {
        **second["payload"],
        "claims": [
            {
                "key": "definition",
                "statement": second["payload"]["definition"],
                "evidence_ids": [first["evidence"]["id"]],
            }
        ],
    }
    revision = client.post(
        f"/v1/reviews/drafts?meme_id={second['meme_id']}", json=payload, headers=auth
    ).json()
    approved = client.post(
        f"/v1/reviews/{revision['id']}/decision",
        headers=matching_revision(client, auth, f"/v1/reviews/{revision['id']}/decision"),
        json={
            "decision": "approve",
            "reason": "合成引用绑定测试，非文化事实",
            "verified_evidence_ids": [first["evidence"]["id"]],
        },
    )
    assert approved.status_code == 200
    items = [client.get(f"/v1/memes/{x['meme_id']}").json() for x in (first, second)]
    monkeypatch.setattr(
        rag,
        "search",
        lambda *args: {
            "items": items,
            "channels": ["exact_alias"],
            "degraded": [],
            "scores_calibrated": False,
        },
    )
    response = client.post("/v1/answers", json={"query": "合成引用验证"})
    assert response.status_code == 200, response.text
    answer = AnswerOut.model_validate(response.json())
    assert {(c.meme_id, c.meme_revision) for c in answer.claims} == {
        (first["meme_id"], 1),
        (second["meme_id"], 2),
    }
    assert len(answer.citations) == 1
    assert {(ref.meme_id, ref.meme_revision) for ref in answer.citations[0].meme_references} == {
        (first["meme_id"], 1),
        (second["meme_id"], 2),
    }
    assert answer.citations[0].meme_revision == 1


def test_supported_origin_requires_support_not_just_counter_evidence(client, auth, prepared):
    item = prepared(name="合成起源判断梗", publish=False)
    payload = {
        **item["payload"],
        "origin_status": "supported",
        "claims": [
            *item["payload"]["claims"],
            {
                "key": "origin",
                "statement": "合成反对材料中提及的起源说法，不是真实历史。",
                "stance": "contradicts",
                "evidence_ids": [item["evidence"]["id"]],
            },
        ],
        "relations": [
            {
                "predicate": "claimed_origin",
                "target_type": "source",
                "target_id": item["source"]["id"],
                "evidence_ids": [item["evidence"]["id"]],
            }
        ],
    }
    client.put(
        f"/v1/reviews/{item['revision']['id']}",
        json=payload,
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision']['id']}"),
    )
    response = client.post(
        f"/v1/reviews/{item['revision']['id']}/decision",
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision']['id']}/decision"),
        json={
            "decision": "approve",
            "reason": "合成来源判断测试",
            "verified_evidence_ids": [item["evidence"]["id"]],
        },
    )
    assert response.status_code == 422
    assert "支持性" in response.json()["detail"]


def test_supported_origin_cannot_use_a_disputed_source_relation(client, auth, prepared):
    item = prepared(name="合成争议来源关联梗", publish=False)
    payload = {
        **item["payload"],
        "origin_status": "supported",
        "claims": [
            *item["payload"]["claims"],
            {
                "key": "origin",
                "statement": "合成来源断言，非文化事实。",
                "evidence_ids": [item["evidence"]["id"]],
            },
        ],
        "relations": [
            {
                "predicate": "claimed_origin",
                "target_type": "source",
                "target_id": item["source"]["id"],
                "assertion_status": "disputed",
                "evidence_ids": [item["evidence"]["id"]],
            }
        ],
    }
    client.put(
        f"/v1/reviews/{item['revision']['id']}",
        json=payload,
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision']['id']}"),
    )
    response = client.post(
        f"/v1/reviews/{item['revision']['id']}/decision",
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision']['id']}/decision"),
        json={
            "decision": "approve",
            "reason": "合成争议关系测试",
            "verified_evidence_ids": [item["evidence"]["id"]],
        },
    )
    assert response.status_code == 422
