from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    id: str
    platform: str
    platform_item_id: str
    canonical_url: str
    title: str
    platform_published_at: datetime | None
    availability: str
    created_at: datetime


class EvidenceOut(BaseModel):
    id: str
    source_id: str
    kind: str
    text: str
    locator: dict[str, Any]
    verified: bool
    retracted: bool
    content_hash: str
    artifact_hash: str
    created_at: datetime
    source: SourceOut | None = None


class ClaimOut(BaseModel):
    key: str
    statement: str
    stance: str
    evidence_ids: list[str]


class EventOut(BaseModel):
    id: str
    event_type: str
    description: str
    occurred_at_start: datetime | None
    occurred_at_end: datetime | None
    time_precision: str
    time_basis: str
    evidence_ids: list[str] = Field(default_factory=list)


class RelationOut(BaseModel):
    id: str
    predicate: str
    to_meme_id: str | None
    to_source_id: str | None
    to_entity_id: str | None
    assertion_status: str
    evidence_ids: list[str] = Field(default_factory=list)


class MemeOut(BaseModel):
    id: str
    canonical_name: str
    aliases: list[str]
    definition: str
    usage_context: str
    origin_status: str
    published_revision: int
    evidence: list[EvidenceOut]
    claims: list[ClaimOut]
    events: list[EventOut]
    relations: list[RelationOut]
    exact_match: bool = False
    matches: list[dict[str, Any]] = Field(default_factory=list)


class MemeRef(BaseModel):
    """Enough to address a meme and to tell two same-named ones apart."""

    id: str
    canonical_name: str
    published_revision: int
    created_at: datetime


class SearchOut(BaseModel):
    items: list[MemeOut]
    total: int
    channels: list[str]
    degraded: list[str]
    query: str
    total_is_candidate_count: bool = False


class AnswerClaim(ClaimOut):
    meme_id: str
    meme_name: str
    origin_status: str


class CitationOut(BaseModel):
    evidence_id: str
    source_id: str
    url: str
    text: str
    locator: dict[str, Any]
    content_hash: str
    meme_revision: int
    published_at: datetime | None


class AnswerOut(BaseModel):
    answer: str
    claims: list[AnswerClaim]
    citations: list[CitationOut]
    uncertainties: list[str]
    mode: str
    retrieval_version: str
    channels: list[str]
    degraded: list[str]
