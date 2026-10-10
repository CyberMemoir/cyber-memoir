"""Synthetic review snapshots: stale editors cannot overwrite or approve another draft."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from cyber_memoir.application import content, revisions
from cyber_memoir.domain.models import Base, Meme, Revision
from cyber_memoir.domain.schemas import MemeDraft


def test_stale_draft_write_does_not_overwrite_another_editor(client, auth):
    draft = client.post("/v1/reviews/drafts", json={"canonical_name": "合成并行编辑稿"}, headers=auth).json()
    path = f"/v1/reviews/{draft['id']}"
    headers = {**auth, "If-Match": draft.get("etag", f'"review-{draft["id"]}-v1"')}
    first = client.put(path, json={"canonical_name": "合成编辑者甲的文字"}, headers=headers)
    assert first.status_code == 200, first.text
    second = client.put(path, json={"canonical_name": "合成编辑者乙的过期文字"}, headers=headers)
    assert second.status_code == 412, second.text
    latest = client.get(path, headers=auth)
    assert latest.json()["payload"]["canonical_name"] == "合成编辑者甲的文字"


def test_preconditions_are_required_for_edit_and_decision(client, auth):
    draft = client.post("/v1/reviews/drafts", json={"canonical_name": "合成条件写入稿"}, headers=auth).json()
    path = f"/v1/reviews/{draft['id']}"
    assert client.get(path).status_code == 401
    assert client.get(path + "/comparison").status_code == 401
    assert client.put(path, json=draft["payload"], headers=auth).status_code == 428
    assert (
        client.post(
            path + "/decision", json={"decision": "reject", "reason": "合成测试拒绝"}, headers=auth
        ).status_code
        == 428
    )
    for value in ["*", "W/" + draft["etag"], draft["etag"] + ", " + draft["etag"]]:
        assert client.put(path, json=draft["payload"], headers={**auth, "If-Match": value}).status_code == 400
    row = client.get(path, headers=auth)
    assert row.headers["etag"] == draft["etag"]
    assert row.json()["edit_version"] == 1


def test_decision_cannot_approve_a_different_saved_payload(client, prepared, auth):
    made = prepared(publish=False)
    path = f"/v1/reviews/{made['revision']['id']}"
    original = client.get(path, headers=auth).json()
    changed = {**original["payload"], "definition": "另一位审核者的合成新定义。", "claims": []}
    response = client.put(path, json=changed, headers={**auth, "If-Match": original["etag"]})
    assert response.status_code == 200
    assert response.json()["edit_version"] == 2
    attempted = client.post(
        path + "/decision",
        headers={**auth, "If-Match": original["etag"]},
        json={
            "decision": "approve",
            "reason": "我只核查了旧稿，不应批准新稿。",
            "verified_evidence_ids": [made["evidence"]["id"]],
        },
    )
    assert attempted.status_code == 412
    assert client.get(f"/v1/memes/{made['meme_id']}").status_code == 404
    latest = client.get(path, headers=auth).json()
    assert latest["payload"] == changed
    assert latest["edit_version"] == 2


def test_identical_saves_still_change_etag_and_validation_rolls_back(client, prepared, auth):
    made = prepared(publish=False)
    path = f"/v1/reviews/{made['revision']['id']}"
    original = client.get(path, headers=auth).json()
    saved = client.put(path, json=original["payload"], headers={**auth, "If-Match": original["etag"]}).json()
    assert saved["etag"] != original["etag"]
    failed = client.post(
        path + "/decision",
        headers={**auth, "If-Match": saved["etag"]},
        json={
            "decision": "approve",
            "reason": "未勾选新材料不能批准",
            "verified_evidence_ids": [],
        },
    )
    assert failed.status_code == 422
    latest = client.get(path, headers=auth).json()
    assert latest["etag"] == saved["etag"] and latest["edit_version"] == 2


def test_comparison_exposes_actual_baseline_and_later_publication(client, prepared, auth):
    made = prepared()
    body = {**made["payload"], "canonical_name": "合成待对照的修改"}
    draft = client.post(
        "/v1/reviews/drafts", params={"meme_id": made["meme_id"]}, json=body, headers=auth
    ).json()
    other = client.post(
        "/v1/reviews/drafts", params={"meme_id": made["meme_id"]}, json=made["payload"], headers=auth
    ).json()
    first = client.get(f"/v1/reviews/{draft['id']}/comparison", headers=auth).json()
    assert first["base"]["payload"] == made["revision"]["payload"]
    assert first["base_changed"] is False
    response = client.post(
        f"/v1/reviews/{other['id']}/decision",
        headers={**auth, "If-Match": other["etag"]},
        json={
            "decision": "approve",
            "reason": "合成后续修订发布",
            "verified_evidence_ids": [],
        },
    )
    assert response.status_code == 200
    latest = client.get(f"/v1/reviews/{draft['id']}/comparison", headers=auth).json()
    assert latest["base_changed"] is True
    assert latest["base"]["id"] == first["base"]["id"]
    assert latest["current"]["id"] == other["id"]
    assert latest["current_published_revision"] == 2
    assert latest["draft"]["etag"] != draft["etag"]


def test_parent_retraction_invalidates_old_review_snapshot(client, prepared, auth):
    made = prepared()
    draft = client.post(
        "/v1/reviews/drafts", params={"meme_id": made["meme_id"]}, json=made["payload"], headers=auth
    ).json()
    assert (
        client.post(
            f"/v1/reviews/memes/{made['meme_id']}/retract", json={"reason": "合成临时撤回"}, headers=auth
        ).status_code
        == 200
    )
    attempted = client.post(
        f"/v1/reviews/{draft['id']}/decision",
        headers={**auth, "If-Match": draft["etag"]},
        json={
            "decision": "approve",
            "reason": "过期页面不能无声重新发布",
            "verified_evidence_ids": [],
        },
    )
    assert attempted.status_code == 412
    assert client.get(f"/v1/memes/{made['meme_id']}").status_code == 404


def test_parent_change_between_read_and_conditional_write_is_rechecked(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'race.sqlite'}")
    Base.metadata.create_all(eng)
    with Session(eng) as db:
        row = content.create_draft(db, MemeDraft(canonical_name="合成真实连接竞争稿"))
        db.commit()
        identifier, meme_id, expected = row.id, row.meme_id, revisions.etag(row)
    injected = []

    def change_parent(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE revisions SET edit_version") and not injected:
            injected.append(True)
            with Session(eng) as other:
                other.get(Meme, meme_id).status = "retracted"
                other.commit()

    event.listen(eng, "before_cursor_execute", change_parent)
    try:
        with Session(eng) as db, pytest.raises(HTTPException) as caught:
            revisions.claim(db, identifier, expected)
        assert caught.value.status_code == 412
        with Session(eng) as db:
            assert db.get(Revision, identifier).edit_version == 1
            assert db.get(Meme, meme_id).status == "retracted"
    finally:
        eng.dispose()


def test_two_real_connections_share_one_edit_precondition(tmp_path):
    eng = create_engine(f"sqlite:///{tmp_path / 'concurrent.sqlite'}")
    Base.metadata.create_all(eng)
    with Session(eng) as db:
        row = content.create_draft(db, MemeDraft(canonical_name="合成并发连接稿"))
        db.commit()
        identifier, expected = row.id, revisions.etag(row)
    barrier = Barrier(2)

    def wait_before_write(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE revisions SET edit_version"):
            barrier.wait(timeout=10)

    event.listen(eng, "before_cursor_execute", wait_before_write)

    def edit(name):
        try:
            with Session(eng) as db:
                row = revisions.claim(db, identifier, expected)
                row.payload = {**row.payload, "canonical_name": name}
                db.commit()
            return 200
        except HTTPException as exc:
            return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as workers:
            codes = list(workers.map(edit, ["合成甲的修改", "合成乙的修改"]))
        assert sorted(codes) == [200, 412]
        with Session(eng) as db:
            row = db.get(Revision, identifier)
            assert row.edit_version == 2
            assert row.payload["canonical_name"] in {"合成甲的修改", "合成乙的修改"}
    finally:
        eng.dispose()
