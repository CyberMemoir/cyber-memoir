"""An Event may name the Source it is about.

Timeline entries are discovered as "this dated video is a derivative of that meme".
Without a structured link the video's identity survived only as free text in the
description, so nothing could be clicked through, queried by uploader, or invalidated
when the referenced source was retracted.
"""


def event(evidence_id, to_source_id=None):
    body = {
        "event_type": "remix",
        "description": "合成测试：出现衍生作品",
        "occurred_at_start": "2026-08-21T00:00:00+08:00",
        "time_precision": "day",
        "time_basis": "平台显示的投稿时间",
        "evidence_ids": [evidence_id],
    }
    if to_source_id:
        body["to_source_id"] = to_source_id
    return body


def test_event_links_to_its_source(client, prepared):
    made = prepared(name="合成事件来源梗")
    source_id = made["source"]["id"]
    detail = client.get(f"/v1/memes/{made['meme_id']}").json()
    assert detail["events"] == []

    revision = client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], "events": [event(made["evidence"]["id"], source_id)]},
        headers={"Authorization": "Bearer unit-test-reviewer"},
        params={"meme_id": made["meme_id"]},
    )
    assert revision.status_code == 201, revision.text
    approved = client.post(
        f"/v1/reviews/{revision.json()['id']}/decision",
        json={
            "decision": "approve",
            "reason": "合成测试：核对事件与来源的关联",
            "verified_evidence_ids": [made["evidence"]["id"]],
        },
        headers={"Authorization": "Bearer unit-test-reviewer"},
    )
    assert approved.status_code == 200, approved.text

    published = client.get(f"/v1/memes/{made['meme_id']}").json()
    assert len(published["events"]) == 1
    assert published["events"][0]["to_source_id"] == source_id


def test_event_source_must_exist(client, prepared):
    made = prepared(name="合成缺失来源梗")
    revision = client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], "events": [event(made["evidence"]["id"], "no-such-source")]},
        headers={"Authorization": "Bearer unit-test-reviewer"},
        params={"meme_id": made["meme_id"]},
    )
    assert revision.status_code == 201, revision.text
    approved = client.post(
        f"/v1/reviews/{revision.json()['id']}/decision",
        json={
            "decision": "approve",
            "reason": "合成测试：事件指向不存在的来源应被拒绝",
            "verified_evidence_ids": [made["evidence"]["id"]],
        },
        headers={"Authorization": "Bearer unit-test-reviewer"},
    )
    assert approved.status_code == 404, approved.text


def test_event_without_source_still_allowed(client, prepared):
    """Plenty of dated observations have no single artefact behind them."""
    made = prepared(name="合成无来源事件梗")
    revision = client.post(
        "/v1/reviews/drafts",
        json={**made["payload"], "events": [event(made["evidence"]["id"])]},
        headers={"Authorization": "Bearer unit-test-reviewer"},
        params={"meme_id": made["meme_id"]},
    )
    approved = client.post(
        f"/v1/reviews/{revision.json()['id']}/decision",
        json={
            "decision": "approve",
            "reason": "合成测试：无来源事件仍可发布",
            "verified_evidence_ids": [made["evidence"]["id"]],
        },
        headers={"Authorization": "Bearer unit-test-reviewer"},
    )
    assert approved.status_code == 200, approved.text
    published = client.get(f"/v1/memes/{made['meme_id']}").json()
    assert published["events"][0]["to_source_id"] is None
