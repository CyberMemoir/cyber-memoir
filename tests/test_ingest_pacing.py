"""Platform rate limiting is a transient condition, not a broken source.

Bilibili answers bursts with HTTP 412 however correctly the request is signed, so the
constraint is volume over time. The worker treats that as "ask again later" rather than
spending its attempt budget and marking the source as needing human material.
"""

import subprocess
from datetime import UTC, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from cyber_memoir.domain.models import Job, Source, now
from cyber_memoir.ingestion import media
from cyber_memoir.workers.main import _claim_fetch_slot, run_once


def _blocked(*args, **kwargs):
    raise subprocess.CalledProcessError(
        1, "yt-dlp", stderr=b"ERROR: [BiliBili] Request is blocked by server (412), please wait"
    )


def _gone(*args, **kwargs):
    raise subprocess.CalledProcessError(1, "yt-dlp", stderr=b"ERROR: [BiliBili] Video unavailable")


def test_rate_limit_is_recognised_and_named(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _blocked)
    with pytest.raises(media.PlatformRateLimited):
        media.metadata("https://www.bilibili.com/video/BV1TEST00001")


def test_other_failures_keep_their_own_type(monkeypatch):
    monkeypatch.setattr(subprocess, "run", _gone)
    with pytest.raises(subprocess.CalledProcessError):
        media.metadata("https://www.bilibili.com/video/BV1TEST00001")


def _submit(client, url="https://www.bilibili.com/video/BV1TEST00001"):
    response = client.post("/v1/submissions", json={"url": url, "title": "合成测试来源"})
    assert response.status_code == 202, response.text
    return response.json()["source"]["id"]


def _run_ingest(monkeypatch, failure):
    """Drive one worker cycle with the platform failing in a given way."""
    monkeypatch.setattr(subprocess, "run", failure)
    monkeypatch.setattr("cyber_memoir.workers.main._claim_fetch_slot", lambda *_: True)
    assert run_once() is True


def test_a_block_leaves_the_source_alone_and_keeps_the_job(client, env, monkeypatch):
    source_id = _submit(client)
    _run_ingest(monkeypatch, _blocked)
    with Session(env) as db:
        source = db.get(Source, source_id)
        job = db.scalar(select(Job).where(Job.kind == "ingest"))
        # Nothing is wrong with this source; a reviewer has nothing to supply.
        assert source.availability != "needs_material"
        assert source.last_error is None
        assert job.status == "pending"
        # SQLite hands back a naive datetime where PostgreSQL keeps the zone; compare the
        # instant rather than the representation.
        retry_at = job.available_at
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        assert retry_at > now() + timedelta(minutes=30)


def test_an_unavailable_source_does_ask_for_material(client, env, monkeypatch):
    source_id = _submit(client, "https://www.bilibili.com/video/BV1TEST00002")
    _run_ingest(monkeypatch, _gone)
    with Session(env) as db:
        source = db.get(Source, source_id)
        assert source.availability == "needs_material"
        assert source.last_error


def test_the_gate_allows_one_fetch_per_interval():
    class DeadRedis:
        def set(self, *args, **kwargs):
            raise ConnectionError("redis down")

    redis = DeadRedis()
    # In-process fallback: sound for the single-worker V1 deployment, and it degrades the
    # same way the API rate limiter does when Redis is unavailable.
    assert _claim_fetch_slot(redis, 60) is True
    assert _claim_fetch_slot(redis, 60) is False
    assert _claim_fetch_slot(redis, 0) is True
