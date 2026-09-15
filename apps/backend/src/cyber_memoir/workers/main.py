import logging
import signal
import threading
import time
from datetime import timedelta

from redis import Redis
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from cyber_memoir.adapters.storage import remove_temporary
from cyber_memoir.config import settings
from cyber_memoir.db import engine
from cyber_memoir.domain.models import Job, Source, now
from cyber_memoir.ingestion.media import PlatformRateLimited
from cyber_memoir.ingestion.pipeline import extract, ingest, process_media
from cyber_memoir.search.indexing import index_meme

log = logging.getLogger(__name__)

# Only these reach the platform; indexing and extraction are local and must keep flowing
# even while fetching is paused.
PLATFORM_KINDS = ("ingest", "media")
# None means no fetch has happened in this process. 0.0 would be a lie: time.monotonic()
# counts from boot, so on a freshly started host every early moment sits within `interval`
# of zero and the gate would refuse the first fetch for up to five minutes. The dev machine
# never saw it - 5.7 days of uptime - and CI, which boots a runner per job, failed on it.
_last_fetch: list[float | None] = [None]


def _claim_fetch_slot(redis, interval: int) -> bool:
    """One platform fetch per interval across the worker, whatever the queue depth.

    Per-job backoff cannot pace this: twenty ready jobs still fire twenty requests back to
    back. Redis holds the gate so it survives a restart; the in-process fallback matches how
    the API rate limiter degrades, and is sound for the single-worker V1 deployment.

    An interval of 0 disables pacing, which is what the test environment wants: a suite that
    waited out the production interval between worker cycles would take minutes.
    """
    if interval <= 0:
        return True
    try:
        return bool(redis.set("memoir:platform:gate", "1", nx=True, ex=interval))
    except Exception:
        previous = _last_fetch[0]
        if previous is not None and time.monotonic() - previous < interval:
            return False
        _last_fetch[0] = time.monotonic()
        return True


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
        if not _claim_fetch_slot(redis, cfg.platform_fetch_interval_seconds):
            eligible = eligible & Job.kind.notin_(PLATFORM_KINDS)
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
            if isinstance(exc, PlatformRateLimited):
                # A block is transient. Waiting it out is the only useful response, so this
                # gets its own budget and does not spend the ordinary attempt allowance.
                job.status = "failed" if job.attempts >= cfg.platform_block_max_attempts else "pending"
                job.available_at = now() + timedelta(seconds=cfg.platform_block_backoff_seconds)
                job.error = "PlatformRateLimited: 平台限流，稍后自动重试"
            else:
                job.status = (
                    "failed" if job.attempts >= cfg.job_max_attempts or kind == "media" else "pending"
                )
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
