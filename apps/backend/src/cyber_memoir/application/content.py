import json
from collections import defaultdict
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.domain.models import (
    Alias,
    Entity,
    Event,
    Evidence,
    EvidenceLink,
    Job,
    Meme,
    Relation,
    Revision,
    Source,
    now,
)
from cyber_memoir.domain.policy import publication_is_valid
from cyber_memoir.domain.schemas import Material, MemeDraft, ReviewAction, normalize
from cyber_memoir.ingestion.urls import canonicalize


def dump(obj):
    return {col.key: getattr(obj, col.key) for col in inspect(obj).mapper.column_attrs}


def require(db: Session, model, identifier: str):
    obj = db.get(model, identifier)
    if obj is None:
        raise HTTPException(404, "记录不存在")
    return obj


def enqueue(db: Session, kind: str, payload: dict, key: str):
    old = db.scalar(select(Job).where(Job.dedupe_key == key))
    if old:
        return old
    job = Job(kind=kind, payload=payload, dedupe_key=key)
    db.add(job)
    db.flush()
    return job


def submit(db: Session, url: str, title=""):
    platform, item, canonical = canonicalize(url)
    source = db.scalar(select(Source).where(Source.platform == platform, Source.platform_item_id == item))
    duplicate = source is not None
    if source is None:
        source = Source(
            platform=platform, platform_item_id=item, canonical_url=canonical, submitted_url=url, title=title
        )
        db.add(source)
        db.flush()
    job = enqueue(db, "ingest", {"source_id": source.id}, f"ingest:{source.id}")
    db.commit()
    return {"source": dump(source), "job_id": job.id, "duplicate": duplicate}


def add_material(db: Session, source_id: str, material: Material, provenance=None, artifact_key=None):
    source = require(db, Source, source_id)
    if not material.text.strip():
        raise HTTPException(422, "材料不能为空白")
    if not material.locator:
        raise HTTPException(422, "必须提供证据定位，例如 field、start_ms 或人工核查说明 note")
    if material.supersedes_id:
        previous = require(db, Evidence, material.supersedes_id)
        if previous.source_id != source_id:
            raise HTTPException(422, "修订必须属于同一来源")
    data = json.dumps(material.model_dump(), ensure_ascii=False, sort_keys=True).encode()
    digest = sha256(data).hexdigest()
    existing = db.scalar(
        select(Evidence).where(Evidence.source_id == source_id, Evidence.content_hash == digest)
    )
    if existing:
        return existing
    text_key, _ = storage.put(data)
    evidence = Evidence(
        source_id=source_id,
        kind=material.kind,
        text=material.text,
        locator=material.locator,
        artifact_key=artifact_key or text_key,
        content_hash=digest,
        artifact_hash=(artifact_key or text_key).split("/")[-1],
        extraction_provenance={
            "pipeline": "v1",
            "text_artifact_key": text_key,
            **(provenance or {"method": "human_submission"}),
        },
        supersedes_id=material.supersedes_id,
    )
    db.add(evidence)
    source.availability = "material_available"
    db.flush()
    enqueue(db, "extract", {"source_id": source_id}, f"extract:{evidence.id}")
    return evidence


def create_draft(db: Session, payload: MemeDraft, meme_id: str | None = None):
    if not payload.canonical_name.strip():
        raise HTTPException(422, "梗名称不能为空白")
    if meme_id:
        meme = require(db, Meme, meme_id)
        if meme.status == "merged":
            raise HTTPException(409, "该条目已合并")
    else:
        meme = Meme(canonical_name=payload.canonical_name, normalized_name=normalize(payload.canonical_name))
        db.add(meme)
        db.flush()
    revision = Revision(
        meme_id=meme.id, based_on_revision=meme.published_revision, payload=payload.model_dump(mode="json")
    )
    db.add(revision)
    db.flush()
    return revision


def _evidence_ids(payload: MemeDraft):
    return {
        eid for item in [*payload.claims, *payload.events, *payload.relations] for eid in item.evidence_ids
    }


def review(db: Session, revision_id: str, action: ReviewAction, reviewer: str):
    revision = db.scalar(select(Revision).where(Revision.id == revision_id).with_for_update())
    if not revision:
        raise HTTPException(404, "修订不存在")
    if revision.status != "pending_review":
        raise HTTPException(409, "该修订已处理")
    meme = db.scalar(select(Meme).where(Meme.id == revision.meme_id).with_for_update())
    if meme.published_revision != revision.based_on_revision:
        raise HTTPException(409, "公开版本已变化，请重新创建修订")
    if meme.status == "merged":
        raise HTTPException(409, "条目已合并")
    if action.decision == "approve":
        payload = MemeDraft.model_validate(revision.payload)
        if not payload.definition.strip():
            raise HTTPException(422, "发布前必须填写有证据支持的定义")
        for field in ("definition", "usage_context"):
            value = getattr(payload, field)
            if value and not any(
                c.key == field and c.statement == value and c.stance == "supports" for c in payload.claims
            ):
                raise HTTPException(422, f"{field} 必须有覆盖完整字段文本的支持性引用")
        if payload.origin_status != "unknown" and not any(c.key == "origin" for c in payload.claims):
            raise HTTPException(422, "来源主张必须提供专门的 origin 证据")
        if payload.origin_status == "supported" and not any(
            r.predicate == "claimed_origin" for r in payload.relations
        ):
            raise HTTPException(422, "起源主张必须关联具体 Source")
        ids = _evidence_ids(payload)
        for eid in ids:
            evidence = require(db, Evidence, eid)
            if evidence.retracted:
                raise HTTPException(422, "不能引用已撤回的证据")
            if not evidence.verified and eid not in action.verified_evidence_ids:
                raise HTTPException(422, "请显式确认所有新证据已人工核对")
            evidence.verified = True
        number = meme.published_revision + 1
        for field in ("canonical_name", "aliases", "definition", "usage_context", "origin_status"):
            setattr(meme, field, getattr(payload, field))
        meme.normalized_name = normalize(meme.canonical_name)
        meme.published_revision = number
        meme.status = "published"
        for alias in db.scalars(select(Alias).where(Alias.meme_id == meme.id)).all():
            db.delete(alias)
        db.flush()
        inherited_aliases = []
        for merged in db.scalars(select(Meme).where(Meme.merged_into_id == meme.id)):
            inherited_aliases.extend([merged.canonical_name, *merged.aliases])
        for alias in {normalize(x) for x in [meme.canonical_name, *meme.aliases, *inherited_aliases]}:
            if alias:
                db.add(Alias(meme_id=meme.id, normalized=alias))

        def link(ids, key, statement, stance="supports", **kwargs):
            for eid in set(ids):
                db.add(
                    EvidenceLink(
                        meme_id=meme.id,
                        revision=number,
                        evidence_id=eid,
                        claim_key=key,
                        statement=statement,
                        stance=stance,
                        **kwargs,
                    )
                )

        for claim in payload.claims:
            link(claim.evidence_ids, claim.key, claim.statement, claim.stance)
        for item in payload.events:
            if item.to_source_id:
                require(db, Source, item.to_source_id)
            event = Event(meme_id=meme.id, revision=number, **item.model_dump(exclude={"evidence_ids"}))
            db.add(event)
            db.flush()
            link(item.evidence_ids, "event", item.description, event_id=event.id)
        allowed = {
            "derived_from": "meme",
            "variant_of": "meme",
            "claimed_origin": "source",
            "documented_in": "source",
            "mentions": "entity",
        }
        for item in payload.relations:
            if allowed[item.predicate] != item.target_type:
                raise HTTPException(422, "关系端点类型不匹配")
            model = {"meme": Meme, "source": Source, "entity": Entity}[item.target_type]
            target = require(db, model, item.target_id)
            if item.target_type == "meme" and (target.status != "published" or target.id == meme.id):
                raise HTTPException(422, "关联目标必须为另一条已发布的梗")
            relation = Relation(
                meme_id=meme.id,
                revision=number,
                predicate=item.predicate,
                assertion_status=item.assertion_status,
                **{f"to_{item.target_type}_id": item.target_id},
            )
            db.add(relation)
            db.flush()
            link(item.evidence_ids, "relation", item.predicate, relation_id=relation.id)
        enqueue(db, "index", {"meme_id": meme.id}, f"index:{meme.id}:{number}")
    revision.status = "published" if action.decision == "approve" else "rejected"
    revision.review_reason, revision.reviewer, revision.reviewed_at = action.reason, reviewer, now()
    db.commit()
    return dump(revision)


def public_meme(db: Session, meme_id: str):
    meme = require(db, Meme, meme_id)
    if meme.status == "merged":
        raise HTTPException(409, {"message": "已合并", "merged_into_id": meme.merged_into_id})
    if not db.scalar(select(Meme.id).where(Meme.id == meme_id, publication_is_valid())):
        raise HTTPException(404, "未公开的条目或其证据已失效")
    return meme


def detail(db: Session, meme_id: str):
    meme = public_meme(db, meme_id)
    links = db.scalars(
        select(EvidenceLink).where(
            EvidenceLink.meme_id == meme.id, EvidenceLink.revision == meme.published_revision
        )
    ).all()
    evidence, claims = {}, defaultdict(list)
    for link in links:
        item = db.get(Evidence, link.evidence_id)
        if not item or item.retracted or not item.verified:
            continue
        source = db.get(Source, item.source_id)
        evidence[item.id] = {**dump(item), "source": dump(source)}
        claims[(link.claim_key, link.statement, link.stance)].append(item.id)
    return {
        **dump(meme),
        "evidence": list(evidence.values()),
        "claims": [
            {"key": k, "statement": s, "stance": st, "evidence_ids": ids}
            for (k, s, st), ids in claims.items()
        ],
        "events": [
            {**dump(x), "evidence_ids": list({link.evidence_id for link in links if link.event_id == x.id})}
            for x in db.scalars(
                select(Event)
                .where(Event.meme_id == meme.id, Event.revision == meme.published_revision)
                .order_by(Event.occurred_at_start.asc().nulls_last())
            )
        ],
        "relations": [
            {
                **dump(x),
                "evidence_ids": list({link.evidence_id for link in links if link.relation_id == x.id}),
            }
            for x in db.scalars(
                select(Relation).where(
                    Relation.meme_id == meme.id, Relation.revision == meme.published_revision
                )
            )
        ],
    }


def evidence_is_public(db: Session, evidence_id: str):
    return (
        db.scalar(
            select(EvidenceLink.id)
            .join(Meme)
            .join(Evidence)
            .where(
                EvidenceLink.evidence_id == evidence_id,
                EvidenceLink.revision == Meme.published_revision,
                publication_is_valid(),
                Evidence.verified.is_(True),
                Evidence.retracted.is_(False),
            )
            .limit(1)
        )
        is not None
    )


def retract_meme(db: Session, meme_id: str, reason: str, reviewer: str, commit=True):
    meme = db.scalar(select(Meme).where(Meme.id == meme_id).with_for_update())
    if not meme:
        raise HTTPException(404, "条目不存在")
    meme.status = "retracted"
    db.add(
        Revision(
            meme_id=meme.id,
            based_on_revision=meme.published_revision,
            status="retracted",
            payload={"action": "retract"},
            reviewer=reviewer,
            reviewed_at=now(),
            review_reason=reason,
        )
    )
    enqueue(db, "index", {"meme_id": meme.id}, f"retract:{meme.id}:{now().isoformat()}")
    if commit:
        db.commit()
    return {"id": meme.id, "status": meme.status}
