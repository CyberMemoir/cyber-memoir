"""Actual fetch history survives refreshes and downstream failures, without session data."""

import importlib.util
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.domain.models import Job, Source, SourceObservation
from cyber_memoir.domain.observations import append_observation, build_observation
from cyber_memoir.ingestion import pipeline
from cyber_memoir.workers.main import run_once

ROOT = Path(__file__).resolve().parents[1]
URL = "https://www.bilibili.com/video/BV1TEST00001"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_counts_time_and_allowlist_do_not_invent_or_leak_data(tmp_path):
    observed_at = datetime(2026, 10, 7, tzinfo=UTC)
    payload = build_observation(
        URL + "?session=private#fragment",
        {
            "title": "测试",
            "timestamp": 123,
            "view_count": 0,
            "like_count": "1.2万",
            "comment_count": float("nan"),
            "share_count": True,
            "webpage_url": URL + "?token=private",
            "cookies": "private",
            "http_headers": {"Authorization": "private"},
            "formats": [{"url": "private"}],
        },
        observed_at=observed_at,
        entrypoint="fixture",
    )
    assert payload["observed_at"] == observed_at.isoformat()
    assert payload["metadata"]["timestamp"] == 123  # Publication is not observation time.
    assert payload["metrics"]["view_count"] == 0
    assert payload["metrics"]["like_count"] is None
    assert payload["raw_metrics"]["like_count"] == "1.2万"
    assert payload["metrics"]["repost_count"] is None
    assert payload["raw_metrics"]["comment_count"] is None
    assert payload["raw_metrics"]["share_count"] is None
    first = append_observation(tmp_path, payload)
    assert "private" not in first.read_text(encoding="utf-8")
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        append_observation(tmp_path, payload)
    assert first.read_bytes() == original
    second = append_observation(tmp_path, build_observation(URL, {"view_count": 0}, entrypoint="fixture"))
    assert first != second and len(list(tmp_path.glob("*.json"))) == 2


def test_refresh_keeps_old_counters_and_latest_source_metadata(client, env, monkeypatch):
    source_id = client.post("/v1/submissions", json={"url": URL}).json()["source"]["id"]
    results = iter([{"title": "旧标题", "view_count": 10}, {"title": "新标题", "view_count": 20}])
    monkeypatch.setattr(pipeline, "metadata", lambda _: next(results))
    with Session(env) as db:
        pipeline.ingest(db, source_id)
        db.commit()
        first = db.scalar(select(SourceObservation))
        first_bytes = storage.get(first.artifact_key)
        pipeline.ingest(db, source_id)
        db.commit()
        rows = db.scalars(select(SourceObservation).order_by(SourceObservation.observed_at)).all()
        assert [row.payload["metrics"]["view_count"] for row in rows] == [10, 20]
        assert db.get(Source, source_id).title == "新标题"
        assert storage.get(first.artifact_key) == first_bytes
        assert json.loads(first_bytes) == first.payload


def test_fetch_survives_worker_rollback_after_material_failure(client, env, monkeypatch):
    submitted = client.post("/v1/submissions", json={"url": URL}).json()
    monkeypatch.setattr(pipeline, "metadata", lambda _: {"title": "测试", "view_count": 42})

    def fail_material(*args, **kwargs):
        raise RuntimeError("synthetic extraction failure")

    monkeypatch.setattr(pipeline, "add_material", fail_material)
    assert run_once()
    with Session(env) as db:
        assert db.get(Job, submitted["job_id"]).status == "pending"
        observation = db.scalar(select(SourceObservation))
        assert observation.status == "observed"
        assert observation.payload["metrics"]["view_count"] == 42
        assert storage.get(observation.artifact_key)


def test_download_info_deleted_only_after_safe_history_is_saved(tmp_path, monkeypatch):
    prep = load_file("observation_prep", ROOT / "evals/feasibility/prep.py")
    raw = tmp_path / "video.info.json"
    raw.write_text(json.dumps({"title": "测试", "view_count": 30, "formats": [{"url": "private"}]}))
    prep.retain_download_observation(tmp_path, URL, raw)
    assert not raw.exists()
    saved = next((tmp_path / "observations").glob("*.json"))
    assert json.loads(saved.read_text())["metrics"]["view_count"] == 30
    assert "private" not in saved.read_text()
    raw.write_text('{"title":"retained"}')

    def disk_full(*args, **kwargs):
        raise OSError("synthetic disk full")

    monkeypatch.setattr(prep, "append_observation", disk_full)
    with pytest.raises(OSError):
        prep.retain_download_observation(tmp_path, URL, raw)
    assert raw.read_text() == '{"title":"retained"}'


@pytest.mark.parametrize("failure", ["rate_limited", "fetch_failed"])
def test_metadata_only_revisit_stops_on_failure_without_touching_inputs(tmp_path, monkeypatch, failure):
    prep = load_file("observation_revisit", ROOT / "evals/feasibility/prep.py")
    unchanged = tmp_path / "existing.derivatives.csv"
    unchanged.write_bytes(b"untouched")
    calls = []
    results = iter(
        [
            subprocess.CompletedProcess([], 0, '{"view_count":0}', ""),
            subprocess.CompletedProcess([], 1, "", "HTTP 412 session=private"),
        ]
    )

    def probe(args):
        calls.append(args)
        if failure == "fetch_failed" and len(calls) == 2:
            raise subprocess.TimeoutExpired("fixture", 300)
        return next(results)

    monkeypatch.setattr(prep, "run", probe)
    waits = []
    monkeypatch.setattr(prep.time, "sleep", waits.append)
    monkeypatch.setattr(
        prep.sys, "argv", ["prep", "observe", URL, URL + "2", URL + "3", "--out", str(tmp_path)]
    )
    assert prep.main() == 3
    assert len(calls) == 2 and waits == [20]
    assert all("--skip-download" in args and args[args.index("--retries") + 1] == "0" for args in calls)
    snapshots = [json.loads(path.read_text()) for path in (tmp_path / "observations").glob("*.json")]
    assert {item["status"] for item in snapshots} == {"observed", failure}
    failed = next(item for item in snapshots if item["status"] == failure)
    assert all(value is None for value in failed["metrics"].values())
    assert unchanged.read_bytes() == b"untouched"
    with pytest.raises(ValueError):
        prep.observe_sources([URL], tmp_path, sleep=1)
    with pytest.raises(ValueError):
        prep.observe_sources(["https://user:password@example.test/page"], tmp_path)
    assert len(calls) == 2


def test_migration_preserves_existing_source_without_fake_history():
    migration = load_file(
        "observation_migration", ROOT / "apps/backend/migrations/versions/d3e4f5a6b7c8_source_observations.py"
    )
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        Source.__table__.create(connection)
        connection.execute(
            Source.__table__.insert().values(
                id="old",
                platform="bilibili",
                platform_item_id="old",
                canonical_url=URL,
                submitted_url=URL,
                title="kept",
            )
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert connection.execute(text("SELECT title FROM sources")).scalar_one() == "kept"
        assert connection.execute(text("SELECT count(*) FROM source_observations")).scalar_one() == 0
        assert "source_observations" in inspect(connection).get_table_names()
    engine.dispose()
