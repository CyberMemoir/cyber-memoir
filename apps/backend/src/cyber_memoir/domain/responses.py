from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    id: str
    platform: str
    platform_item_id: str
    canonical_url: str
    title: str
    platform_published_at: datetime | None
    availability: str
    source_tier: str | None = None
    metadata_note: str | None = None
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


class TargetRef(BaseModel):
    """The far end of an event or relation, named and dated, so a reader needs no second
    request to label an edge or place it in time.

    availability means different things by type, so switch on type before reading it.
    For a source it is the archive's ingestion state - pending, needs_material,
    material_available - and says nothing about whether the video is still up on the
    platform; no takedown status is recorded anywhere. For a meme it is published or
    withdrawn, and a withdrawn target comes back with no label.

    published_at is an instant in UTC. A video posted at 00:00 in Beijing comes back as
    16:00 the previous day, so slicing the first ten characters reads the wrong date;
    render it in Asia/Shanghai.
    """

    type: Literal["meme", "source", "entity"]
    id: str
    label: str
    url: str | None = None
    published_at: datetime | None = None
    availability: str | None = None
    tier: str | None = None


class EventOut(BaseModel):
    id: str
    event_type: str
    description: str
    occurred_at_start: datetime | None
    occurred_at_end: datetime | None
    time_precision: str
    time_basis: str
    to_source_id: str | None = None
    target: TargetRef | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class RelationOut(BaseModel):
    id: str
    predicate: str
    to_meme_id: str | None
    to_source_id: str | None
    to_entity_id: str | None
    assertion_status: str
    target: TargetRef | None = None
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
    # Best calibrated score among this item's retrieved chunks; None when nothing scored it.
    retrieval_score: float | None = None


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
    # False means no calibrated scorer ran, so the ADR 0004 floor could not be applied.
    scores_calibrated: bool = False


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


class UniverseBand(BaseModel):
    """A quiet period cut out of the axis. start and end are axis positions; days is how
    long the silence really was, which the band must show since its width does not."""

    start: float
    end: float
    date_from: str
    date_to: str
    days: int


class UniverseTick(BaseModel):
    t: float
    date: str


class Star(BaseModel):
    """One dated piece of a meme's lineage.

    t is its position on the galaxy's time axis, 0 at the earliest star, and null when
    the star has no date - an undated star is evidence without a time, which is not the
    same as a missing stage. date is the calendar day in Beijing; never derive it from
    at, which is UTC.
    """

    id: str
    stage: Literal["source", "popularized_by", "derivative", "derived_meme"]
    kind: Literal["source", "meme"]
    target_id: str | None
    label: str
    url: str | None
    bvid: str | None
    tier: str | None
    at: datetime | None
    date: str | None
    t: float | None
    milestone: bool
    evidence_ids: list[str]


class Emergence(BaseModel):
    """When the meme is first evidenced as a meme: its first derivative, else the work that
    popularized it, else its earliest upstream source. basis says which, so a galaxy dated
    only by old material can be drawn as such."""

    at: datetime | None
    date: str | None
    basis: Literal["derivative", "popularized_by", "source", "none"]


class Galaxy(BaseModel):
    meme_id: str
    name: str
    definition: str
    emergence: Emergence
    u: float | None
    stars: list[Star]
    milestones: dict[str, str | None] = Field(
        description="The first star of each stage by date. null means the stage has no evidence "
        "at all - draw an empty slot - which differs from a stage whose stars are merely undated."
    )
    bands: list[UniverseBand]
    ticks: list[UniverseTick]


class UniverseAxis(BaseModel):
    bands: list[UniverseBand]
    ticks: list[UniverseTick]


class UniverseLink(BaseModel):
    from_meme_id: str
    to_meme_id: str
    predicate: str


class UniverseOut(BaseModel):
    timezone: str
    quiet_gap_days: int
    axis: UniverseAxis
    galaxies: list[Galaxy]
    links: list[UniverseLink]
