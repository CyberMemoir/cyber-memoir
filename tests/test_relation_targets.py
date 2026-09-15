"""An edge names what it points at.

Relations and events used to carry only the far end's id. Rendered, 闹吃VS古振兴's
lineage was seven identical lines ending in a UUID, and placing any of it on a time
axis took one request per edge. Every reader of a timeline needs the label, the link
and the date, so the archive hands them over with the edge.
"""

AUTH = {"Authorization": "Bearer unit-test-reviewer"}


def revise(client, made, reason, **fields):
    revision = client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], **fields},
        headers=AUTH,
        params={"meme_id": made["meme_id"]},
    )
    assert revision.status_code == 201, revision.text
    approved = client.post(
        f"/v1/reviews/{revision.json()['id']}/decision",
        json={
            "decision": "approve",
            "reason": reason,
            "verified_evidence_ids": [made["evidence"]["id"]],
        },
        headers=AUTH,
    )
    assert approved.status_code == 200, approved.text


def test_a_source_target_is_named_linked_dated_and_tiered(client, prepared):
    made = prepared(name="合成来源端点梗")
    source_id = made["source"]["id"]
    tiered = client.post(
        f"/v1/reviews/sources/{source_id}/tier",
        json={"tier": "A", "reason": "合成测试：原帖即原始记录"},
        headers=AUTH,
    )
    assert tiered.status_code == 200, tiered.text
    revise(
        client,
        made,
        "合成测试：记录来源端点",
        relations=[
            {
                "predicate": "documented_in",
                "target_type": "source",
                "target_id": source_id,
                "evidence_ids": [made["evidence"]["id"]],
            }
        ],
    )

    target = client.get(f"/v1/memes/{made['meme_id']}").json()["relations"][0]["target"]
    assert target["type"] == "source" and target["id"] == source_id
    assert target["label"], (
        "a source edge must carry something readable, never only its id"
    )
    assert target["url"].startswith("https://www.bilibili.com/video/")
    assert target["tier"] == "A"
    assert "published_at" in target and "availability" in target


def test_an_event_names_the_work_it_is_about(client, prepared):
    made = prepared(name="合成事件端点梗")
    source_id = made["source"]["id"]
    revise(
        client,
        made,
        "合成测试：事件指向作品",
        events=[
            {
                "event_type": "remix",
                "description": "合成测试衍生作品",
                "occurred_at_start": "2026-08-20T00:00:00+08:00",
                "time_precision": "day",
                "time_basis": "合成测试",
                "to_source_id": source_id,
                "evidence_ids": [made["evidence"]["id"]],
            }
        ],
    )

    event = client.get(f"/v1/memes/{made['meme_id']}").json()["events"][0]
    assert event["target"]["type"] == "source"
    assert event["target"]["id"] == source_id
    assert event["target"]["url"]


def test_a_meme_target_stops_being_named_once_retracted(client, prepared):
    """Review checks a meme target is published, but not that it stays so.

    Thirty-two memes were retracted in one pass on 2026-09-13. A relation written
    before that must not keep a withdrawn meme's name readable through a live page.
    """
    parent = prepared(name="合成被引用梗")
    child = prepared(name="合成引用他梗")
    revise(
        client,
        child,
        "合成测试：梗衍生自梗",
        relations=[
            {
                "predicate": "derived_from",
                "target_type": "meme",
                "target_id": parent["meme_id"],
                "evidence_ids": [child["evidence"]["id"]],
            }
        ],
    )

    before = client.get(f"/v1/memes/{child['meme_id']}").json()["relations"][0][
        "target"
    ]
    assert before == {
        **before,
        "type": "meme",
        "label": "合成被引用梗",
        "availability": "published",
    }

    retracted = client.post(
        f"/v1/reviews/memes/{parent['meme_id']}/retract",
        json={"reason": "合成测试：撤回被引用的梗"},
        headers=AUTH,
    )
    assert retracted.status_code == 200, retracted.text

    after = client.get(f"/v1/memes/{child['meme_id']}").json()["relations"][0]["target"]
    assert after["availability"] == "withdrawn"
    assert after["label"] == ""
    assert after["id"] == parent["meme_id"]
