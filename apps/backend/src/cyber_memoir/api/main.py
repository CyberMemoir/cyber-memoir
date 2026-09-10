import contextlib
import hashlib
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from redis import Redis
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.api.auth import reviewer, submitter
from cyber_memoir.api.body_limit import BodyLimitMiddleware
from cyber_memoir.application import content
from cyber_memoir.config import settings
from cyber_memoir.db import session
from cyber_memoir.domain.models import Alias, Entity, Evidence, EvidenceLink, Job, Meme, Revision, Source, now
from cyber_memoir.domain.responses import AnswerOut, EvidenceOut, MemeOut, MemeRef, SearchOut
from cyber_memoir.domain.schemas import (
    Material,
    MemeDraft,
    MergeRequest,
    Reason,
    ReviewAction,
    SearchRequest,
    Submission,
    normalize,
)
from cyber_memoir.rag.answer import answer
from cyber_memoir.search.retrieval import search

DB = Annotated[Session, Depends(session)]
Reviewer = Annotated[str, Depends(reviewer)]


@contextlib.asynccontextmanager
async def lifespan(app):
    from cyber_memoir.mcp.server import mcp

    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Cyber Memoir",
    version="0.1.0",
    lifespan=lifespan,
    description="Evidence-first 中文互联网文化记忆。所有公开文化断言均经过人工审核。",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings().cors_origins.split(","),
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(BodyLimitMiddleware, max_bytes=settings().max_material_bytes + 100000)
_limits = defaultdict(deque)


@app.middleware("http")
async def safeguards(request: Request, call_next):
    # Do not trust arbitrary X-Forwarded-For. V1 also has a global cap behind a proxy.
    if request.method in {"POST", "PUT"}:
        length = request.headers.get("content-length")
        if length and (not length.isdigit() or int(length) > settings().max_material_bytes + 100000):
            return JSONResponse(status_code=413, content={"detail": "请求过大"})
        key = hashlib.sha256((request.client.host if request.client else "unknown").encode()).hexdigest()[:24]
        try:
            redis = Redis.from_url(settings().redis_url, socket_timeout=0.3, socket_connect_timeout=0.3)
            bucket = f"memoir:rate:{key}:{int(time.time() // 60)}"
            count = redis.incr(bucket)
            redis.expire(bucket, 120)
        except Exception:
            if len(_limits) > 10000:
                _limits.clear()
            values = _limits[key]
            while values and values[0] < time.monotonic() - 60:
                values.popleft()
            values.append(time.monotonic())
            count = len(values)
        if count > 60:
            return JSONResponse(status_code=429, content={"detail": "请求频率过高，请稍后重试"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(ValueError)
async def invalid_value(request, exc):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.get("/health/live")
def live():
    return {"status": "ok"}


@app.get("/health/ready")
def ready(db: DB):
    db.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/v1/stats")
def stats(db: DB):
    return {
        "published_memes": db.scalar(
            select(func.count()).select_from(Meme).where(Meme.status == "published")
        ),
        "evidence_first": True,
    }


@app.post("/v1/submissions", dependencies=[Depends(submitter)], status_code=202)
def submit_url(body: Submission, db: DB):
    try:
        return content.submit(db, body.url, body.title)
    except IntegrityError:
        db.rollback()
        return content.submit(db, body.url, body.title)


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, db: DB):
    job = content.require(db, Job, job_id)
    return {k: v for k, v in content.dump(job).items() if k not in {"payload", "dedupe_key"}}


@app.post("/v1/jobs/{job_id}/retry")
def retry_job(job_id: str, db: DB, who: Reviewer):
    job = content.require(db, Job, job_id)
    if job.status != "failed" or job.kind == "media":
        raise HTTPException(409, "仅可重试失败的非临时媒体任务；媒体请重新上传")
    job.status, job.attempts, job.available_at = "pending", 0, now()
    db.commit()
    return {"id": job.id, "status": job.status}


@app.post("/v1/sources/{source_id}/materials", dependencies=[Depends(submitter)], status_code=201)
def material(source_id: str, body: Material, db: DB):
    evidence = content.add_material(db, source_id, body)
    db.commit()
    return content.dump(evidence)


@app.post("/v1/sources/{source_id}/media", dependencies=[Depends(submitter)], status_code=202)
async def media(source_id: str, db: DB, file: UploadFile = File(...)):
    content.require(db, Source, source_id)
    mime = file.content_type or ""
    if mime not in {
        "image/png",
        "image/jpeg",
        "image/webp",
        "audio/mpeg",
        "audio/wav",
        "audio/mp4",
        "video/mp4",
        "audio/x-wav",
    }:
        raise HTTPException(415, "支持 PNG/JPEG/WebP、MP3/WAV/M4A/MP4")
    data = await file.read(settings().max_material_bytes + 1)
    await file.close()
    if len(data) > settings().max_material_bytes:
        raise HTTPException(413, "媒体材料上限 16 MiB")
    if not data:
        raise HTTPException(422, "文件为空")
    key, digest = storage.put(data, mime, temporary=True)
    job = content.enqueue(
        db,
        "media",
        {"source_id": source_id, "key": key, "kind": "ocr" if mime.startswith("image/") else "asr"},
        f"media:{source_id}:{digest}:{now().isoformat()}",
    )
    db.commit()
    return {"job_id": job.id}


@app.get("/v1/sources/{source_id}")
def source_detail(source_id: str, db: DB):
    source = content.require(db, Source, source_id)
    evidence = [
        content.dump(e)
        for e in db.scalars(select(Evidence).where(Evidence.source_id == source_id))
        if content.evidence_is_public(db, e.id)
    ]
    return {**content.dump(source), "evidence": evidence}


@app.get("/v1/evidence/{evidence_id}", response_model=EvidenceOut)
def evidence_detail(evidence_id: str, db: DB):
    if not content.evidence_is_public(db, evidence_id):
        raise HTTPException(404, "证据尚未公开或已撤回")
    evidence = content.require(db, Evidence, evidence_id)
    return {**content.dump(evidence), "source": content.dump(db.get(Source, evidence.source_id))}


@app.get("/v1/evidence/{evidence_id}/artifact")
def evidence_artifact(evidence_id: str, db: DB):
    if not content.evidence_is_public(db, evidence_id):
        raise HTTPException(404, "证据尚未公开或已撤回")
    item = db.get(Evidence, evidence_id)
    return Response(
        storage.get(item.artifact_key),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="evidence-{item.id}.bin"'},
    )


@app.get("/v1/memes", response_model=list[MemeRef])
def memes_by_name(db: DB, name: str = Query(min_length=1, max_length=200)):
    """Exact lookup by canonical name, so a tool that knows the name need not search.

    Search is the wrong instrument for this: it is ranked, it is approximate, and it
    drags in the reranker, so a name a caller already knows exactly cannot be turned
    into an id while any of that is unavailable.
    """
    return content.find_by_name(db, name)


@app.get("/v1/memes/{meme_id}", response_model=MemeOut)
def meme_detail(meme_id: str, db: DB):
    return content.detail(db, meme_id)


@app.get("/v1/memes/{meme_id}/timeline")
def timeline(meme_id: str, db: DB):
    result = content.detail(db, meme_id)
    return {
        "events": result["events"],
        "evidence": result["evidence"],
        "claims": result["claims"],
        "note": "事件时间不等于采集时间；本库最早记录不等于互联网起源。",
    }


@app.get("/v1/memes/{meme_id}/relations")
def relations(meme_id: str, db: DB):
    result = content.detail(db, meme_id)
    return {"relations": result["relations"], "evidence": result["evidence"]}


@app.post("/v1/search", response_model=SearchOut)
def search_api(body: SearchRequest, db: DB):
    return search(db, body)


@app.post("/v1/answers", response_model=AnswerOut)
def answers_api(body: SearchRequest, db: DB):
    if not body.query.strip():
        raise HTTPException(422, "请输入问题")
    return answer(db, body)


@app.get("/v1/reviews")
def reviews(db: DB, who: Reviewer, status: str = "pending_review"):
    return [
        content.dump(x)
        for x in db.scalars(
            select(Revision).where(Revision.status == status).order_by(Revision.created_at).limit(200)
        )
    ]


@app.get("/v1/reviews/sources/{source_id}")
def review_source(source_id: str, db: DB, who: Reviewer):
    return {
        "source": content.dump(content.require(db, Source, source_id)),
        "evidence": [
            content.dump(e) for e in db.scalars(select(Evidence).where(Evidence.source_id == source_id))
        ],
    }


@app.get("/v1/reviews/evidence/{evidence_id}")
def review_evidence(evidence_id: str, db: DB, who: Reviewer):
    item = content.require(db, Evidence, evidence_id)
    return {**content.dump(item), "source": content.dump(db.get(Source, item.source_id))}


@app.post("/v1/reviews/sources/{source_id}/refresh", status_code=202)
def refresh_source(source_id: str, db: DB, who: Reviewer):
    content.require(db, Source, source_id)
    job = content.enqueue(db, "ingest", {"source_id": source_id}, f"refresh:{source_id}:{now().isoformat()}")
    db.commit()
    return {"job_id": job.id}


@app.post("/v1/reviews/drafts", status_code=201)
def draft(body: MemeDraft, db: DB, who: Reviewer, meme_id: str | None = None):
    revision = content.create_draft(db, body, meme_id)
    db.commit()
    return content.dump(revision)


@app.put("/v1/reviews/{revision_id}")
def edit_draft(revision_id: str, body: MemeDraft, db: DB, who: Reviewer):
    revision = db.scalar(select(Revision).where(Revision.id == revision_id).with_for_update())
    if not revision:
        raise HTTPException(404, "修订不存在")
    if revision.status != "pending_review":
        raise HTTPException(409, "只有待审修订可编辑")
    revision.payload = {
        **body.model_dump(mode="json"),
        **{k: v for k, v in revision.payload.items() if k.startswith("_")},
    }
    db.commit()
    return content.dump(revision)


@app.post("/v1/reviews/{revision_id}/decision")
def decision(revision_id: str, body: ReviewAction, db: DB, who: Reviewer):
    return content.review(db, revision_id, body, who)


@app.get("/v1/reviews/memes/{meme_id}/history")
def history(meme_id: str, db: DB, who: Reviewer):
    return [
        content.dump(x)
        for x in db.scalars(
            select(Revision).where(Revision.meme_id == meme_id).order_by(Revision.created_at.desc())
        )
    ]


@app.post("/v1/reviews/memes/{meme_id}/retract")
def retract(meme_id: str, body: Reason, db: DB, who: Reviewer):
    return content.retract_meme(db, meme_id, body.reason, who)


@app.post("/v1/reviews/evidence/{evidence_id}/retract")
def retract_evidence(evidence_id: str, body: Reason, db: DB, who: Reviewer):
    item = content.require(db, Evidence, evidence_id)
    item.retracted = True
    impacted = list(
        db.scalars(
            select(Meme.id)
            .join(EvidenceLink)
            .where(
                EvidenceLink.evidence_id == item.id,
                EvidenceLink.revision == Meme.published_revision,
                Meme.status == "published",
            )
            .distinct()
        )
    )
    for mid in sorted(impacted):
        content.retract_meme(db, mid, f"证据 {item.id} 撤回：{body.reason}", who, commit=False)
    db.commit()
    return {"evidence_id": item.id, "retracted_memes": impacted}


@app.post("/v1/reviews/memes/{meme_id}/merge")
def merge(meme_id: str, body: MergeRequest, db: DB, who: Reviewer):
    if meme_id == body.target_id:
        raise HTTPException(422, "不能合并到自身")
    locked = db.scalars(
        select(Meme).where(Meme.id.in_([meme_id, body.target_id])).order_by(Meme.id).with_for_update()
    ).all()
    if len(locked) != 2:
        raise HTTPException(404, "条目不存在")
    source, target = content.public_meme(db, meme_id), content.public_meme(db, body.target_id)
    source.status, source.merged_into_id = "merged", target.id
    for alias in [source.canonical_name, *source.aliases]:
        normalized = normalize(alias)
        if not db.get(Alias, (target.id, normalized)):
            db.add(Alias(meme_id=target.id, normalized=normalized))
    db.add(
        Revision(
            meme_id=source.id,
            based_on_revision=source.published_revision,
            payload={"merged_into_id": target.id},
            status="merged",
            review_reason=body.reason,
            reviewer=who,
            reviewed_at=now(),
        )
    )
    content.enqueue(db, "index", {"meme_id": source.id}, f"merge:{source.id}:{now().isoformat()}")
    db.commit()
    return {"merged_into_id": target.id, "note": "历史证据保留，事实不自动迁移；需在目标条目创建审核修订。"}


class EntityInput(BaseModel):
    entity_type: str = Field(max_length=32)
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list)
    platform_identifiers: dict = Field(default_factory=dict)


@app.post("/v1/reviews/entities", status_code=201)
def add_entity(body: EntityInput, db: DB, who: Reviewer):
    item = Entity(**body.model_dump())
    db.add(item)
    db.commit()
    return content.dump(item)


@app.post("/v1/reviews/reindex", status_code=202)
def reindex(db: DB, who: Reviewer):
    count = 0
    for meme in db.scalars(select(Meme)):
        content.enqueue(db, "index", {"meme_id": meme.id}, f"rebuild:{meme.id}:{now().isoformat()}")
        count += 1
    db.commit()
    return {"queued": count}


# SDK protocol adapter; no duplicated business rules or arbitrary execution tools.
from cyber_memoir.mcp.server import mcp  # noqa: E402

app.mount("/mcp", mcp.streamable_http_app())
