"""A meme can derive from material that is not itself a meme.

Upstream material is often a film, a clip, or an off-platform post that will never
be curated as its own entry. Restricting derived_from to meme targets left no way to
record it, so an archive could hold a meme's derivatives but not what it came from.
"""

AUTH = {"Authorization": "Bearer unit-test-reviewer"}


def relation(evidence_id, target_id, target_type="source", predicate="derived_from"):
    return {
        "predicate": predicate,
        "target_type": target_type,
        "target_id": target_id,
        "evidence_ids": [evidence_id],
    }


def revise(client, made, **extra):
    return client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], **extra},
        headers=AUTH,
        params={"meme_id": made["meme_id"]},
    )


def approve(client, revision_id, evidence_id, reason):
    return client.post(
        f"/v1/reviews/{revision_id}/decision",
        json={"decision": "approve", "reason": reason, "verified_evidence_ids": [evidence_id]},
        headers=AUTH,
    )


def test_meme_derives_from_upstream_source(client, prepared):
    made = prepared(name="合成上游素材梗")
    evidence_id, source_id = made["evidence"]["id"], made["source"]["id"]
    revision = revise(client, made, relations=[relation(evidence_id, source_id)])
    assert revision.status_code == 201, revision.text
    approved = approve(client, revision.json()["id"], evidence_id, "合成测试：记录上游素材")
    assert approved.status_code == 200, approved.text

    published = client.get(f"/v1/memes/{made['meme_id']}").json()
    assert len(published["relations"]) == 1
    assert published["relations"][0]["predicate"] == "derived_from"
    assert published["relations"][0]["to_source_id"] == source_id
    assert published["relations"][0]["to_meme_id"] is None


def test_variant_of_still_refuses_a_source(client, prepared):
    """Only derived_from was widened; a variant is a variant of another meme."""
    made = prepared(name="合成变体端点梗")
    evidence_id = made["evidence"]["id"]
    revision = revise(
        client,
        made,
        relations=[relation(evidence_id, made["source"]["id"], predicate="variant_of")],
    )
    assert revision.status_code == 201, revision.text
    approved = approve(client, revision.json()["id"], evidence_id, "合成测试：端点类型不匹配应被拒绝")
    assert approved.status_code == 422, approved.text


def test_derived_from_source_must_exist(client, prepared):
    made = prepared(name="合成上游缺失梗")
    evidence_id = made["evidence"]["id"]
    revision = revise(client, made, relations=[relation(evidence_id, "no-such-source")])
    approved = approve(client, revision.json()["id"], evidence_id, "合成测试：上游来源不存在")
    assert approved.status_code == 404, approved.text
