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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from materials_index import load_material_index, resolve_placeholder  # noqa: E402


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


class Loader:
    def __init__(self, base: str, dry: bool, pace: float = 1.1):
        self.dry = dry
        # The API caps POST/PUT at 60 per minute per client; stay just under it.
        self.pace = pace
        self.client = httpx.Client(base_url=base, timeout=60, trust_env=False)
        self.auth = {"Authorization": "Bearer %s" % token()}
        self.sources: dict[str, str] = {}
        self.memes: dict[str, str] = {}
        self.duplicates: dict[str, list[str]] = {}

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

        Where several share the name, the oldest wins and the rest are reported: it
        is deterministic, and it is the id anything else is most likely to already
        reference."""
        if self.dry:
            return "dry-meme"
        if name in self.memes:
            return self.memes[name]
        rows = self.lookup(name)
        if not rows:
            return None
        if len(rows) > 1:
            self.duplicates[name] = [x["id"] for x in rows[1:]]
        self.memes[name] = rows[0]["id"]
        return rows[0]["id"]

    def lookup(self, name: str) -> list[dict]:
        """Published memes with this canonical name, oldest first."""
        if self.dry:
            return []
        response = self.client.get("/v1/memes", params={"name": name})
        response.raise_for_status()
        return response.json()

    def publish(self, draft: dict, evidence_ids: list[str], name: str, reason: str) -> str:
        """Revise the meme of this name if it exists, and only otherwise create one.

        Without the meme_id the API creates a new meme every time, so each rerun of
        this script minted another copy - the archive reached 42 published memes for
        ten curated records before anyone looked."""
        if self.dry:
            return "dry-revision"
        existing = self.meme_for(name)
        path = "/v1/reviews/drafts" + ("?meme_id=%s" % existing if existing else "")
        revision = self.post(path, draft).json()["id"]
        self.post(
            "/v1/reviews/%s/decision" % revision,
            {
                "decision": "approve",
                "reason": reason,
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


def approval_reason(doc: dict, name: str) -> str:
    """What the approved revision says about who wrote it.

    A definition drafted by a model and confirmed by a curator is not the same thing as
    one the curator wrote, and the revision is the only place that difference survives:
    both are Tier C commentary, so the tier cannot carry it."""
    curation = doc.get("curation") or {}
    drafted = str(curation.get("drafted_by") or "").strip()
    if not drafted:
        return "人工策展：定义与用法出自讲解视频旁白，衍生时间来自平台元数据（%s）" % name
    return (
        "模型起草、人工审定：定义与用法由 %s 依据讲解视频画面字幕 OCR 起草，%s 审定；"
        "衍生时间来自平台元数据（%s）" % (drafted, str(curation.get("confirmed_by")).strip(), name)
    )


def unconfirmed_draft(doc: dict) -> bool:
    curation = doc.get("curation") or {}
    return bool(str(curation.get("drafted_by") or "").strip()) and not str(
        curation.get("confirmed_by") or ""
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--pace", type=float, default=1.1)
    parser.add_argument(
        "records", nargs="*", type=Path,
        help="load only these files; default is every record, and each run revises every meme it loads",
    )
    args = parser.parse_args()

    index = load_material_index()
    platform = load_platform_index()
    loader = Loader(args.api, args.dry_run, args.pace)
    episodes: set[str] = set()
    tiered: set[str] = set()
    failures = 0

    paths = sorted(p.resolve() for p in args.records) or [
        p for p in sorted(CURATION.glob("*.yaml")) if not p.name.startswith("_")
    ]
    docs = {path: yaml.safe_load(path.read_text(encoding="utf-8")) for path in paths}

    for path in order_by_dependency(paths, docs):
        raw = path.read_text(encoding="utf-8")
        doc = docs[path]
        name = doc["canonical_name"]
        print("\n=== %s  (%s) ===" % (name, path.name))
        if unconfirmed_draft(doc):
            # Checked before anything is posted, so a refused record leaves no evidence behind.
            print("  x 模型起草的记录尚未人工审定（curation.confirmed_by 为空），跳过")
            failures += 1
            continue

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
            revision = loader.publish(draft, every_id, name, approval_reason(doc, name))
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

    if loader.duplicates:
        print("\n! 同名的已发布梗，只用了最早的一条；其余是历次重跑留下的副本：")
        for name, ids in sorted(loader.duplicates.items()):
            print("  %s：%s" % (name, "、".join(x[:8] for x in ids)))
        print("  清理需要人工决定：POST /v1/reviews/memes/<id>/retract，本脚本不代劳。")
    print("\n完成，%d 处失败。" % failures)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
