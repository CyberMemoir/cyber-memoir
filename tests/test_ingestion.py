from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.domain.models import Evidence, Job, Revision, Source, now
from cyber_memoir.ingestion import pipeline
from cyber_memoir.ingestion.subtitles import parse_subtitles
from cyber_memoir.workers.main import run_once


def test_srt_and_vtt_timestamps():
    for header, ts in [("1", "00:01:02,500"), ("WEBVTT\n\n", "01:02.500")]:
        result = parse_subtitles(f"{header}\n{ts} --> 00:01:03.750\n合成字幕\n", "srt")
        assert result == [{"text": "合成字幕", "locator": {"start_ms": 62500, "end_ms": 63750}}]


def test_bilibili_json_timestamps():
    result = parse_subtitles('{"body":[{"from":1.5,"to":3,"content":"合成字幕"}]}', "json")
    assert result[0]["locator"] == {"start_ms": 1500, "end_ms": 3000}


def test_inline_bilibili_subtitle_and_redis_loss_recovery(client, env, monkeypatch):
    data = client.post("/v1/submissions", json={"url": "https://www.bilibili.com/video/BV1TEST00001"}).json()
    monkeypatch.setattr(
        pipeline,
        "metadata",
        lambda url: {
            "title": "合成测试",
            "subtitles": {"zh-CN": [{"ext": "srt", "data": "1\n00:00:01,000 --> 00:00:02,000\n合成字幕\n"}]},
        },
    )
    assert run_once()  # Redis points to closed port; durable polling must still work.
    assert run_once()
    with Session(env) as db:
        source = db.get(Source, data["source"]["id"])
        assert source.availability == "material_available"
        assert db.scalar(select(Evidence).where(Evidence.kind == "subtitle")).locator["start_ms"] == 1000
        assert db.scalar(select(Revision)).status == "pending_review"
        assert db.get(Job, data["job_id"]).status == "succeeded"


def test_platform_failure_requests_human_material(client, env, monkeypatch):
    data = client.post(
        "/v1/submissions", json={"url": "https://www.douyin.com/video/1234567890123456789"}
    ).json()

    def blocked(url):
        raise RuntimeError("fixture platform unavailable")

    monkeypatch.setattr(pipeline, "metadata", blocked)
    assert run_once()
    with Session(env) as db:
        assert db.get(Source, data["source"]["id"]).availability == "needs_material"


def test_expired_job_lease_can_be_reclaimed(client, env, monkeypatch):
    data = client.post("/v1/submissions", json={"url": "https://www.bilibili.com/video/BV1TEST00001"}).json()
    with Session(env) as db:
        job = db.get(Job, data["job_id"])
        job.status = "running"
        job.started_at = now() - timedelta(hours=2)
        db.commit()
    monkeypatch.setattr(pipeline, "metadata", lambda url: {"title": "合成材料"})
    assert run_once()
    with Session(env) as db:
        assert db.get(Job, data["job_id"]).status == "succeeded"


def test_temp_uploads_do_not_share_deletion_key(env):
    a, hash_a = storage.put(b"fixture media", temporary=True)
    b, hash_b = storage.put(b"fixture media", temporary=True)
    assert a != b and hash_a == hash_b
    storage.remove_temporary(a)
    assert storage.get(b) == b"fixture media"
