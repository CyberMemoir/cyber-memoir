#!/usr/bin/env python3
"""Find same-named published memes and retract the copies you do not want.

    python evals/dedupe_memes.py report          # -> evals/curation/_keep.csv
    # edit the keep column by hand
    python evals/dedupe_memes.py retract

Every rerun of load_curation.py published a fresh meme, because /v1/reviews/drafts
creates one unless handed a meme_id, so the archive holds several copies of most
records. The copies are not identical - later runs carry evidence earlier runs had
no builder for - so which one survives is a real choice and this script does not
make it. It lays the copies side by side, marks the one the stated rule would pick,
and leaves the keep column for you to change.

Retracting is reversible in the sense that matters: status becomes retracted and a
Revision records who did it and why. Nothing is deleted.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import httpx
import yaml

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "evals" / "curation"
SHEET = CURATION / "_keep.csv"
FIELDS = [
    "canonical_name", "meme_id", "published_revision", "created_at",
    "evidence", "claims", "events", "relations", "keep",
]


def token() -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("REVIEWER_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("在 .env 里找不到 REVIEWER_TOKEN")


def names() -> list[str]:
    found = []
    for path in sorted(CURATION.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        found.append(doc["canonical_name"])
    return found


def rank(row: dict) -> tuple:
    """The rule the report applies, written down so a reader can disagree with it.

    Most evidence first, because a copy citing more of the episode is the more
    complete record. Then the most events and relations, for the same reason. Then
    the newest revision. Ties break toward the oldest copy, which is the one any
    link written so far already points at.
    """
    return (
        int(row["evidence"]),
        int(row["events"]) + int(row["relations"]),
        int(row["published_revision"]),
        row["created_at"],
    )


def report(client: httpx.Client) -> int:
    rows: list[dict] = []
    for name in names():
        found = client.get("/v1/memes", params={"name": name})
        found.raise_for_status()
        copies = found.json()
        group = []
        for ref in copies:
            detail = client.get("/v1/memes/%s" % ref["id"])
            detail.raise_for_status()
            body = detail.json()
            group.append({
                "canonical_name": name,
                "meme_id": ref["id"],
                "published_revision": ref["published_revision"],
                "created_at": ref["created_at"],
                "evidence": len(body.get("evidence") or []),
                "claims": len(body.get("claims") or []),
                "events": len(body.get("events") or []),
                "relations": len(body.get("relations") or []),
                "keep": "",
            })
        if not group:
            print("  ! 《%s》没有已发布的副本" % name)
            continue
        best = max(group, key=rank)
        best["keep"] = "y"
        rows.extend(sorted(group, key=lambda r: r["created_at"]))
        mark = "" if len(group) == 1 else "  ← %d 个副本" % len(group)
        print("%-14s %d 个已发布%s" % (name, len(group), mark))

    with SHEET.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    extra = sum(1 for r in rows if not r["keep"])
    print("\n-> %s   %d 行，标记保留 %d 行，待撤回 %d 行"
          % (SHEET.name, len(rows), len(rows) - extra, extra))
    print("规则：证据最多 > 事件与关系最多 > 修订号最大 > 创建最早。改 keep 列即可推翻。")
    return 0


def retract(client: httpx.Client, reason: str, dry: bool) -> int:
    if not SHEET.exists():
        raise SystemExit("先跑 report 生成 %s" % SHEET.name)
    with SHEET.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["canonical_name"], []).append(row)

    problems = []
    for name, group in groups.items():
        kept = [r for r in group if r["keep"].strip().lower() in {"y", "yes", "1"}]
        if len(kept) != 1:
            problems.append("《%s》标记保留 %d 行，必须恰好 1 行" % (name, len(kept)))
    if problems:
        for line in problems:
            print("x %s" % line)
        return 1

    doomed = [r for r in rows if r["keep"].strip().lower() not in {"y", "yes", "1"}]
    print("将撤回 %d 条，保留 %d 条。" % (len(doomed), len(rows) - len(doomed)))
    failed = 0
    for row in doomed:
        if dry:
            print("  (dry) %s  %s" % (row["canonical_name"], row["meme_id"][:8]))
            continue
        # The API caps POST/PUT at 60 per minute per client IP.
        time.sleep(1.1)
        try:
            client.post(
                "/v1/reviews/memes/%s/retract" % row["meme_id"], json={"reason": reason}
            ).raise_for_status()
            print("  已撤回 %s  %s" % (row["canonical_name"], row["meme_id"][:8]))
        except httpx.HTTPStatusError as exc:
            print("  x %s %s: %s"
                  % (row["canonical_name"], exc.response.status_code, exc.response.text[:120]))
            failed += 1
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["report", "retract"])
    parser.add_argument("--api", default="http://localhost:8100")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--reason",
        default="重复条目：同一策展记录被多次发布，保留内容最完整的一条，其余撤回",
    )
    args = parser.parse_args()

    client = httpx.Client(
        base_url=args.api,
        timeout=60,
        trust_env=False,
        headers={"Authorization": "Bearer %s" % token()},
    )
    if args.mode == "report":
        return report(client)
    return retract(client, args.reason, args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
