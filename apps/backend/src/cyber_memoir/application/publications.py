"""Validate first; atomically stage all records. No fetching, extraction or publication."""

import json
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.application import content
from cyber_memoir.domain.models import Evidence, ImportRecord, Meme, Revision, Source
from cyber_memoir.domain.publications import (
    ImportPlan,
    ImportPlanItem,
    ImportResult,
    ImportResultItem,
    PublicationPackage,
    SourceRegistration,
    json_bytes,
)
from cyber_memoir.domain.schemas import EventInput, Material, MemeDraft, normalize
from cyber_memoir.domain.sources import source_identity

WARNINGS = [
    "导入只创建待审修订，不发布、不抓取、不运行模型。",
    "文本摘录随包保存；原始截图、音视频和本机路径仅是引用，不声称已归档或已校验。",
    "不自动建立定义与证据的支持关系；新增条目须在审核工作台选择字段证据。",
    "Query 材料只保留为交付溯源，不加入别名、人工金标准或搜索日志。",
]


def register_source(db: Session, registration: SourceRegistration):
    item, url = source_identity(registration.platform, registration.url)
    source = db.scalar(
        select(Source).where(Source.platform == registration.platform, Source.platform_item_id == item)
    )
    duplicate = source is not None
    if source is None:
        source = Source(
            platform=registration.platform,
            platform_item_id=item,
            canonical_url=url,
            submitted_url=url,
            title=registration.title,
            platform_published_at=registration.platform_published_at,
            availability="needs_material",
            metadata_note="人工/数据包登记；未发起平台请求，元数据尚待核对。",
        )
        db.add(source)
        db.flush()
    return source, duplicate


def material_for(source):
    return Material(
        text="\n\n".join(source.text_parts),
        kind="manual",
        locator={
            "note": "数据包携带的公开文本摘录；原始附件仅有引用，需人工核查。",
            "fields": ["text_parts"],
            "source_url": source.url,
        },
    )


def plan(db: Session, package: PublicationPackage, rows=None) -> ImportPlan:
    rows = rows if rows is not None else package.entries()
    items = []
    identities = set()
    for row in rows:
        fingerprint = row.fingerprint()
        receipt = db.get(ImportRecord, fingerprint)
        item = ImportPlanItem(canonical_name=row.canonical_name, entry_hash=fingerprint, action="blocked")
        for source in row.sources:
            platform_item_id, _ = source_identity(source.platform, source.url)
            identities.add((source.platform, platform_item_id))
        if receipt:
            revision = db.get(Revision, receipt.revision_id)
            item.action, item.target_meme_id = "duplicate", revision.meme_id
            item.revision_id, item.based_on_revision = revision.id, revision.based_on_revision
        else:
            matches = db.scalars(
                select(Meme).where(Meme.normalized_name == normalize(row.canonical_name))
            ).all()
            if row.operation == "create_new":
                if matches:
                    item.message = "同名条目已存在（包括草稿/撤回记录），请先人工消歧，不自动覆盖。"
                else:
                    item.action = "create_draft"
            elif len(matches) != 1:
                item.message = "追加目标不存在或同名不唯一；请先导入基础条目或人工消歧。"
            else:
                meme = matches[0]
                try:
                    content.public_meme(db, meme.id)
                except HTTPException:
                    item.message = "追加目标未公开或证据已失效。"
                else:
                    pending = db.scalar(
                        select(Revision.id).where(
                            Revision.meme_id == meme.id, Revision.status == "pending_review"
                        )
                    )
                    if pending:
                        item.message = "追加目标已有待审修订，请先处理，避免并行覆盖。"
                    else:
                        item.action, item.target_meme_id = "append_draft", meme.id
                        item.based_on_revision = meme.published_revision
                        if len(current_draft(db, meme.id).events) + len(row.sources) > 100:
                            item.action, item.message = (
                                "blocked",
                                "追加后超过单修订 100 个事件上限，请拆分或调整数据模型。",
                            )
            if item.action != "blocked":
                for source in row.sources:
                    identity, _ = source_identity(source.platform, source.url)
                    stored = db.scalar(
                        select(Source).where(
                            Source.platform == source.platform, Source.platform_item_id == identity
                        )
                    )
                    if stored:
                        digest = sha256(
                            json.dumps(
                                material_for(source).model_dump(), ensure_ascii=False, sort_keys=True
                            ).encode()
                        ).hexdigest()
                        evidence = db.scalar(
                            select(Evidence).where(
                                Evidence.source_id == stored.id, Evidence.content_hash == digest
                            )
                        )
                        if evidence and evidence.retracted:
                            item.action, item.message = "blocked", "同一文本证据已撤回，不能通过导入复活。"
        items.append(item)
    result = ImportPlan(
        entries_sha256=package.manifest.entries_sha256,
        groups=len(rows),
        new_groups=package.manifest.new_groups,
        existing_groups=package.manifest.existing_groups,
        meme_source_associations=package.manifest.meme_source_associations,
        unique_sources=len(identities),
        can_import=all(x.action != "blocked" for x in items),
        items=items,
        warnings=WARNINGS,
    )
    result.plan_hash = sha256(json_bytes(result.model_dump(exclude={"plan_hash"}))).hexdigest()
    return result


def current_draft(db: Session, meme_id: str) -> MemeDraft:
    snapshot = content.detail(db, meme_id)
    approved = db.scalar(
        select(Revision).where(
            Revision.meme_id == meme_id,
            Revision.status == "published",
            Revision.based_on_revision == snapshot["published_revision"] - 1,
        )
    )
    # SQLite strips offsets from DateTime; recover exact instants from the immutable
    # approved payload, not by guessing the timezone of a naive database timestamp.
    original_events = approved.payload.get("events", []) if approved else []
    for event in snapshot["events"]:
        if event.get("occurred_at_start") is not None and event["occurred_at_start"].tzinfo is None:
            candidates = []
            for original in original_events:
                if not all(
                    event.get(k) == original.get(k)
                    for k in ("event_type", "description", "to_source_id", "time_basis")
                ) or set(event["evidence_ids"]) != set(original["evidence_ids"]):
                    continue
                exact = True
                for field in ("occurred_at_start", "occurred_at_end"):
                    raw = original.get(field)
                    at = datetime.fromisoformat(raw.replace("Z", "+00:00")) if raw else None
                    if at is not None and at.tzinfo is None:
                        exact = False
                    if (at.replace(tzinfo=None) if at else None) != event.get(field):
                        exact = False
                if exact:
                    candidates.append(original)
            dates = {(x.get("occurred_at_start"), x.get("occurred_at_end")) for x in candidates}
            if len(dates) != 1:
                raise ValueError("已发布事件缺少可恢复的带时区时间；请先核查基础修订。")
            for field in ("occurred_at_start", "occurred_at_end"):
                event[field] = candidates[0].get(field)
    # Public detail includes presentation-only ids and refs; Pydantic strips those.
    return MemeDraft.model_validate(
        {
            **snapshot,
            "claims": [
                x
                for x in snapshot["claims"]
                if x["key"] in {"definition", "usage_context", "origin", "alias"}
            ],
        }
    )


def stage(
    db: Session, package: PublicationPackage, reviewer: str, expected_plan_hash: str | None = None
) -> ImportResult:
    rows = package.entries()
    # Different packages for the same names cannot race into two brand-new memes on PG.
    # Source uniqueness and receipt PK handle the remaining races; the API retries a rollback.
    if db.bind.dialect.name == "postgresql":
        for name in sorted({normalize(x.canonical_name) for x in rows}):
            lock = int.from_bytes(sha256(name.encode()).digest()[:8], "big", signed=True)
            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
        db.scalars(
            select(Meme)
            .where(Meme.normalized_name.in_([normalize(x.canonical_name) for x in rows]))
            .order_by(Meme.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).all()
    preview = plan(db, package, rows)
    if expected_plan_hash and preview.plan_hash != expected_plan_hash:
        raise HTTPException(409, "数据包或目标状态已变化，请重新预演。")
    if not preview.can_import:
        raise HTTPException(
            409,
            {
                "message": "数据包存在冲突，未导入任何条目。",
                "items": [x.model_dump() for x in preview.items if x.action == "blocked"],
            },
        )
    artifact_key = None
    results = []
    for row, planned in zip(rows, preview.items, strict=True):
        if planned.action == "duplicate":
            receipt = db.get(ImportRecord, planned.entry_hash)
            results.append(ImportResultItem(**receipt.bindings, duplicate=True))
            continue
        if artifact_key is None:
            # Store parsed, canonicalized material rather than URL session parameters.
            artifact_key, _ = storage.put(
                json_bytes(
                    {
                        "manifest": package.manifest.model_dump(mode="json"),
                        "entries": [x.model_dump(mode="json", exclude_unset=True) for x in rows],
                        "limitations": WARNINGS,
                    }
                )
            )
        source_ids, evidence_ids, events = [], [], []
        for source in row.sources:
            # Do not invent timestamps from yearless displays or equate publication with an event.
            dates = {
                r["publication"]["normalized"]
                for r in source.original_records
                if isinstance(r.get("publication"), dict)
                and isinstance(r["publication"].get("normalized"), str)
                and r["publication"]["normalized"]
            }
            published = None
            if len(dates) == 1:
                try:
                    parsed = datetime.fromisoformat(next(iter(dates)).replace("Z", "+00:00"))
                    published = parsed.astimezone(UTC) if parsed.tzinfo else None
                except (ValueError, TypeError):
                    pass
            stored, _ = register_source(
                db,
                SourceRegistration(
                    platform=source.platform,
                    url=source.url,
                    title=source.text_parts[0][:500],
                    platform_published_at=published,
                ),
            )
            evidence = content.add_material(
                db,
                stored.id,
                material_for(source),
                provenance={
                    "method": "publication_import",
                    "bundle_artifact_key": artifact_key,
                    "original_attachments_available": False,
                },
                enqueue_extract=False,
            )
            if evidence.retracted:
                raise HTTPException(409, "证据在导入期间已撤回，请重新预演。")
            source_ids.append(stored.id)
            evidence_ids.append(evidence.id)
            events.append(
                EventInput(
                    event_type="observed_use",
                    description="\n\n".join(source.text_parts)[:2000],
                    time_basis="数据包记录的用法材料，事件时间未核实；平台发布时间单独保留。",
                    evidence_ids=[evidence.id],
                    to_source_id=stored.id,
                )
            )
        if planned.action == "append_draft":
            baseline = current_draft(db, planned.target_meme_id)
            payload = baseline.model_copy(update={"events": [*baseline.events, *events]})
            # Enforce existing API limits rather than silently dropping old events.
            payload = MemeDraft.model_validate(payload.model_dump(mode="json"))
        else:
            baseline = None
            payload = MemeDraft(
                canonical_name=row.canonical_name,
                definition=row.definition or "",
                usage_context=row.usage_context or "",
                aliases=row.aliases or [],
                origin_status=row.origin_status or "unknown",
                claims=[],
                events=events,
            )
        revision = content.create_draft(db, payload, planned.target_meme_id)
        revision.payload = {
            **revision.payload,
            "_import": {
                "entry_hash": planned.entry_hash,
                "entries_sha256": package.manifest.entries_sha256,
                "evidence_ids": evidence_ids,
                "source_ids": source_ids,
                "operation": row.operation,
                "warnings": WARNINGS,
            },
            **({"_import_append_base": baseline.model_dump(mode="json")} if baseline else {}),
        }
        result = ImportResultItem(
            canonical_name=row.canonical_name,
            meme_id=revision.meme_id,
            revision_id=revision.id,
            evidence_ids=evidence_ids,
            source_ids=source_ids,
            duplicate=False,
        )
        db.add(
            ImportRecord(
                fingerprint=planned.entry_hash,
                revision_id=revision.id,
                artifact_key=artifact_key,
                imported_by=reviewer,
                bindings=result.model_dump(exclude={"duplicate"}),
            )
        )
        db.flush()
        results.append(result)
    db.commit()
    return ImportResult(entries_sha256=package.manifest.entries_sha256, items=results)
