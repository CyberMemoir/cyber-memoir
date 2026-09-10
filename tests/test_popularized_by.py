"""The work that made a meme spread is its own kind of link.

Curating 闹吃VS古振兴 produced two videos a reviewer called the source of its
popularity, both dated *after* derivatives already in the archive. Neither
claimed_origin nor derived_from says that: the meme did not come from them, and
they were not made from it. A timeline that cannot name its amplifier collapses
origin and popularity into one thing, which is the mistake the archive exists to
avoid.
"""

AUTH = {"Authorization": "Bearer unit-test-reviewer"}


def relation(evidence_id, target_id, predicate="popularized_by", target_type="source"):
    return {
        "predicate": predicate,
        "target_type": target_type,
        "target_id": target_id,
        "evidence_ids": [evidence_id],
    }


def revise_and_approve(client, made, relations, reason):
    revision = client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], "relations": relations},
        headers=AUTH,
        params={"meme_id": made["meme_id"]},
    )
    assert revision.status_code == 201, revision.text
    return client.post(
        f"/v1/reviews/{revision.json()['id']}/decision",
        json={
            "decision": "approve",
            "reason": reason,
            "verified_evidence_ids": [made["evidence"]["id"]],
        },
        headers=AUTH,
    )


def test_a_meme_can_name_the_work_that_spread_it(client, prepared):
    made = prepared(name="合成走红来源梗")
    source_id = made["source"]["id"]
    approved = revise_and_approve(
        client, made, [relation(made["evidence"]["id"], source_id)], "合成测试：记录走红来源"
    )
    assert approved.status_code == 200, approved.text

    published = client.get(f"/v1/memes/{made['meme_id']}").json()
    assert len(published["relations"]) == 1
    assert published["relations"][0]["predicate"] == "popularized_by"
    assert published["relations"][0]["to_source_id"] == source_id
    # Popularity is not origin: naming an amplifier must not imply the origin is settled.
    assert published["origin_status"] == "unknown"


def test_it_coexists_with_upstream_material(client, prepared):
    """A meme can draw on one work and be spread by another, as 闹吃VS古振兴 does."""
    made = prepared(name="合成素材与走红梗")
    evidence_id, source_id = made["evidence"]["id"], made["source"]["id"]
    approved = revise_and_approve(
        client,
        made,
        [
            relation(evidence_id, source_id, predicate="derived_from"),
            relation(evidence_id, source_id, predicate="popularized_by"),
        ],
        "合成测试：素材与走红来源并存",
    )
    assert approved.status_code == 200, approved.text
    predicates = {r["predicate"] for r in client.get(f"/v1/memes/{made['meme_id']}").json()["relations"]}
    assert predicates == {"derived_from", "popularized_by"}


def test_it_refuses_a_meme_target(client, prepared):
    """An amplifier is a work, not a meme; that is what derived_from is for."""
    made = prepared(name="合成走红端点梗")
    other = prepared(name="合成另一条梗")
    approved = revise_and_approve(
        client,
        made,
        [relation(made["evidence"]["id"], other["meme_id"], target_type="meme")],
        "合成测试：端点类型不匹配应被拒绝",
    )
    assert approved.status_code == 422, approved.text


def test_the_named_source_must_exist(client, prepared):
    made = prepared(name="合成走红缺失梗")
    approved = revise_and_approve(
        client, made, [relation(made["evidence"]["id"], "no-such-source")], "合成测试：来源不存在"
    )
    assert approved.status_code == 404, approved.text
