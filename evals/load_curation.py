#!/usr/bin/env python3
"""Load hand-curated records into a running Cyber Memoir instance.

    python evals/load_curation.py --dry-run
    python evals/load_curation.py

Walks each evals/curation/*.yaml, submits the sources it cites, posts the OCR/ASR
material as Evidence, writes the returned ids back into evidence_map, then creates
and approves a draft. Rerunnable: submissions dedupe on (platform, item id) and
material dedupes on content hash, so a second run adds nothing.

A relation may name another meme instead of a video, with target_type: meme and
target_name: <that meme's canonical_name>. The named meme must already be published,
so records are loaded in dependency order rather than alphabetically.

Explainer episodes are tiered C: archived explainers, not primary records.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "evals" / "curation"
FEASIBILITY = ROOT / "evals" / "feasibility"
BV = re.compile(r"BV[0-9A-Za-z]{10}")


def token() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("REVIEWER_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("在 .env 里找不到 REVIEWER_TOKEN")


def load_platform_index() -> dict[str, dict]:
    """bv -> platform facts already resolved by evals/feasibility/prep.py."""
    facts = {}
    for path in sorted(FEASIBILITY.glob("*.derivatives.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if row.get("resolved") == "True" and row.get("upload_date"):
                    facts[row["bv_id"]] = {"title": row.get("title") or "", "date": row["upload_date"]}
    return facts


def load_material_index() -> dict[str, list[dict]]:
    """episode id -> its Material payloads, narration first."""
    index = {}
    for path in sorted(FEASIBILITY.glob("materials/*.materials.json")):
        episode = path.name.replace(".materials.json", "")
        index[episode] = json.loads(path.read_text(encoding="utf-8"))["materials"]
    return index


def resolve_placeholder(key: str, index: dict[str, list[dict]]) -> tuple[str, dict] | None:
    """Map an evidence_map key onto (episode, Material). Keys look like
    ocr-narration-<EP>, ocr-<BV of a cited work>, or asr-<EP>."""
    if key.startswith("ocr-narration-"):
        episode = key[len("ocr-narration-") :]
        return (episode, index[episode][0]) if episode in index else None
    if key.startswith("asr-"):
        episode = key[len("asr-") :]
        transcript = FEASIBILITY / ("%s.transcript.txt" % episode)
        if not transcript.exists():
            return None
        return episode, {
            "text": transcript.read_text(encoding="utf-8"),
            "kind": "asr",
            "locator": {"start_ms": 0, "note": "%s 语音转写全文（faster-whisper）" % episode},
        }
    found = BV.search(key)
    if not found:
        return None
    target = found.group(0)
    for episode, materials in index.items():
        for material in materials[1:]:
            if target in material["locator"].get("note", ""):
                return episode, material
    return None


class Loader:
    def __init__(self, base: str, dry: bool, pace: float = 1.1):
        self.dry = dry
        # The API caps POST/PUT at 60 per minute per client; stay just under it.
        self.pace = pace
        self.client = httpx.Client(base_url=base, timeout=60, trust_env=False)
        self.auth = {"Authorization": "Bearer %s" % token()}
        self.sources: dict[str, str] = {}
        self.memes: dict[str, str] = {}

    def post(self, path: str, payload: dict) -> httpx.Response:
        time.sleep(self.pace)
        response = self.client.post(path, json=payload, headers=self.auth)
        response.raise_for_status()
        return response

    def source_for(self, bv: str) -> str:
        """Submit a bilibili video once; return its Source id."""
        if bv in self.sources:
            return self.sources[bv]
        if self.dry:
            self.sources[bv] = "dry-%s" % bv
            return self.sources[bv]
        response = self.post("/v1/submissions", {"url": "https://www.bilibili.com/video/%s" % bv, "title": ""})
        self.sources[bv] = response.json()["source"]["id"]
        return self.sources[bv]

    def metadata(self, source_id: str, title: str, date: str, reason: str) -> None:
        """Seed facts ingestion could not write, e.g. the platform refused the fetch."""
        if self.dry:
            return
        payload = {"reason": reason}
        if title:
            payload["title"] = title
        if date:
            payload["platform_published_at"] = "%s-%s-%sT00:00:00+08:00" % (date[:4], date[4:6], date[6:8])
        self.post("/v1/reviews/sources/%s/metadata" % source_id, payload)

    def tier(self, source_id: str, value: str, reason: str) -> None:
        if self.dry:
            return
        self.post("/v1/reviews/sources/%s/tier" % source_id, {"tier": value, "reason": reason})

    def material(self, source_id: str, payload: dict) -> str:
        if self.dry:
            return "dry-evidence"
        return self.post("/v1/sources/%s/materials" % source_id, payload).json()["id"]

    def meme_for(self, name: str) -> str | None:
        """The id of an already-published meme, by its canonical name.

        There is no lookup-by-name endpoint, so this goes through search, which
        matches the canonical name exactly - and then checks the name back, because
        a near-miss hit would silently point the relation at the wrong meme."""
        if self.dry:
            return "dry-meme"
        if name in self.memes:
            return self.memes[name]
        time.sleep(self.pace)
        found = self.client.post("/v1/search", json={"query": name, "limit": 10})
        found.raise_for_status()
        for item in found.json()["items"]:
            if item["canonical_name"] == name:
                self.memes[name] = item["id"]
                return item["id"]
        return None

    def publish(self, draft: dict, evidence_ids: list[str], name: str) -> str:
        if self.dry:
            return "dry-revision"
        revision = self.post("/v1/reviews/drafts", draft).json()["id"]
        self.post(
            "/v1/reviews/%s/decision" % revision,
            {
                "decision": "approve",
                "reason": "人工策展：定义与用法出自讲解视频旁白，衍生时间来自平台元数据（%s）" % name,
                "verified_evidence_ids": evidence_ids,
            },
        )
        return revision


def target_id(relation: dict, sources: dict[str, str], memes: dict[str, str]) -> str | None:
    if relation.get("target_bv"):
        return sources.get(relation["target_bv"])
    if relation.get("target_name"):
        return memes.get(relation["target_name"])
    return relation.get("target_id")


def cited_bv(item: dict) -> str | None:
    """The work an event is about, taken from its evidence key only."""
    for key in item.get("evidence", []):
        found = BV.search(key)
        if found and not key.startswith("ocr-narration-"):
            return found.group(0)
    return None


def order_by_dependency(paths: list[Path], docs: dict[Path, dict]) -> list[Path]:
    """A record naming another meme has to be loaded after it.

    Alphabetical order put 才是王道 before 闹吃VS古振兴, which it derives from, and the
    relation cannot resolve until the target is published. Anything in a cycle, or
    naming a meme no record defines, keeps its alphabetical place and fails loudly at
    publish time rather than being silently dropped here."""
    owner = {docs[path]["canonical_name"]: path for path in paths}
    pending = list(paths)
    done: set[Path] = set()
    ordered: list[Path] = []
    while pending:
        ready = [
            path
            for path in pending
            if all(
                owner[name] in done
                for name in (
                    r.get("target_name")
                    for r in docs[path].get("relations") or []
                )
                if name in owner and owner[name] is not path
            )
        ]
        if not ready:  # a cycle: give up on ordering, keep the input order
            ordered.extend(pending)
            break
        ordered.extend(ready)
        done.update(ready)
        pending = [path for path in pending if path not in done]
    return ordered


def build_draft(doc: dict, ids: dict[str, str], sources: dict[str, str], memes: dict[str, str]) -> dict:
    def refs(item):
        return [ids[k] for k in item.get("evidence", []) if k in ids]

    events = []
    for item in doc.get("events") or []:
        event = {k: v for k, v in item.items() if k != "evidence"}
        event["evidence_ids"] = refs(item)
        target = cited_bv(item)
        if target and target in sources:
            event["to_source_id"] = sources[target]
        # PyYAML gives real datetimes; the API wants ISO strings.
        for field in ("occurred_at_start", "occurred_at_end"):
            if isinstance(event.get(field), datetime):
                event[field] = event[field].isoformat()
        events.append(event)
    return {
        "canonical_name": doc["canonical_name"],
        "aliases": doc.get("aliases") or [],
        "definition": doc.get("definition") or "",
        "usage_context": doc.get("usage_context") or "",
        "origin_status": doc.get("origin_status", "unknown"),
        "claims": [
            {
                "key": c["key"],
                "statement": c["statement"],
                "stance": c.get("stance", "supports"),
                "evidence_ids": refs(c),
            }
            for c in doc.get("claims") or []
        ],
        "events": events,
        "relations": [
            {
                "predicate": r["predicate"],
                "target_type": r.get("target_type", "source"),
                # target_bv names a video, target_name another meme; neither id is
                # known until that thing exists in the archive.
                "target_id": target_id(r, sources, memes),
                "assertion_status": r.get("assertion_status", "supported"),
                "evidence_ids": refs(r),
            }
            for r in doc.get("relations") or []
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pace", type=float, default=1.1)
    args = parser.parse_args()

    index = load_material_index()
    platform = load_platform_index()
    loader = Loader(args.api, args.dry_run, args.pace)
    episodes: set[str] = set()
    tiered: set[str] = set()
    failures = 0

    paths = [p for p in sorted(CURATION.glob("*.yaml")) if not p.name.startswith("_")]
    docs = {path: yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths}

    for path in order_by_dependency(paths, docs):
        raw = path.read_text(encoding="utf-8")
        doc = docs[path]
        name = doc["canonical_name"]
        print("\n=== %s  (%s) ===" % (name, path.name))

        ids: dict[str, str] = {}
        for key in (doc.get("evidence_map") or {}):
            found = resolve_placeholder(key, index)
            if not found:
                print("  x 无法定位证据 %s" % key)
                failures += 1
                continue
            episode, payload = found
            source_id = loader.source_for(episode)
            loader.tier(source_id, "C", "讲解类视频，属证据分级 C（存档式解说），非原始记录")
            episodes.add(episode)
            ids[key] = loader.material(source_id, payload)
            print("  证据 %-34s -> %s" % (key, ids[key][:8]))

        # Each cited derivative becomes a Source so its Event can point at it.
        for item in doc.get("events") or []:
            target = cited_bv(item)
            if target:
                loader.source_for(target)
        for item in doc.get("relations") or []:
            if item.get("target_bv"):
                loader.source_for(item["target_bv"])
        for bv, source_id in loader.sources.items():
            if bv in episodes or bv in tiered:
                continue
            tiered.add(bv)
            loader.tier(source_id, "A", "作品原帖本身，属证据分级 A（原始记录）")
            fact = platform.get(bv)
            if fact:
                loader.metadata(
                    source_id, fact["title"], fact["date"],
                    "日期与标题取自 yt-dlp 对平台元数据的解析；抓取受限，ingest 未能写入",
                )

        memes: dict[str, str] = {}
        for item in doc.get("relations") or []:
            wanted = item.get("target_name")
            if not wanted:
                continue
            found = loader.meme_for(wanted)
            if not found:
                print("  x 关系指向的梗《%s》尚未发布" % wanted)
                failures += 1
            else:
                memes[wanted] = found

        draft = build_draft(doc, ids, loader.sources, memes)
        if any(r["target_id"] is None for r in draft["relations"]):
            print("  x 有关系的目标无法解析，跳过")
            failures += 1
            continue
        # Every referenced id must be confirmed, relations included, or approve is refused.
        every_id = sorted(
            {i for c in draft["claims"] for i in c["evidence_ids"]}
            | {i for e in draft["events"] for i in e["evidence_ids"]}
            | {i for r in draft["relations"] for i in r["evidence_ids"]}
        )
        if not every_id:
            print("  x 没有可用证据，跳过")
            failures += 1
            continue
        try:
            revision = loader.publish(draft, every_id, name)
            print("  已发布 revision %s（证据 %d 条，事件 %d 条）"
                  % (revision[:8], len(every_id), len(draft["events"])))
        except httpx.HTTPStatusError as exc:
            print("  x 发布失败 %s: %s" % (exc.response.status_code, exc.response.text[:200]))
            failures += 1
            continue

        if not args.dry_run and ids:
            for key, value in ids.items():
                raw = re.sub(r"^(  %s:).*$" % re.escape(key), r"\1 %s" % value, raw, flags=re.M)
            raw = raw.replace("resolved: false", "resolved: true", 1)
            path.write_text(raw, encoding="utf-8")

    print("\n完成，%d 处失败。" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
