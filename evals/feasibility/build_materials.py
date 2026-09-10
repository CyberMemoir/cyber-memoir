#!/usr/bin/env python3
"""Turn an episode's OCR dump into the Material payloads load_curation.py posts.

    python evals/feasibility/build_materials.py BV1ii4C6QEk8 --meme 闹吃VS古振兴

Material 0 is the whole episode's on-screen text in time order, each distinct
string kept only the first time it appears - a line held on screen for thirty
frames is one observation, not thirty - with the channel's own furniture and the
sub-six-character fragments OCR invents dropped. Material N is the single frame in
which a cited work's BV id appeared, kept raw, because that frame is the evidence
an event or relation points at and trimming it would trim the id's context.

One file per episode, not per meme: an episode can cover several memes, and the
loader picks the frame it needs by the BV id in the locator note.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent


def stamp(seconds: float) -> str:
    return "%05.1fs" % seconds


# The channel's watermark and its logo, on screen in almost every frame.
FURNITURE = re.compile(r"bilibili|bilisili|梗百科")
# A box holding only digits and punctuation is a timer, a counter or a version.
COUNTER = re.compile(r"^[\d\s.:+=]+$")
# Below six characters OCR mostly returns fragments of a longer box it split.
MIN_CHARS = 6


def narration(frames: list[dict], episode: str) -> dict:
    seen: set[str] = set()
    lines = []
    for frame in frames:
        for text in frame.get("text") or []:
            line = text.strip()
            if len(line) < MIN_CHARS or line in seen:
                continue
            if FURNITURE.search(line) or COUNTER.match(line):
                continue
            seen.add(line)
            lines.append("%s %s" % (stamp(frame["at"]), line))
    return {
        "text": "\n".join(lines),
        "kind": "ocr",
        "locator": {"start_ms": 0, "note": "%s 画面内嵌字幕全文，RapidOCR 每秒取帧" % episode},
    }


def citation(frames: list[dict], episode: str, bv: str, at: float) -> dict | None:
    for frame in frames:
        if abs(frame["at"] - at) < 0.01:
            return {
                # One line, boxes in reading order: the frame is a single glance,
                # not a transcript, and the id is only legible beside its caption.
                "text": " | ".join(frame.get("text") or []),
                "kind": "ocr",
                "locator": {
                    "start_ms": int(at * 1000),
                    "note": "%s 第 %d 秒画面出现 %s" % (episode, int(at), bv),
                },
            }
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("episode")
    parser.add_argument("--meme", default="")
    parser.add_argument(
        "--force",
        action="store_true",
        help="重建已存在的文件；证据按内容哈希去重，改动会生成第二条 Evidence，"
             "已发布的剧集不要重建",
    )
    args = parser.parse_args()

    episode = args.episode
    frames = json.loads((HERE / ("%s.ocr.json" % episode)).read_text(encoding="utf-8"))
    materials = [narration(frames, episode)]

    missing = []
    with (HERE / ("%s.derivatives.csv" % episode)).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            found = citation(frames, episode, row["bv_id"], float(row["seen_at"]))
            if found:
                materials.append(found)
            else:
                missing.append(row["bv_id"])

    target = HERE / "materials" / ("%s.materials.json" % episode)
    if target.exists() and not args.force:
        print("已存在 %s，未改动（--force 可重建）" % target.name)
        return 0
    target.parent.mkdir(exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "source_url": "https://www.bilibili.com/video/%s" % episode,
                "meme": args.meme,
                "materials": materials,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("-> %s   旁白 1 条 + 引用 %d 条" % (target.name, len(materials) - 1))
    if missing:
        print("   ! 没找到对应帧：%s" % ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
