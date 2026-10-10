"""Synthetic packages only: these names, sources and excerpts are not cultural facts."""

import copy
import json
from hashlib import sha256

import pytest
from review_requests import matching_revision
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from cyber_memoir.domain.models import (
    Event,
    Evidence,
    EvidenceLink,
    ImportRecord,
    Job,
    Meme,
    Revision,
    Source,
)


def package(entries):
    raw = "".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in entries)
    return {
        "manifest": {
            "schema_version": 1,
            "groups": len(entries),
            "new_groups": sum(x["operation"] == "create_new" for x in entries),
            "existing_groups": sum(x["operation"] == "append_derivatives" for x in entries),
            "meme_source_associations": sum(len(x["sources"]) for x in entries),
            "entries_sha256": sha256(raw.encode()).hexdigest(),
            "automatic_import": False,
        },
        "entries_jsonl": raw,
    }


def entry(name="合成导入梗", operation="create_new"):
    result = {
        "canonical_name": name,
        "operation": operation,
        "event_type": "observed_use",
        "published_meme_id": "foreign-instance-id-never-reused",
        "published_revision_id": "foreign-revision-id-never-reused",
        "sources": [
            {
                "platform": "xiaohongshu",
                "url": "https://www.xiaohongshu.com/explore/0123456789abcdef01234567?xsec_token=discard",
                "text_parts": ["仅供软件验收的合成来源摘录，不是真实文化材料。"],
                "original_records": [{"publication": {"normalized": None}, "observation": {"like": 0}}],
            },
            {
                "platform": "web",
                "url": "https://example.org/read?id=1#section",
                "text_parts": ["第二份合成测试材料。"],
                "original_records": [],
            },
        ],
        "query_evidence": [{"layer": "real_expression", "queries": [{"raw_text": "不是人工搜索日志"}]}],
    }
    if operation == "create_new":
        result.update(definition="仅用于导入测试的虚构定义。", usage_context="仅用于测试。", aliases=[])
        result["origin_status"] = "unknown"
    return result


def counts(engine):
    with Session(engine) as db:
        return tuple(
            db.scalar(select(func.count()).select_from(m)) for m in (Source, Evidence, Meme, Revision, Job)
        )


def test_import_auth_and_side_effect_free_preview(client, auth, env, tmp_path):
    data = package([entry()])
    assert client.post("/v1/reviews/imports/validate", json=data).status_code == 401
    before = counts(env)
    response = client.post("/v1/reviews/imports/validate", json=data, headers=auth)
    assert response.status_code == 200, response.text
    plan = response.json()
    assert plan["can_import"] is True
    assert plan["groups"] == 1 and plan["meme_source_associations"] == 2 and plan["unique_sources"] == 2
    assert plan["items"][0]["action"] == "create_draft"
    assert plan["plan_hash"]
    assert counts(env) == before
    assert not (tmp_path / "artifacts").exists()


def test_import_stages_unverified_private_draft_without_jobs_and_is_idempotent(client, auth, env):
    data = package([entry()])
    preview = client.post("/v1/reviews/imports/validate", json=data, headers=auth).json()
    response = client.post(
        "/v1/reviews/imports", params={"expected_plan_hash": preview["plan_hash"]}, json=data, headers=auth
    )
    assert response.status_code == 200, response.text
    result = response.json()
    item = result["items"][0]
    assert item["duplicate"] is False
    assert item["meme_id"] != "foreign-instance-id-never-reused"
    assert client.get(f"/v1/memes/{item['meme_id']}").status_code == 404
    assert client.get("/v1/stats").json()["published_memes"] == 0
    assert counts(env) == (2, 2, 1, 1, 0)
    drafts = client.get("/v1/reviews", headers=auth).json()
    payload = drafts[0]["payload"]
    assert payload["claims"] == []  # The importer must not invent definition support.
    assert payload["origin_status"] == "unknown"
    assert len(payload["events"]) == 2
    assert payload["_import"]["evidence_ids"] == item["evidence_ids"]
    assert all(x["occurred_at_start"] is None for x in payload["events"])
    with Session(env) as db:
        assert not any(e.verified for e in db.scalars(select(Evidence)))
    second = client.post("/v1/reviews/imports", json=data, headers=auth)
    assert second.status_code == 200, second.text
    assert second.json()["items"][0]["duplicate"] is True
    assert second.json()["items"][0]["revision_id"] == item["revision_id"]
    assert counts(env) == (2, 2, 1, 1, 0)
    decision = client.post(
        f"/v1/reviews/{item['revision_id']}/decision",
        json={
            "decision": "approve",
            "reason": "仍需人工选择字段证据",
            "verified_evidence_ids": item["evidence_ids"],
        },
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision_id']}/decision"),
    )
    assert decision.status_code == 422


def test_append_preserves_existing_fields_claims_events_and_relations(client, auth, prepared, env):
    old = prepared(name="合成已有梗")
    before = client.get(f"/v1/memes/{old['meme_id']}").json()
    data = package([entry("合成已有梗", "append_derivatives")])
    response = client.post("/v1/reviews/imports", json=data, headers=auth)
    assert response.status_code == 200, response.text
    item = response.json()["items"][0]
    assert item["meme_id"] == old["meme_id"]
    draft = next(x for x in client.get("/v1/reviews", headers=auth).json() if x["id"] == item["revision_id"])
    payload = draft["payload"]
    for field in ("canonical_name", "definition", "usage_context", "aliases", "origin_status"):
        assert payload[field] == before[field]
    assert old["evidence"]["id"] in payload["claims"][0]["evidence_ids"]
    assert client.get(f"/v1/memes/{old['meme_id']}").json() == before
    result = client.post(
        f"/v1/reviews/{item['revision_id']}/decision",
        json={
            "decision": "approve",
            "reason": "合成测试确认，非文化事实",
            "verified_evidence_ids": item["evidence_ids"],
        },
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision_id']}/decision"),
    )
    assert result.status_code == 200, result.text
    after = client.get(f"/v1/memes/{old['meme_id']}").json()
    for field in ("canonical_name", "definition", "usage_context", "aliases", "origin_status"):
        assert before[field] == after[field]
    assert len(after["events"]) == 2
    for platform in ("xiaohongshu", "web"):
        search = client.post("/v1/search", json={"query": "合成已有梗", "platform": platform})
        assert search.status_code == 200, search.text
    with Session(env) as db:
        assert db.get(Source, old["source"]["id"]).title == old["source"]["title"]


@pytest.mark.parametrize("change", ["definition", "aliases", "claims", "events"])
def test_append_cannot_silently_replace_protected_content(client, auth, prepared, env, change):
    old = prepared(name="合成受保护梗")
    with Session(env) as db:
        event = Event(
            meme_id=old["meme_id"],
            revision=1,
            event_type="observed_use",
            description="合成旧事件",
            time_basis="合成测试",
            to_source_id=old["source"]["id"],
        )
        db.add(event)
        db.flush()
        db.add(
            EvidenceLink(
                meme_id=old["meme_id"],
                revision=1,
                evidence_id=old["evidence"]["id"],
                event_id=event.id,
                claim_key="event",
                statement="合成旧事件",
                stance="supports",
            )
        )
        db.commit()
    result = client.post(
        "/v1/reviews/imports", json=package([entry("合成受保护梗", "append_derivatives")]), headers=auth
    )
    assert result.status_code == 200, result.text
    item = result.json()["items"][0]
    draft = next(x for x in client.get("/v1/reviews", headers=auth).json() if x["id"] == item["revision_id"])
    payload = draft["payload"]
    if change == "definition":
        payload[change] = "不同的合成定义"
    elif change == "aliases":
        payload[change] = []
    elif change == "claims":
        payload["claims"][0]["evidence_ids"] = item["evidence_ids"]
    else:
        payload["events"] = payload["events"][1:]
    payload.pop("_import_append_base", None)  # PUT must retain server-owned metadata.
    assert (
        client.put(
            f"/v1/reviews/{item['revision_id']}",
            json=payload,
            headers=matching_revision(client, auth, f"/v1/reviews/{item['revision_id']}"),
        ).status_code
        == 200
    )
    response = client.post(
        f"/v1/reviews/{item['revision_id']}/decision",
        json={"decision": "approve", "reason": "合成改动测试", "verified_evidence_ids": item["evidence_ids"]},
        headers=matching_revision(client, auth, f"/v1/reviews/{item['revision_id']}/decision"),
    )
    assert response.status_code == 422
    assert client.get(f"/v1/memes/{old['meme_id']}").json()["definition"] == old["payload"]["definition"]


def test_missing_append_target_blocks_entire_batch_and_stale_preview_is_refused(client, auth, prepared, env):
    data = package([entry(), entry("不存在的合成梗", "append_derivatives")])
    before = counts(env)
    plan = client.post("/v1/reviews/imports/validate", json=data, headers=auth).json()
    assert plan["can_import"] is False
    assert client.post("/v1/reviews/imports", json=data, headers=auth).status_code == 409
    assert counts(env) == before
    data = package([entry()])
    preview = client.post("/v1/reviews/imports/validate", json=data, headers=auth).json()
    prepared(name="合成导入梗")
    before = counts(env)
    assert (
        client.post(
            "/v1/reviews/imports",
            params={"expected_plan_hash": preview["plan_hash"]},
            json=data,
            headers=auth,
        ).status_code
        == 409
    )
    assert counts(env) == before


@pytest.mark.parametrize("mutation", ["checksum", "count", "append_fields", "no_excerpt", "duplicate_name"])
def test_invalid_packages_are_rejected_before_any_write(client, auth, env, mutation):
    e = entry()
    if mutation == "append_fields":
        e["operation"] = "append_derivatives"
    elif mutation == "no_excerpt":
        e["sources"][0]["text_parts"] = ["   "]
    data = package([e, copy.deepcopy(e)] if mutation == "duplicate_name" else [e])
    if mutation == "checksum":
        data["entries_jsonl"] += " "
    elif mutation == "count":
        data["manifest"]["groups"] = 2
    response = client.post("/v1/reviews/imports", json=data, headers=auth)
    assert response.status_code == 422, response.text
    assert counts(env) == (0, 0, 0, 0, 0)


def test_registration_is_offline_and_query_identity_is_not_discarded(client, auth, monkeypatch):
    import socket

    resolver = socket.getaddrinfo

    def local_only(host, *args, **kwargs):
        if host != "127.0.0.1":
            pytest.fail("Registration must not fetch or resolve source DNS")
        return resolver(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", local_only)

    def register(url, platform="web"):
        return client.post(
            "/v1/reviews/sources", json={"url": url, "platform": platform, "title": "合成来源"}, headers=auth
        )

    first = register("https://example.org/read?id=1#first")
    assert first.status_code == 200, first.text
    same = register("https://example.org/read?id=1#second")
    other = register("https://example.org/read?id=2")
    assert same.json()["duplicate"] is True
    assert first.json()["source"]["id"] == same.json()["source"]["id"]
    assert first.json()["source"]["id"] != other.json()["source"]["id"]
    xhs = register(
        "https://www.xiaohongshu.com/discovery/item/0123456789abcdef01234567?xsec_token=discard",
        "xiaohongshu",
    )
    assert xhs.status_code == 200, xhs.text
    assert "xsec_token" not in xhs.json()["source"]["canonical_url"]
    assert "xsec_token" not in xhs.json()["source"]["submitted_url"]
    assert (
        client.post(f"/v1/reviews/sources/{xhs.json()['source']['id']}/refresh", headers=auth).status_code
        == 422
    )
    for url in (
        "http://example.org/",
        "https://127.0.0.1/",
        "https://localhost/",
        "https://user:pass@example.org/",
        "https://example.org:8443/",
    ):
        assert register(url).status_code == 422


def test_storage_failure_rolls_back_all_database_objects(client, auth, env, monkeypatch):
    from cyber_memoir.adapters import storage

    original = storage.put
    calls = []

    def fail_material(data, *args, **kwargs):
        calls.append(data)
        if len(calls) == 2:
            raise OSError("synthetic object-store failure")
        return original(data, *args, **kwargs)

    monkeypatch.setattr(storage, "put", fail_material)
    with pytest.raises(OSError, match="synthetic"):
        client.post("/v1/reviews/imports", json=package([entry()]), headers=auth)
    assert counts(env) == (0, 0, 0, 0, 0)
    with Session(env) as db:
        assert db.scalar(select(func.count()).select_from(ImportRecord)) == 0


def test_retracted_material_and_ambiguous_targets_are_not_reused(client, auth, env, prepared):
    data = package([entry()])
    result = client.post("/v1/reviews/imports", json=data, headers=auth).json()
    evidence_id = result["items"][0]["evidence_ids"][0]
    with Session(env) as db:
        db.get(Evidence, evidence_id).retracted = True
        db.commit()
    renamed = entry("合成另一个梗")
    before = counts(env)
    assert client.post("/v1/reviews/imports", json=package([renamed]), headers=auth).status_code == 409
    assert counts(env) == before
    prepared(name="合成歧义梗")
    prepared(name="合成歧义梗")
    assert (
        client.post(
            "/v1/reviews/imports", json=package([entry("合成歧义梗", "append_derivatives")]), headers=auth
        ).status_code
        == 409
    )


def test_append_retains_timezone_from_approved_payload(client, auth, prepared):
    old = prepared(name="合成有日期梗", publish=False)
    payload = old["payload"]
    payload["events"] = [
        {
            "event_type": "observed_use",
            "description": "合成有日期事件",
            "time_basis": "合成测试时间",
            "occurred_at_start": "2026-10-09T00:00:00+08:00",
            "time_precision": "second",
            "to_source_id": old["source"]["id"],
            "evidence_ids": [old["evidence"]["id"]],
        }
    ]
    assert (
        client.put(
            f"/v1/reviews/{old['revision']['id']}",
            json=payload,
            headers=matching_revision(client, auth, f"/v1/reviews/{old['revision']['id']}"),
        ).status_code
        == 200
    )
    assert (
        client.post(
            f"/v1/reviews/{old['revision']['id']}/decision",
            headers=matching_revision(client, auth, f"/v1/reviews/{old['revision']['id']}/decision"),
            json={
                "decision": "approve",
                "reason": "合成日期测试",
                "verified_evidence_ids": [old["evidence"]["id"]],
            },
        ).status_code
        == 200
    )
    result = client.post(
        "/v1/reviews/imports", json=package([entry("合成有日期梗", "append_derivatives")]), headers=auth
    )
    assert result.status_code == 200, result.text
    draft = client.get("/v1/reviews", headers=auth).json()[0]
    assert draft["payload"]["events"][0]["occurred_at_start"] == "2026-10-09T00:00:00+08:00"


@pytest.mark.parametrize(
    "platform,url,expected",
    [
        ("bilibili", "https://www.bilibili.com/video/BV1TEST00001?p=2", "BV1TEST00001:p2"),
        ("douyin", "https://www.douyin.com/video/1234567890123456789?share=discard", "1234567890123456789"),
        (
            "xiaohongshu",
            "https://www.xiaohongshu.com/explore/ABCDEF0123456789ABCDEF01",
            "abcdef0123456789abcdef01",
        ),
    ],
)
def test_platform_identity_is_exact_and_offline(platform, url, expected):
    from cyber_memoir.domain.sources import source_identity

    assert source_identity(platform, url)[0] == expected


def test_cli_preserves_crlf_bytes_and_requires_token(tmp_path, monkeypatch, capsys):
    from cyber_memoir.cli.import_publication import main, read_package

    data = package([entry()])
    raw = data["entries_jsonl"].replace("\n", "\r\n").encode()
    data["manifest"]["entries_sha256"] = sha256(raw).hexdigest()
    (tmp_path / "entries.jsonl").write_bytes(raw)
    (tmp_path / "manifest.json").write_text(json.dumps(data["manifest"]), encoding="utf-8")
    assert read_package(tmp_path).entries_jsonl.encode() == raw
    assert main(["validate", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["valid"] is True
    monkeypatch.delenv("REVIEWER_TOKEN", raising=False)
    assert main(["import", str(tmp_path)]) == 1
    assert "REVIEWER_TOKEN" in capsys.readouterr().err


def test_additive_receipt_migration_preserves_existing_tables(tmp_path):
    import importlib.util
    from pathlib import Path

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine, inspect

    from cyber_memoir.domain.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    Base.metadata.create_all(
        engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "import_records"]
    )
    path = (
        Path(__file__).resolve().parents[1]
        / "apps/backend/migrations/versions/e4f5a6b7c8d9_import_receipts.py"
    )
    spec = importlib.util.spec_from_file_location("receipt_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        before = set(inspect(connection).get_table_names())
        migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before | {"import_records"}
        migration.downgrade()
        assert set(inspect(connection).get_table_names()) == before
    engine.dispose()


def test_shared_sources_are_deduplicated_across_entries_and_package_boundaries(client, auth, env):
    first, second = entry("合成共享来源甲"), entry("合成共享来源乙")
    first_package = package([first])
    assert client.post("/v1/reviews/imports", json=first_package, headers=auth).status_code == 200
    combined = package([first, second])
    plan = client.post("/v1/reviews/imports/validate", json=combined, headers=auth).json()
    assert plan["unique_sources"] == 2 and plan["meme_source_associations"] == 4
    response = client.post("/v1/reviews/imports", json=combined, headers=auth)
    assert response.status_code == 200, response.text
    results = response.json()["items"]
    assert results[0]["duplicate"] is True and results[1]["duplicate"] is False
    assert results[0]["source_ids"] == results[1]["source_ids"]
    assert results[0]["evidence_ids"] == results[1]["evidence_ids"]
    assert counts(env) == (2, 2, 2, 2, 0)


def test_repeated_dated_events_recover_their_own_offsets(client, auth, prepared):
    old = prepared(name="合成重复有日期事件梗", publish=False)
    payload = old["payload"]
    dates = ["2026-10-08T00:00:00+08:00", "2026-10-09T00:00:00+08:00"]
    payload["events"] = [
        {
            "event_type": "observed_use",
            "description": "相同的合成用法",
            "time_basis": "合成日期",
            "occurred_at_start": at,
            "time_precision": "second",
            "to_source_id": old["source"]["id"],
            "evidence_ids": [old["evidence"]["id"]],
        }
        for at in dates
    ]
    client.put(
        f"/v1/reviews/{old['revision']['id']}",
        json=payload,
        headers=matching_revision(client, auth, f"/v1/reviews/{old['revision']['id']}"),
    )
    client.post(
        f"/v1/reviews/{old['revision']['id']}/decision",
        headers=matching_revision(client, auth, f"/v1/reviews/{old['revision']['id']}/decision"),
        json={
            "decision": "approve",
            "reason": "合成重复事件测试",
            "verified_evidence_ids": [old["evidence"]["id"]],
        },
    )
    response = client.post(
        "/v1/reviews/imports",
        json=package([entry("合成重复有日期事件梗", "append_derivatives")]),
        headers=auth,
    )
    assert response.status_code == 200, response.text
    draft = client.get("/v1/reviews", headers=auth).json()[0]
    assert [x["occurred_at_start"] for x in draft["payload"]["events"][:2]] == dates
