"""Reviewer-only snapshots and atomic optimistic editing; never auto-merge facts."""

from hashlib import sha256

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session, object_session

from cyber_memoir.domain.models import Meme, Revision


def etag(revision: Revision, meme: Meme | None = None) -> str:
    if meme is None:
        db = object_session(revision)
        if db is None:
            raise ValueError("Revision snapshot requires its parent session")
        meme = db.get(Meme, revision.meme_id)
    state = f"{revision.id}:{revision.edit_version}:{meme.published_revision}:{meme.status}"
    return f'"review-{sha256(state.encode()).hexdigest()}"'


def claim(db: Session, identifier: str, expected: str | None) -> Revision:
    revision = db.scalar(
        select(Revision).where(Revision.id == identifier).execution_options(populate_existing=True)
    )
    if revision is None:
        raise HTTPException(404, "修订不存在")
    # Lock parent first across all review mutations. Retraction/publication state
    # is part of the snapshot; a stale editor must not silently republish it.
    meme = db.scalar(
        select(Meme)
        .where(Meme.id == revision.meme_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if expected is None or not expected.strip():
        raise HTTPException(428, "需要读取稿件后携带具体 If-Match，再保存或提交审核。")
    expected = expected.strip()
    if expected == "*" or expected.startswith("W/") or "," in expected:
        raise HTTPException(400, "审核操作只接受读取稿件时获得的单个具体强 ETag。")
    if expected != etag(revision, meme):
        raise HTTPException(412, "稿件已被修改或处理；你的本地文字未提交，请对照最新稿件。")
    if revision.status != "pending_review":
        raise HTTPException(409, "只有待审修订可编辑或审核")
    version = revision.edit_version
    parent_state = (meme.published_revision, meme.status)
    result = db.execute(
        update(Revision)
        .where(
            Revision.id == identifier, Revision.edit_version == version, Revision.status == "pending_review"
        )
        .values(edit_version=version + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise HTTPException(412, "稿件已被修改或处理；你的本地文字未提交，请对照最新稿件。")
    # The conditional write holds the row/write lock until the outer transaction
    # commits. This also works where SELECT FOR UPDATE is ignored (SQLite).
    db.refresh(revision)
    db.refresh(meme)
    if parent_state != (meme.published_revision, meme.status):
        raise HTTPException(412, "条目的公开状态已变化；请对照当前状态，不自动覆盖或重新发布。")
    return revision


def comparison(db: Session, identifier: str):
    from cyber_memoir.application.content import dump, require

    revision = require(db, Revision, identifier)
    meme = require(db, Meme, revision.meme_id)

    def snapshot(number):
        if not number:
            return None
        row = db.scalar(
            select(Revision).where(
                Revision.meme_id == meme.id,
                Revision.status == "published",
                Revision.based_on_revision == number - 1,
            )
        )
        return dump(row) if row else None

    return {
        "draft": dump(revision),
        "base": snapshot(revision.based_on_revision),
        "current": snapshot(meme.published_revision),
        "current_published_revision": meme.published_revision,
        "meme_status": meme.status,
        "base_changed": meme.published_revision != revision.based_on_revision,
    }
