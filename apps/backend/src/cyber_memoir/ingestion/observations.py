"""Store an immutable observation artifact and its queryable database record."""

import json
from datetime import datetime

from sqlalchemy.orm import Session

from cyber_memoir.adapters import storage
from cyber_memoir.domain.models import Source, SourceObservation
from cyber_memoir.domain.observations import build_observation


def record_observation(
    db: Session, source: Source, data: dict | None = None, *, status: str = "observed"
) -> SourceObservation:
    payload = build_observation(source.canonical_url, data, status=status, entrypoint="backend_ingest")
    key, digest = storage.put(json.dumps(payload, ensure_ascii=False, allow_nan=False).encode())
    observation = SourceObservation(
        id=payload["observation_id"],
        source_id=source.id,
        observed_at=datetime.fromisoformat(payload["observed_at"]),
        status=status,
        payload=payload,
        artifact_key=key,
        artifact_hash=digest,
    )
    db.add(observation)
    return observation
