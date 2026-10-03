"""Transactional evaluation journal with exclusive ownership and frozen context."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def public_snapshot(client):
    response = client.get("/v1/universe")
    response.raise_for_status()
    ids = sorted(g["meme_id"] for g in response.json()["galaxies"])
    records = []
    evidence_ids = set()
    for identifier in ids:
        response = client.get(f"/v1/memes/{identifier}")
        response.raise_for_status()
        record = response.json()
        records.append(record)
        for group in ("claims", "events", "relations"):
            for item in record.get(group, []):
                evidence_ids.update(item.get("evidence_ids", []))
    evidence = []
    for identifier in sorted(evidence_ids):
        response = client.get(f"/v1/evidence/{identifier}")
        response.raise_for_status()
        evidence.append(response.json())
    return digest({"records": records, "evidence": evidence})


class Checkpoint:
    def __init__(self, path: Path, context: dict):
        path.parent.mkdir(parents=True, exist_ok=True)
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
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS cases (position INTEGER PRIMARY KEY, result TEXT)"
        )
        serialized = json.dumps(context, ensure_ascii=False, sort_keys=True)
        existing = self.db.execute("SELECT context FROM run WHERE id=1").fetchone()
        if existing and existing[0] != serialized:
            self.close()
            raise ValueError("Checkpoint context changed: use a new checkpoint file")
        self.db.execute(
            "INSERT OR IGNORE INTO run VALUES (1, ?, 'running')", (serialized,)
        )
        self.db.execute("UPDATE run SET status='running' WHERE id=1")
        self.db.commit()

    def get(self, position):
        row = self.db.execute(
            "SELECT result FROM cases WHERE position=?", (position,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def save(self, position, result):
        self.db.execute(
            "INSERT INTO cases VALUES (?, ?)",
            (position, json.dumps(result, ensure_ascii=False)),
        )
        self.db.commit()

    def finish(self, success):
        self.db.execute(
            "UPDATE run SET status=? WHERE id=1", ("complete" if success else "failed",)
        )
        self.db.commit()

    def close(self):
        self.db.close()
        self.lock.close()
