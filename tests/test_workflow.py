from sqlalchemy import select
from sqlalchemy.orm import Session

from cyber_memoir.domain.models import Chunk, Evidence, Job, Meme, Revision
from cyber_memoir.search.indexing import index_meme


def test_health_and_empty_catalog(client):
    assert client.get("/health/ready").status_code == 200
    assert client.post("/v1/search", json={}).json()["total"] == 0


def test_url_deduplication(client):
    first = client.post(
        "/v1/submissions", json={"url": "https://www.bilibili.com/video/BV1TEST00001/?share_source=copy"}
    ).json()
    second = client.post(
        "/v1/submissions", json={"url": "https://www.bilibili.com/video/BV1TEST00001"}
    ).json()
    assert first["source"]["id"] == second["source"]["id"]
    assert second["duplicate"]
    assert first["job_id"] == second["job_id"]


def test_authentication_required(client):
    assert client.get("/v1/reviews").status_code == 401
    assert client.post("/v1/reviews/drafts", json={"canonical_name": "x"}).status_code == 401


def test_drafts_and_unverified_evidence_are_private(client, prepared):
    item = prepared(publish=False)
    assert client.get(f"/v1/memes/{item['meme_id']}").status_code == 404
    assert client.get(f"/v1/evidence/{item['evidence']['id']}").status_code == 404
    assert client.post("/v1/search", json={"query": "合成测试梗"}).json()["total"] == 0


def test_publication_and_evidence_download(client, prepared):
    item = prepared()
    detail = client.get(f"/v1/memes/{item['meme_id']}").json()
    assert detail["published_revision"] == 1
    assert detail["evidence"][0]["verified"]
    assert client.get(f"/v1/evidence/{item['evidence']['id']}/artifact").status_code == 200
    assert detail["origin_status"] == "unknown"


def test_definition_requires_complete_support(client, prepared, auth):
    item = prepared(publish=False)
    payload = {**item["payload"], "definition": "这句话没有证据支持"}
    assert client.put(f"/v1/reviews/{item['revision']['id']}", json=payload, headers=auth).status_code == 200
    response = client.post(
        f"/v1/reviews/{item['revision']['id']}/decision",
        json={"decision": "approve", "reason": "人工核查", "verified_evidence_ids": [item["evidence"]["id"]]},
        headers=auth,
    )
    assert response.status_code == 422


def test_review_requires_explicit_verification(client, prepared, auth):
    item = prepared(publish=False)
    response = client.post(
        f"/v1/reviews/{item['revision']['id']}/decision",
        json={"decision": "approve", "reason": "人工核查"},
        headers=auth,
    )
    assert response.status_code == 422


def test_origin_cannot_be_inferred_without_specific_evidence(client, prepared, auth):
    item = prepared(publish=False, origin_status="supported")
    response = client.post(
        f"/v1/reviews/{item['revision']['id']}/decision",
        json={
            "decision": "approve",
            "reason": "看起来最早",
            "verified_evidence_ids": [item["evidence"]["id"]],
        },
        headers=auth,
    )
    assert response.status_code == 422


def test_rejected_revision_is_not_published(client, prepared, auth):
    item = prepared(publish=False)
    path = f"/v1/reviews/{item['revision']['id']}/decision"
    assert (
        client.post(path, json={"decision": "reject", "reason": "证据不足"}, headers=auth).status_code == 200
    )
    assert (
        client.post(path, json={"decision": "reject", "reason": "证据不足"}, headers=auth).status_code == 409
    )
    assert client.get(f"/v1/memes/{item['meme_id']}").status_code == 404


def test_new_draft_does_not_overwrite_public_revision(client, prepared, auth):
    item = prepared()
    draft = client.post(
        f"/v1/reviews/drafts?meme_id={item['meme_id']}",
        json={**item["payload"], "canonical_name": "尚未审核的名称"},
        headers=auth,
    ).json()
    assert draft["based_on_revision"] == 1
    assert client.get(f"/v1/memes/{item['meme_id']}").json()["canonical_name"] == "合成测试梗"


def test_stale_revision_conflict(client, prepared, auth):
    item = prepared()
    path = f"/v1/reviews/drafts?meme_id={item['meme_id']}"
    a = client.post(path, json=item["payload"], headers=auth).json()
    b = client.post(path, json=item["payload"], headers=auth).json()
    decision = {"decision": "approve", "reason": "人工复核证据"}
    assert client.post(f"/v1/reviews/{a['id']}/decision", json=decision, headers=auth).status_code == 200
    assert client.post(f"/v1/reviews/{b['id']}/decision", json=decision, headers=auth).status_code == 409


def test_index_jobs_are_transactional_and_idempotent(client, prepared, env):
    item = prepared()
    with Session(env) as db:
        assert db.scalar(select(Job).where(Job.kind == "index"))
        index_meme(db, item["meme_id"])
        db.commit()
        first = list(db.scalars(select(Chunk.id)))
        index_meme(db, item["meme_id"])
        db.commit()
        assert first == list(db.scalars(select(Chunk.id)))


def test_retraction_immediately_blocks_stale_index(client, prepared, auth, env):
    item = prepared()
    with Session(env) as db:
        index_meme(db, item["meme_id"])
        db.commit()
    assert client.post("/v1/search", json={"query": "合成测试梗"}).json()["total"] == 1
    assert (
        client.post(
            f"/v1/reviews/memes/{item['meme_id']}/retract", json={"reason": "来源需要重新核查"}, headers=auth
        ).status_code
        == 200
    )
    assert client.post("/v1/search", json={"query": "合成测试梗"}).json()["total"] == 0
    assert client.get(f"/v1/evidence/{item['evidence']['id']}").status_code == 404


def test_evidence_retraction_invalidates_dependent_publication(client, prepared, auth):
    item = prepared()
    response = client.post(
        f"/v1/reviews/evidence/{item['evidence']['id']}/retract",
        json={"reason": "原文识别错误"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert item["meme_id"] in response.json()["retracted_memes"]
    assert client.get(f"/v1/memes/{item['meme_id']}").status_code == 404


def test_material_dedup_and_immutable_revision(client, prepared, env):
    item = prepared()
    old = item["evidence"]
    response = client.post(
        f"/v1/sources/{item['source']['id']}/materials", json={"text": old["text"], "locator": old["locator"]}
    )
    assert response.json()["id"] == old["id"]
    revised = client.post(
        f"/v1/sources/{item['source']['id']}/materials",
        json={"text": "修正后的合成文本", "locator": {"note": "重新核查"}, "supersedes_id": old["id"]},
    ).json()
    assert revised["id"] != old["id"]
    with Session(env) as db:
        assert db.get(Evidence, old["id"]).text == old["text"]


def test_merge_preserves_history_without_migrating_claims(client, prepared, auth, env):
    a = prepared("合成甲")
    b = prepared("合成乙")
    response = client.post(
        f"/v1/reviews/memes/{a['meme_id']}/merge",
        json={"target_id": b["meme_id"], "reason": "同一概念人工消歧"},
        headers=auth,
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/v1/memes/{a['meme_id']}").status_code == 409
    assert client.post("/v1/search", json={"query": "合成甲"}).json()["items"][0]["id"] == b["meme_id"]
    with Session(env) as db:
        assert db.get(Meme, a["meme_id"]).merged_into_id == b["meme_id"]
        assert len(list(db.scalars(select(Revision).where(Revision.meme_id == a["meme_id"])))) == 2
