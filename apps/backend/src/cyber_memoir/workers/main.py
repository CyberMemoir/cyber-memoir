import logging
import signal
import threading
from datetime import timedelta

from redis import Redis
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cyber_memoir.adapters.storage import remove_temporary
from cyber_memoir.config import settings
from cyber_memoir.db import engine
from cyber_memoir.domain.models import Job, Source, now
from cyber_memoir.ingestion.pipeline import extract, ingest, process_media
from cyber_memoir.search.indexing import index_meme

log = logging.getLogger(__name__)


def run_once() -> bool:
    cfg = settings()
    redis = Redis.from_url(cfg.redis_url, socket_connect_timeout=1, socket_timeout=1, decode_responses=True)
    with Session(engine()) as db:
        # This small relay replaces a separate outbox service in V1.
        ready = list(
            db.scalars(select(Job.id).where(Job.status == "pending", Job.available_at <= now()).limit(100))
        )
        hint = None
        try:
            for jid in ready:
                if redis.set(f"memoir:dispatch:{jid}", "1", nx=True, ex=30):
                    redis.rpush("memoir:jobs", jid)
            hint = redis.lpop("memoir:jobs")
        except Exception:
            pass  # PostgreSQL polling is the durable recovery path.
        eligible = or_(
            (Job.status == "pending") & (Job.available_at <= now()),
            (Job.status == "running")
            & (Job.started_at < now() - timedelta(seconds=cfg.task_timeout_seconds)),
        )
        query = (
            select(Job).where(eligible).order_by(Job.created_at).with_for_update(skip_locked=True).limit(1)
        )
        job = db.scalar(query.where(Job.id == hint)) if hint else None
        job = job or db.scalar(query)
        if not job:
            return False
        job.status, job.started_at = "running", now()
        job.attempts += 1
        jid = job.id
        db.commit()
    with Session(engine()) as db:
        job = db.scalar(select(Job).where(Job.id == jid).with_for_update())
        kind, payload = job.kind, job.payload
        try:
            if kind == "ingest":
                ingest(db, **payload)
            elif kind == "extract":
                extract(db, **payload)
            elif kind == "index":
                index_meme(db, **payload)
            elif kind == "media":
                process_media(db, **payload)
            else:
                raise ValueError("Unknown job kind")
            job.status, job.finished_at, job.error = "succeeded", now(), None
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(Job, jid)
            job.error = f"{type(exc).__name__}: 任务失败，详情见服务端日志"
            job.status = "failed" if job.attempts >= 3 or kind == "media" else "pending"
            job.available_at = now() + timedelta(seconds=min(300, 10 * 2**job.attempts))
            if kind == "media":
                source = db.get(Source, payload["source_id"])
                source.availability, source.last_error = "needs_material", job.error
            db.commit()
            log.exception("job_failed id=%s kind=%s", jid, kind)
        if kind == "media" and job.status in {"failed", "succeeded"}:
            try:
                remove_temporary(payload["key"])
            except Exception:
                log.exception("temporary_cleanup_failed job=%s", jid)
    return True


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    while not stopping.is_set():
        try:
            if not run_once():
                stopping.wait(2)
        except Exception:
            log.exception("worker_loop_failed")
            stopping.wait(5)


if __name__ == "__main__":
    main()
