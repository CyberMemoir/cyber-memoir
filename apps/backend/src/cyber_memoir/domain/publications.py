"""The reviewed JSONL handoff format; an import is a proposal, never an approval."""

import json
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cyber_memoir.domain.schemas import MemeDraft, normalize
from cyber_memoir.domain.sources import Platform, source_identity


class SourceRegistration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Platform
    url: str = Field(min_length=10, max_length=2000)
    title: str = Field(default="", max_length=500)
    platform_published_at: datetime | None = None

    @model_validator(mode="after")
    def identity_and_time(self):
        _, self.url = source_identity(self.platform, self.url)
        if self.platform_published_at and self.platform_published_at.tzinfo is None:
            raise ValueError("平台发布时间必须包含时区")
        return self


class PublicationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Platform
    url: str = Field(min_length=10, max_length=2000)
    text_parts: list[str] = Field(min_length=1, max_length=20)
    original_records: list[dict] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def available_excerpt(self):
        _, self.url = source_identity(self.platform, self.url)
        if not all(x.strip() for x in self.text_parts) or len("\n\n".join(self.text_parts)) > 200000:
            raise ValueError("每个来源必须携带非空且不超过 200000 字的文本摘录")
        item, _ = source_identity(self.platform, self.url)
        for record in self.original_records:
            if self.platform != "web" and record.get("platform") and record["platform"] != self.platform:
                raise ValueError("原始记录的平台与来源链接不一致")
            if (
                self.platform != "web"
                and record.get("platform_item_id")
                and str(record["platform_item_id"]) != item
            ):
                raise ValueError("原始记录的内容 ID 与来源链接不一致，不能近似替换")
        return self


class PublicationEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    canonical_name: str = Field(min_length=1, max_length=200)
    operation: Literal["create_new", "append_derivatives"]
    event_type: Literal["observed_use"] = "observed_use"
    definition: str | None = Field(default=None, max_length=5000)
    usage_context: str | None = Field(default=None, max_length=5000)
    aliases: list[str] | None = Field(default=None, max_length=50)
    origin_status: Literal["unknown", "supported", "disputed"] | None = None
    origin_verified: bool | None = None
    proposal_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    published_meme_id: str | None = None
    published_revision_id: str | None = None
    preserve_existing_fields: list[Literal["definition", "usage_context", "aliases", "origin_status"]] = (
        Field(default_factory=list)
    )
    sources: list[PublicationSource] = Field(min_length=1, max_length=100)
    query_evidence: list[dict] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def operation_is_explicit(self):
        if not normalize(self.canonical_name):
            raise ValueError("梗名称不能为空白")
        protected = {"definition", "usage_context", "aliases", "origin_status"}
        if self.operation == "append_derivatives" and self.model_fields_set & protected:
            raise ValueError("追加用法不能携带定义、使用语境、别名或起源覆盖字段")
        if self.operation == "create_new" and not (self.definition or "").strip():
            raise ValueError("新增条目需要待审定义")
        identities = [(x.platform, source_identity(x.platform, x.url)[0]) for x in self.sources]
        if len(set(identities)) != len(identities):
            raise ValueError("同一条目中的来源身份不能重复")
        return self

    def fingerprint(self):
        return sha256(json_bytes(self.model_dump(mode="json", exclude_unset=True))).hexdigest()


class PublicationManifest(BaseModel):
    # Additional delivery metadata (date, held names, approved-plan hash) is provenance only.
    model_config = ConfigDict(extra="allow")
    schema_version: Literal[1]
    groups: int = Field(ge=1, le=100)
    new_groups: int = Field(ge=0, le=100)
    existing_groups: int = Field(ge=0, le=100)
    meme_source_associations: int = Field(ge=1, le=10000)
    entries_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    automatic_import: Literal[False] = False


class PublicationPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manifest: PublicationManifest
    entries_jsonl: str = Field(min_length=1, max_length=8_000_000)

    def entries(self) -> list[PublicationEntry]:
        if len(self.entries_jsonl.encode("utf-8")) > 8_000_000:
            raise ValueError("entries.jsonl 超过 8 MB 大小限制")
        if sha256(self.entries_jsonl.encode("utf-8")).hexdigest() != self.manifest.entries_sha256:
            raise ValueError("entries.jsonl SHA-256 与 manifest 不一致")
        lines = [x for x in self.entries_jsonl.splitlines() if x.strip()]
        if len(lines) != self.manifest.groups:
            raise ValueError("manifest 的条目数量与 JSONL 不一致")
        rows = [PublicationEntry.model_validate_json(line) for line in lines]
        if len({normalize(x.canonical_name) for x in rows}) != len(rows):
            raise ValueError("一个数据包不能重复包含同名条目")
        actual = (sum(x.operation == "create_new" for x in rows), sum(len(x.sources) for x in rows))
        if actual != (self.manifest.new_groups, self.manifest.meme_source_associations) or (
            self.manifest.existing_groups != len(rows) - actual[0]
        ):
            raise ValueError("manifest 的新增、追加或来源关联数量不一致")
        return rows


def json_bytes(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


class ImportPlanItem(BaseModel):
    canonical_name: str
    entry_hash: str
    action: Literal["create_draft", "append_draft", "duplicate", "blocked"]
    target_meme_id: str | None = None
    based_on_revision: int | None = None
    revision_id: str | None = None
    message: str | None = None


class ImportPlan(BaseModel):
    entries_sha256: str
    groups: int
    new_groups: int
    existing_groups: int
    meme_source_associations: int
    unique_sources: int
    can_import: bool
    items: list[ImportPlanItem]
    warnings: list[str]
    plan_hash: str = ""


class ImportResultItem(BaseModel):
    canonical_name: str
    meme_id: str
    revision_id: str
    evidence_ids: list[str]
    source_ids: list[str]
    duplicate: bool


class ImportResult(BaseModel):
    entries_sha256: str
    items: list[ImportResultItem]
    published: Literal[False] = False


def require_append_only(payload: MemeDraft, base: dict):
    current = payload.model_dump(mode="json")
    for field in ("canonical_name", "definition", "usage_context", "aliases", "origin_status"):
        if current[field] != base[field]:
            raise ValueError(f"追加用法修订不能修改 {field}；请单独创建内容修订。")
    for field in ("claims", "events", "relations"):

        def supports(items):
            result = {}
            for item in items:
                key = json_bytes({k: v for k, v in item.items() if k != "evidence_ids"})
                result.setdefault(key, set()).update(item["evidence_ids"])
            return result

        existing, proposed = supports(base[field]), supports(current[field])
        if any(not ids <= proposed.get(key, set()) for key, ids in existing.items()):
            raise ValueError(f"追加用法修订不能移除已有 {field} 或其证据绑定。")
