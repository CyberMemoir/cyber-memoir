"""A source carries an authority tier, judged by a reviewer.

Evidence.kind says how text was extracted (asr/ocr/subtitle); it says nothing about
whether the source is a primary record or someone's unsourced explainer. Without this
an OCR'd commentary and an OCR'd original are indistinguishable in the archive.
"""

AUTH = {"Authorization": "Bearer unit-test-reviewer"}


def test_reviewer_sets_tier_and_it_is_published(client, prepared):
    made = prepared(name="合成分级梗")
    source_id = made["source"]["id"]
    assert client.get(f"/v1/sources/{source_id}").json()["source_tier"] is None

    response = client.post(
        f"/v1/reviews/sources/{source_id}/tier",
        json={"tier": "C", "reason": "合成测试：第三方讲解视频，非原始记录"},
        headers=AUTH,
    )
    assert response.status_code == 200, response.text
    assert response.json()["source_tier"] == "C"

    detail = client.get(f"/v1/sources/{source_id}").json()
    assert detail["source_tier"] == "C"
    assert detail["source_tier_reason"] == "合成测试：第三方讲解视频，非原始记录"


def test_tier_requires_reviewer_token(client, prepared):
    source_id = prepared(name="合成分级鉴权梗")["source"]["id"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/tier",
        json={"tier": "A", "reason": "合成测试：未授权不应生效"},
    )
    assert response.status_code == 401, response.text
    assert client.get(f"/v1/sources/{source_id}").json()["source_tier"] is None


def test_tier_outside_rubric_rejected(client, prepared):
    source_id = prepared(name="合成分级越界梗")["source"]["id"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/tier",
        json={"tier": "S", "reason": "合成测试：等级只有 A-D"},
        headers=AUTH,
    )
    assert response.status_code == 422, response.text


def test_tier_requires_a_reason(client, prepared):
    source_id = prepared(name="合成分级无理由梗")["source"]["id"]
    response = client.post(
        f"/v1/reviews/sources/{source_id}/tier",
        json={"tier": "D"},
        headers=AUTH,
    )
    assert response.status_code == 422, response.text
