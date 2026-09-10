import unicodedata
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


class Submission(BaseModel):
    url: str = Field(min_length=10, max_length=2000)
    title: str = Field(default="", max_length=500)


class Material(BaseModel):
    text: str = Field(min_length=1, max_length=200000)
    kind: Literal["manual", "subtitle", "asr", "ocr", "metadata"] = "manual"
    locator: dict = Field(default_factory=dict)
    supersedes_id: str | None = None


class Claim(BaseModel):
    key: Literal["definition", "usage_context", "origin", "alias"]
    statement: str = Field(min_length=1, max_length=5000)
    evidence_ids: list[str] = Field(min_length=1, max_length=30)
    stance: Literal["supports", "contradicts"] = "supports"


class EventInput(BaseModel):
    event_type: Literal["observed_use", "spread", "remix", "origin_claim"]
    description: str = Field(min_length=1, max_length=2000)
    occurred_at_start: datetime | None = None
    occurred_at_end: datetime | None = None
    time_precision: Literal["unknown", "year", "month", "day", "second"] = "unknown"
    time_basis: str = Field(min_length=1, max_length=500)
    to_source_id: str | None = None
    evidence_ids: list[str] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def valid_time(self):
        for value in (self.occurred_at_start, self.occurred_at_end):
            if value and value.tzinfo is None:
                raise ValueError("时间必须包含时区")
        if self.occurred_at_start and self.occurred_at_end and self.occurred_at_end < self.occurred_at_start:
            raise ValueError("结束时间不能早于开始时间")
        if self.time_precision != "unknown" and not self.occurred_at_start:
            raise ValueError("已知时间精度需要开始时间")
        return self


class RelationInput(BaseModel):
    predicate: Literal["derived_from", "variant_of", "claimed_origin", "mentions", "documented_in"]
    target_type: Literal["meme", "source", "entity"]
    target_id: str
    assertion_status: Literal["supported", "disputed"] = "supported"
    evidence_ids: list[str] = Field(min_length=1, max_length=30)


class MemeDraft(BaseModel):
    canonical_name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=50)
    definition: str = Field(default="", max_length=5000)
    usage_context: str = Field(default="", max_length=5000)
    origin_status: Literal["unknown", "supported", "disputed"] = "unknown"
    claims: list[Claim] = Field(default_factory=list, max_length=100)
    events: list[EventInput] = Field(default_factory=list, max_length=100)
    relations: list[RelationInput] = Field(default_factory=list, max_length=100)


class ReviewAction(BaseModel):
    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=2000)
    verified_evidence_ids: list[str] = Field(default_factory=list)


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=500)
    platform: Literal["bilibili", "douyin"] | None = None
    published_after: datetime | None = None
    published_before: datetime | None = None
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=1000)


class Reason(BaseModel):
    reason: str = Field(min_length=3, max_length=2000)


class MergeRequest(Reason):
    target_id: str
