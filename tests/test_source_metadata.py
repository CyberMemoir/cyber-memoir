"""A reviewer can record platform facts the platform will no longer serve.

Refreshing is the right path while a source is still fetchable. This exists for the ones
that are gone: a deleted video keeps whatever was observed while it still existed, and an
archive of vanishing culture is exactly where that case arises.
"""

from datetime import datetime, timedelta, timezone

AUTH = {"Authorization": "Bearer unit-test-reviewer"}


def test_reviewer_records_metadata_for_an_unfetchable_source(client, prepared):
    source_id = prepared(name="合成失效来源梗")["source"]["id"]
    before = client.get(f"/v1/sources/{source_id}").json()
    assert before["platform_published_at"] is None

    response = client.post(
        f"/v1/reviews/sources/{source_id}/metadata",
        json={
            "title": "合成测试：已下架视频的存档标题",
            "platform_published_at": "2026-08-11T00:00:00+08:00",
            "reason": "合成测试：来源已下架，日期取自下架前的观察记录",
        },
        headers=AUTH,
    )
    assert response.status_code == 200, response.text

    after = client.get(f"/v1/sources/{source_id}").json()
    assert after["title"] == "合成测试：已下架视频的存档标题"
    # SQLite keeps the wall time and drops the zone; PostgreSQL normalises to UTC. Compare
    # the instant rather than the spelling, so this asserts behaviour and not the driver.
    stored = datetime.fromisoformat(after["platform_published_at"])
    expected = datetime(2026, 8, 11, tzinfo=timezone(timedelta(hours=8)))
    if stored.tzinfo is None:
        stored = stored.replace(tzinfo=expected.tzinfo)
    assert stored == expected
    # The note keeps the provenance visible rather than passing a hand-typed date off as fetched.
    assert after["metadata_note"] == "合成测试：来源已下架，日期取自下架前的观察记录"


def test_partial_update_leaves_the_other_field_alone(client, prepared):
    source_id = prepared(name="合成部分更新梗")["source"]["id"]
    original = client.get(f"/v1/sources/{source_id}").json()["title"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/metadata",
        json={"platform_published_at": "2026-01-02T00:00:00+08:00", "reason": "合成测试：只补日期"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert client.get(f"/v1/sources/{source_id}").json()["title"] == original


def test_empty_update_is_refused(client, prepared):
    source_id = prepared(name="合成空更新梗")["source"]["id"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/metadata",
        json={"reason": "合成测试：没有提供任何字段"},
        headers=AUTH,
    )
    assert response.status_code == 422, response.text


def test_naive_datetime_is_refused(client, prepared):
    """Same rule as events: a timestamp without a zone is not a fact."""
    source_id = prepared(name="合成无时区梗")["source"]["id"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/metadata",
        json={"platform_published_at": "2026-08-11T00:00:00", "reason": "合成测试：缺时区"},
        headers=AUTH,
    )
    assert response.status_code == 422, response.text


def test_metadata_requires_reviewer_token(client, prepared):
    source_id = prepared(name="合成元数据鉴权梗")["source"]["id"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/metadata",
        json={"title": "未授权", "reason": "合成测试：未授权不应生效"},
    )
    assert response.status_code == 401, response.text
