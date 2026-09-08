from datetime import UTC, datetime
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def uid():
    return str(uuid4())


def now():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Entity(Identity, Base):
    __tablename__ = "entities"
    entity_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    platform_identifiers: Mapped[dict] = mapped_column(JSON, default=dict)


class Source(Identity, Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("platform", "platform_item_id"),)
    platform: Mapped[str] = mapped_column(String(20), index=True)
    platform_item_id: Mapped[str] = mapped_column(String(100))
    canonical_url: Mapped[str] = mapped_column(Text)
    submitted_url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, default="")
    author_entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"))
    platform_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    availability: Mapped[str] = mapped_column(String(32), default="pending")
    metadata_key: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(Text)


class Meme(Identity, Base):
    __tablename__ = "memes"
    canonical_name: Mapped[str] = mapped_column(String(200))
    normalized_name: Mapped[str] = mapped_column(String(200), index=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    definition: Mapped[str] = mapped_column(Text, default="")
    usage_context: Mapped[str] = mapped_column(Text, default="")
    origin_status: Mapped[str] = mapped_column(String(20), default="unknown")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    published_revision: Mapped[int] = mapped_column(Integer, default=0)
    merged_into_id: Mapped[str | None] = mapped_column(ForeignKey("memes.id"))


class Alias(Base):
    __tablename__ = "aliases"
    meme_id: Mapped[str] = mapped_column(ForeignKey("memes.id"), primary_key=True)
    normalized: Mapped[str] = mapped_column(String(200), primary_key=True, index=True)


class Evidence(Identity, Base):
    __tablename__ = "evidence"
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)
    locator: Mapped[dict] = mapped_column(JSON)
    artifact_key: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(64))
    artifact_hash: Mapped[str] = mapped_column(String(64))
    extraction_provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    retracted: Mapped[bool] = mapped_column(Boolean, default=False)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey("evidence.id"))


class Event(Identity, Base):
    __tablename__ = "events"
    meme_id: Mapped[str] = mapped_column(ForeignKey("memes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    occurred_at_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    occurred_at_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_precision: Mapped[str] = mapped_column(String(20), default="unknown")
    time_basis: Mapped[str] = mapped_column(Text)


class Relation(Identity, Base):
    __tablename__ = "relations"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN to_meme_id IS NULL THEN 0 ELSE 1 END + CASE WHEN to_source_id IS NULL THEN 0 ELSE 1 END + CASE WHEN to_entity_id IS NULL THEN 0 ELSE 1 END) = 1",
            name="one_relation_target",
        ),
    )
    meme_id: Mapped[str] = mapped_column(ForeignKey("memes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    predicate: Mapped[str] = mapped_column(String(40))
    to_meme_id: Mapped[str | None] = mapped_column(ForeignKey("memes.id"), index=True)
    to_source_id: Mapped[str | None] = mapped_column(ForeignKey("sources.id"))
    to_entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"))
    assertion_status: Mapped[str] = mapped_column(String(24), default="supported")


class EvidenceLink(Identity, Base):
    __tablename__ = "evidence_links"
    meme_id: Mapped[str] = mapped_column(ForeignKey("memes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), index=True)
    event_id: Mapped[str | None] = mapped_column(ForeignKey("events.id"))
    relation_id: Mapped[str | None] = mapped_column(ForeignKey("relations.id"))
    claim_key: Mapped[str] = mapped_column(String(100))
    statement: Mapped[str] = mapped_column(Text)
    stance: Mapped[str] = mapped_column(String(20), default="supports")


class Revision(Identity, Base):
    __tablename__ = "revisions"
    meme_id: Mapped[str] = mapped_column(ForeignKey("memes.id"), index=True)
    based_on_revision: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending_review", index=True)
    review_reason: Mapped[str | None] = mapped_column(Text)
    reviewer: Mapped[str | None] = mapped_column(String(100))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Chunk(Identity, Base):
    __tablename__ = "chunks"
    __table_args__ = (UniqueConstraint("meme_id", "revision", "evidence_id", "offset"),)
    meme_id: Mapped[str] = mapped_column(ForeignKey("memes.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidence.id"), index=True)
    offset: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list | None] = mapped_column(Vector(1024).with_variant(JSON(), "sqlite"))


class Job(Identity, Base):
    """Durable outbox + job state; Redis is only an acceleration hint."""

    __tablename__ = "jobs"
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
