"""Sanitised, timestamped observations; no network, credentials or model calls."""

import json
import math
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

METADATA_FIELDS = (
    "id",
    "title",
    "description",
    "uploader",
    "uploader_id",
    "channel",
    "channel_id",
    "timestamp",
    "upload_date",
    "duration",
    "webpage_url",
)
METRIC_FIELDS = (
    "view_count",
    "like_count",
    "comment_count",
    "repost_count",
    "share_count",
    "favorite_count",
    "uploader_follower_count",
)
STATUSES = {"observed", "fetch_failed", "rate_limited"}


def page_url(url: str) -> str:
    """Keep page identity, never credentials, query tokens or signed media URLs."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Observation requires a public page URL without credentials")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def build_observation(
    url: str,
    data: dict | None = None,
    *,
    status: str = "observed",
    entrypoint: str,
    observed_at: datetime | None = None,
) -> dict:
    if status not in STATUSES:
        raise ValueError("Unknown observation status")
    stamp = observed_at or datetime.now(UTC)
    if stamp.tzinfo is None:
        raise ValueError("Observation time must include a timezone")
    data = data or {}
    # Failed requests do not establish counters or a takedown.
    if status != "observed":
        data = {}
    metadata = {
        key: value
        for key in METADATA_FIELDS
        if type(value := data.get(key)) in (str, int, float)
        and (not isinstance(value, float) or math.isfinite(value))
    }
    if metadata.get("webpage_url"):
        try:
            metadata["webpage_url"] = page_url(str(metadata["webpage_url"]))
        except ValueError:
            metadata.pop("webpage_url")
    metrics, raw_metrics = {}, {}
    for key in METRIC_FIELDS:
        value = data.get(key)
        metrics[key] = value if type(value) is int and value >= 0 else None
        # Preserve abbreviated displays without manufacturing an exact count.
        raw_metrics[key] = value if type(value) in (int, float, str) else None
        if isinstance(raw_metrics[key], float) and not math.isfinite(raw_metrics[key]):
            raw_metrics[key] = None
    try:
        collector_version = version("yt-dlp")
    except PackageNotFoundError:
        collector_version = None
    return {
        "schema_version": 1,
        "observation_id": str(uuid4()),
        "observed_at": stamp.astimezone(UTC).isoformat(),
        "source_url": page_url(url),
        "status": status,
        "collector": {"method": "yt-dlp", "version": collector_version, "entrypoint": entrypoint},
        "metadata": metadata,
        "metrics": metrics,
        "raw_metrics": raw_metrics,
    }


def append_observation(directory: Path, observation: dict) -> Path:
    """One exclusive file per actual fetch; identical counters remain separate observations."""
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (observation["observation_id"] + ".json")
    raw = (json.dumps(observation, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
    with target.open("xb") as handle:
        handle.write(raw)
    return target
