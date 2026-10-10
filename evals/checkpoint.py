"""Transactional evaluation journal with exclusive ownership and frozen context."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def collect_public_snapshot(client):
    response = client.get("/v1/universe")
    response.raise_for_status()
    ids = sorted(g["meme_id"] for g in response.json()["galaxies"])
    records, evidence_ids = [], set()
    for identifier in ids:
        response = client.get(f"/v1/memes/{identifier}")
        response.raise_for_status()
        record = response.json()
        records.append(record)
        evidence_ids.update(e["id"] for e in record.get("evidence", []))
        for group in ("claims", "events", "relations"):
            for item in record.get(group, []):
                evidence_ids.update(item.get("evidence_ids", []))
    evidence = []
    for identifier in sorted(evidence_ids):
        response = client.get(f"/v1/evidence/{identifier}")
        response.raise_for_status()
        evidence.append(response.json())
    return {"records": records, "evidence": evidence}


def public_snapshot(client):
    return digest(collect_public_snapshot(client))


class Checkpoint:
    def __init__(self, path: Path, context: dict):
        self.lock, self.db = None, None
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.lock = open(str(path) + ".lock", "a+b")
            self.lock.seek(0)
            if os.name == "nt":
                import msvcrt

                if path.with_name(path.name + ".lock").stat().st_size == 0:
                    self.lock.write(b"0")
                    self.lock.flush()
                self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.db = sqlite3.connect(path)
            self.db.execute("PRAGMA synchronous=FULL")
            self.db.execute(
                "CREATE TABLE IF NOT EXISTS run (id INTEGER PRIMARY KEY, context TEXT, status TEXT)"
            )
            self.db.execute("CREATE TABLE IF NOT EXISTS cases (position INTEGER PRIMARY KEY, result TEXT)")
            serialized = json.dumps(context, ensure_ascii=False, sort_keys=True, allow_nan=False)
            existing = self.db.execute("SELECT context, status FROM run WHERE id=1").fetchone()
            if existing and existing[0] != serialized:
                raise ValueError("Checkpoint context changed: use a new checkpoint file")
            if existing and existing[1] == "invalid":
                raise ValueError("Checkpoint invalidated: use a new checkpoint file")
            self.db.execute("INSERT OR IGNORE INTO run VALUES (1, ?, 'running')", (serialized,))
            self.db.execute("UPDATE run SET status='running' WHERE id=1")
            self.db.commit()
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def get(self, position):
        row = self.db.execute("SELECT result FROM cases WHERE position=?", (position,)).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, position, result):
        self.db.execute(
            "INSERT INTO cases VALUES (?, ?)",
            (
                position,
                json.dumps(result, ensure_ascii=False, allow_nan=False),
            ),
        )
        self.db.commit()

    def finish(self, success):
        self.db.execute("UPDATE run SET status=? WHERE id=1", ("complete" if success else "failed",))
        self.db.commit()

    def invalidate(self, reason):
        # Do not turn an invalid run back into a resumable failed one.
        self.db.execute("UPDATE run SET status='invalid' WHERE id=1")
        self.db.commit()

    def close(self):
        try:
            if self.db is not None:
                self.db.close()
                self.db = None
        finally:
            if self.lock is not None:
                self.lock.close()
                self.lock = None
