"""Prepare/validate attributed reviews of frozen saved evidence; never grade or publish automatically."""

import argparse
import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

from checkpoint import digest
from pydantic import BaseModel, ConfigDict, Field

ASSESSMENTS = ("supported", "partial", "unsupported", "contradicted", "unverifiable")
IDENTITY_FIELDS = ("meme_id", "meme_revision", "key", "statement", "stance", "evidence_ids")


class Quote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    evidence_id: str = Field(min_length=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    exact: str = Field(min_length=1)


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    audit_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    assessment: Literal["supported", "partial", "unsupported", "contradicted", "unverifiable"] | None = None
    reviewer: str | None = None
    reviewed_at: str | None = None
    reason: str | None = None
    quotes: list[Quote] = Field(default_factory=list)


class ReviewFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    scope: Literal["saved_evidence_text_not_publication"]
    queue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviews: list[Review]


def load_queue(raw):
    rows = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError("review queue must be nonempty")
    indexed, evidence_versions = {}, {}
    for row in rows:
        claim = row["claim"]
        identity = digest({key: claim.get(key) for key in IDENTITY_FIELDS})
        if row["audit_id"] != identity or identity in indexed:
            raise ValueError("queue claim identity differs or is duplicated")
        if (
            type(claim.get("meme_revision")) is not int
            or claim["meme_revision"] < 1
            or not isinstance(claim.get("statement"), str)
            or not claim["statement"].strip()
        ):
            raise ValueError("queue requires a versioned nonempty claim")
        if not all(
            isinstance(claim.get(key), str) and claim[key].strip() for key in ["meme_id", "key", "stance"]
        ):
            raise ValueError("claim needs explicit meme, field and stance identities")
        if any(row.get(key) is not None for key in ["assessment", "reviewer", "reason"]):
            raise ValueError("queue must be the ungraded audit output; reviews belong in a separate file")
        refs = claim["evidence_ids"]
        if (
            not isinstance(refs, list)
            or not refs
            or not all(isinstance(ref, str) and ref.strip() for ref in refs)
            or len(refs) != len(set(refs))
        ):
            raise ValueError("claim needs distinct evidence identities")
        evidence = {item["id"]: item for item in row["evidence"]}
        if len(evidence) != len(row["evidence"]) or set(evidence) != set(refs):
            raise ValueError("queue evidence identities differ from claim bindings")
        for item in evidence.values():
            version = digest(item)
            if item["id"] in evidence_versions and evidence_versions[item["id"]] != version:
                raise ValueError("one evidence identity has conflicting queue representations")
            evidence_versions[item["id"]] = version
            sha = item.get("content_hash", "")
            if (
                not isinstance(sha, str)
                or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
                or item.get("verified") is not True
                or item.get("retracted") is not False
                or not isinstance(item.get("text"), str)
                or not item["text"].strip()
                or (item.get("source") or {}).get("id") != item.get("source_id")
            ):
                raise ValueError("queue lacks valid saved evidence/source binding")
        indexed[identity] = row
    return indexed


def prepare(queue_raw):
    queue = load_queue(queue_raw)
    return ReviewFile(
        schema_version=1,
        scope="saved_evidence_text_not_publication",
        queue_sha256=hashlib.sha256(queue_raw).hexdigest(),
        reviews=[Review(audit_id=identifier) for identifier in queue],
    ).model_dump()


def validate(queue_raw, review_raw):
    queue = load_queue(queue_raw)
    parsed = json.loads(review_raw)
    if not isinstance(parsed, dict) or type(parsed.get("schema_version")) is not int:
        raise ValueError("schema version must be an integer")
    file = ReviewFile.model_validate(parsed)
    if file.queue_sha256 != hashlib.sha256(queue_raw).hexdigest():
        raise ValueError("queue changed; cannot reuse an older review file")
    seen, completed, pending = set(), [], set(queue)
    for review in file.reviews:
        if review.audit_id not in queue or review.audit_id in seen:
            raise ValueError("unknown or duplicated review identity")
        seen.add(review.audit_id)
        if review.assessment is None:
            if (
                any(value is not None for value in [review.reviewer, review.reviewed_at, review.reason])
                or review.quotes
            ):
                raise ValueError("pending entries must not masquerade as a completed or attributed review")
            continue
        if not all(
            isinstance(value, str) and value.strip()
            for value in [review.reviewer, review.reviewed_at, review.reason]
        ):
            raise ValueError("assessed entries require reviewer, reason and timezone-aware reviewed_at")
        reviewed = datetime.fromisoformat(review.reviewed_at.replace("Z", "+00:00"))
        if reviewed.tzinfo is None or reviewed.utcoffset() is None:
            raise ValueError("review timestamp must include a timezone")
        if review.assessment in {"supported", "partial", "contradicted"} and not review.quotes:
            raise ValueError("support/partial/contradiction needs an explicit saved-evidence passage")
        evidence = {item["id"]: item for item in queue[review.audit_id]["evidence"]}
        positions = set()
        for quote in review.quotes:
            item = evidence.get(quote.evidence_id)
            position = (quote.evidence_id, quote.start, quote.end)
            if (
                item is None
                or quote.content_hash != item["content_hash"]
                or position in positions
                or quote.end <= quote.start
                or quote.end > len(item["text"])
                or item["text"][quote.start : quote.end] != quote.exact
            ):
                raise ValueError(
                    "quote hash, identity or Unicode-codepoint selection differs from saved text"
                )
            positions.add(position)
        completed.append(review.model_dump())
        pending.remove(review.audit_id)
    counts = {assessment: 0 for assessment in ASSESSMENTS}
    counts.update(Counter(row["assessment"] for row in completed))
    return {
        "status": "complete" if not pending else "partial",
        "scope": file.scope,
        "queue_sha256": file.queue_sha256,
        "review_file_sha256": hashlib.sha256(review_raw).hexdigest(),
        "total": len(queue),
        "assessed": len(completed),
        "pending": len(pending),
        "assessment_counts": counts,
        "pending_ids": sorted(pending),
        "reviews": completed,
        "boundaries": [
            "Quote matching does not prove entailment or truth.",
            "Reviewer/timestamp are declared attribution, not authenticated identity or chronology.",
            "This report cannot approve, edit, retract or publish culture records.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["prepare", "validate"])
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out.resolve() in {
        args.queue.resolve(),
        args.reviews.resolve() if args.reviews else args.queue.resolve(),
    }:
        parser.error("output must be a new file, never an input path")
    if args.action == "validate" and not args.reviews:
        parser.error("validate requires --reviews")
    if args.action == "prepare" and args.reviews:
        parser.error("prepare does not overwrite or import previous assessments")
    queue_raw = args.queue.read_bytes()
    review_raw = args.reviews.read_bytes() if args.reviews else None
    result = prepare(queue_raw) if args.action == "prepare" else validate(queue_raw, review_raw)
    if args.queue.read_bytes() != queue_raw:
        raise ValueError("queue changed during processing; no report written")
    if args.reviews and args.reviews.read_bytes() != review_raw:
        raise ValueError("reviews changed during processing; no report written")
    rendered = (
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    args.out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(rendered)
    summary = (
        {"prepared": len(result["reviews"]), "assessed": 0}
        if args.action == "prepare"
        else {key: result[key] for key in ["status", "total", "assessed", "pending"]}
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
