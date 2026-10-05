"""Bind an independent model review to the exact record and local evidence reviewed."""
import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from materials_index import resolve_placeholder

ROOT = Path(__file__).resolve().parents[1]
SAME_MODEL_LIMITATION = "Same model; separate frozen passes, not human or independent-model review."


def same_model_error(doc: dict, review: dict, index: dict) -> str | None:
    """Allow truthful same-model review only against an unchanged frozen record."""
    if review.get("method") != "same_model_frozen_passes" or review.get("limitations") != SAME_MODEL_LIMITATION:
        return "Same-model review must disclose its method and limited independence"
    frozen = review.get("frozen_draft") or {}
    try:
        path = (ROOT / frozen["path"]).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            return "Frozen draft must be inside the workspace"
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != frozen["sha256"]:
            return "Frozen draft artifact changed"
        snapshot = json.loads(raw)
        freeze_time = datetime.fromisoformat(snapshot["frozen_at"])
        review_time = datetime.fromisoformat(review["review_started_at"])
        if freeze_time.tzinfo is None or review_time.tzinfo is None or review_time <= freeze_time:
            return "Review must start after the timestamped draft freeze"
        if fingerprint(snapshot["record"], index) != fingerprint(doc, index):
            return "Reviewed record differs from frozen draft"
    except (KeyError, TypeError, ValueError, OSError):
        return "Missing or invalid frozen same-model review artifact"
    return None


def fingerprint(doc: dict, index: dict) -> str:
    content = deepcopy(doc)
    # Loading fills IDs, not claims; a successful load must retain its review binding.
    content.pop("resolved", None)
    content["evidence_map"] = sorted((doc.get("evidence_map") or {}).keys())
    content.setdefault("curation", {}).pop("automated_review", None)
    materials = {}
    for key in content["evidence_map"]:
        found = resolve_placeholder(key, index)
        if found is None:
            raise ValueError("Missing evidence: " + key)
        materials[key] = found
    raw = json.dumps({"record": content, "materials": materials}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def review_error(doc: dict, index: dict) -> str | None:
    review = (doc.get("curation") or {}).get("automated_review")
    if not isinstance(review, dict):
        return "No automated review"
    if review.get("decision") != "accept":
        return "Record quarantined or review incomplete"
    reviewer = str(review.get("reviewer") or "").strip()
    drafter = str((doc.get("curation") or {}).get("drafted_by") or "").strip()
    if not reviewer or not drafter:
        return "A named reviewer and drafter are required"
    if reviewer.casefold() == drafter.casefold():
        error = same_model_error(doc, review, index)
        if error:
            return error
    checks = review.get("checks") or {}
    required = {"identity", "meaning", "usage", "origins", "events", "queries"}
    if set(checks) != required or any(not isinstance(v, str) or not v.strip() for v in checks.values()):
        return "Review must explain every required check"
    try:
        if review.get("fingerprint") != fingerprint(doc, index):
            return "Record or evidence changed after review"
    except ValueError as exc:
        return str(exc)
    return None
