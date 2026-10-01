#!/usr/bin/env python3
"""Turn an episode's OCR dump into the Material payloads load_curation.py posts.

    python evals/feasibility/build_materials.py BV1ii4C6QEk8 --meme 闹吃VS古振兴

Material 0 is the whole episode's on-screen text in time order, each distinct
string kept only the first time it appears - a line held on screen for thirty
frames is one observation, not thirty - with the channel's own furniture dropped, and
short lines kept only if they persist across frames: OCR's fragments of a split box
flicker for one frame, real subtitles stay up. Material N is the single frame in
which a cited work's BV id appeared, kept raw, because that frame is the evidence
an event or relation points at and trimming it would trim the id's context.

One file per episode, not per meme: an episode can cover several memes, and the
loader picks the frame it needs by the BV id in the locator note.

When <EP>.boxes.json exists (prep.py boxes / derivatives keep text positions), material 0
is instead only the narrator's subtitle row, and material 1 (ocr-screen-<EP>) is every
other text on screen: the quoted clip's captions, comments, credits. Position is measured,
so "is this the explanation or the thing explained" stops being a judgement call.
Episodes published under the old layout keep it; --timeline writes the split as a
reading aid for any episode without touching evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent


def stamp(seconds: float) -> str:
    return "%05.1fs" % seconds


# The channel's watermark and its logo, on screen in almost every frame.
FURNITURE = re.compile(r"bilibili|bilisili|梗百科")
BV_ID = re.compile(r"BV[0-9A-Za-z]{10}")
# A box holding only digits and punctuation is a timer, a counter or a version.
COUNTER = re.compile(r"^[\d\s.:+=]+$")
# Below six characters OCR often returns fragments of a longer box it split. A flat
# floor also threw away real short lines - the meme's own name 松针大油边, the quote
# "但你会", the line "你走" - so a short line now survives if it persists: a fragment
# flickers for one frame, a subtitle stays up for several. Episodes already published
# were built with the flat floor and must not be rebuilt (see --force).
MIN_CHARS = 6
MIN_SHORT = 2
PERSIST_FRAMES = 2


def narration(frames: list[dict], episode: str) -> dict:
    persist = Counter(t.strip() for f in frames for t in set(f.get("text") or []))
    seen: set[str] = set()
    lines = []
    for frame in frames:
        for text in frame.get("text") or []:
            line = text.strip()
            if line in seen or len(line) < MIN_SHORT:
                continue
            if len(line) < MIN_CHARS and persist[line] < PERSIST_FRAMES:
                continue
            if FURNITURE.search(line) or COUNTER.match(line):
                continue
            seen.add(line)
            lines.append("%s %s" % (stamp(frame["at"]), line))
    return {
        "text": "\n".join(lines),
        "kind": "ocr",
        "locator": {"start_ms": 0, "note": "%s 画面内嵌字幕全文，RapidOCR 每秒取帧，短行须跨帧持续" % episode},
    }


# 梗百科 draws its narrator subtitle as one centred row near the bottom. Everything else -
# the quoted clip's own captions, comments, credits, the watermark - sits elsewhere, or on
# that row at a different size. The row is measured per episode, not fixed: it sat at
# 86.6% of the frame in BV1ii4C6QEk8 and BV1xWtJ6iEGs but 89.4% in BV1vQ8i6uEYf, while
# the 棋魂 dialogue there sat 3% lower. And a clip's own bottom subtitles can share the row
# exactly - 闹吃VS古振兴's rap lyrics sat at 86.5% - but in taller boxes (0.08-0.09 of the
# frame against the narrator's 0.053). Height is what separates them.
ROW_TOLERANCE = 0.012          # narrator boxes seen within 0.861-0.875 on a 0.866 row
HEIGHT_RANGE = (0.6, 1.45)     # x the row's median height: drops 0.016-tall UI text below,
                               # 0.08+ lyrics above, keeps Latin in quotes (0.074 on 0.053)


def narrator_row(frames: list[dict]) -> tuple[float, float] | None:
    """(row centre, median box height) of the episode's narrator subtitle, or None.

    The narrator's line is the most common centred text row in the lower quarter."""
    candidates = [
        (b[1], b[4]) for f in frames for b in f["boxes"]
        if 0.75 <= b[1] <= 0.98 and 0.035 <= b[4] <= 0.08
        and abs((b[2] + b[3]) / 2 - 0.5) < 0.05 and len(str(b[0])) >= 4
    ]
    if len(candidates) < 10:
        return None
    rows = Counter(round(y * 200) for y, _ in candidates)       # 0.5% buckets
    peak = rows.most_common(1)[0][0] / 200
    near = sorted(y for y, _ in candidates if abs(y - peak) <= 0.005)
    centre = near[len(near) // 2]
    heights = sorted(h for y, h in candidates if abs(y - centre) <= ROW_TOLERANCE)
    return centre, heights[len(heights) // 2]


def split_frame(boxes: list[list], row: tuple[float, float] | None) -> tuple[str, list[str]]:
    """One frame's boxes -> (the narrator's line, every other text on screen).

    The narrator's line is often split into several boxes ("就像什么" + "“神不会流血"), so
    its boxes are joined left to right into one line."""
    if row is None:
        return "", [str(b[0]).strip() for b in boxes]
    centre, height = row
    band = sorted(
        (b for b in boxes if abs(b[1] - centre) <= ROW_TOLERANCE
         and HEIGHT_RANGE[0] * height <= b[4] <= HEIGHT_RANGE[1] * height),
        key=lambda b: b[2],
    )
    narrator = "".join(str(b[0]).strip() for b in band)
    others = [str(b[0]).strip() for b in boxes if b not in band]
    return narrator, others


def narration_by_position(frames: list[dict], episode: str) -> tuple[dict, dict]:
    """Two materials from positioned OCR: what the narrator said, and what else was shown.

    The narrator's lines are kept whenever they change - position has already said what
    they are, so no length floor. Other text keeps the persistence rule, and each distinct
    string once. Both carry their second, so a quote can be placed beside its explanation."""
    said, shown = [], []
    last, seen = "", set()
    persist = Counter(t for f in frames for t in {str(b[0]).strip() for b in f["boxes"]})
    row = narrator_row(frames)
    for frame in frames:
        narrator, others = split_frame(frame["boxes"], row)
        # A line held on screen re-reads with a dropped character now and then (屡见不鲜 /
        # 见不鲜); one near-identical to the line just kept is the same line, not a new one.
        if (narrator and not FURNITURE.search(narrator)
                and SequenceMatcher(None, narrator, last).ratio() < 0.85):
            said.append("%s %s" % (stamp(frame["at"]), narrator))
            last = narrator
        for line in others:
            # A line carrying a BV id is evidence even when it also says bilibili: a pasted
            # link "https://www.bilibili.com/video/BV1oWMH6yE9s/..." was being dropped as
            # watermark, and with it the only on-screen mention of that id.
            furniture = FURNITURE.search(line) and not BV_ID.search(line)
            if line in seen or len(line) < MIN_SHORT or furniture or COUNTER.match(line):
                continue
            if len(line) < MIN_CHARS and persist[line] < PERSIST_FRAMES:
                continue
            seen.add(line)
            shown.append("%s %s" % (stamp(frame["at"]), line))
    where = ("解说字幕行位于画面 %.1f%% 高度，框高 %.3f" % (row[0] * 100, row[1])) if row else "未检出解说字幕行"
    note = "%s 画面底部解说字幕（按画面位置与字高识别；%s），RapidOCR 每秒取帧"
    return (
        {"text": "\n".join(said), "kind": "ocr",
         "locator": {"start_ms": 0, "note": note % (episode, where)}},
        {"text": "\n".join(shown), "kind": "ocr",
         "locator": {"start_ms": 0, "note": "%s 画面其他文字：引用视频的字幕、评论、署名等，解说字幕除外" % episode}},
    )


def timeline(frames: list[dict]) -> list[str]:
    """A reading aid, not evidence: both streams interleaved by second and labelled, so a
    quote sits beside the sentence that explains it. Same filters as the two materials."""
    said, shown = narration_by_position(frames, "")
    tagged = [(line[:6], "解说", line[7:]) for line in said["text"].splitlines()]
    tagged += [(line[:6], "画面", line[7:]) for line in shown["text"].splitlines()]
    order = {"解说": 0, "画面": 1}
    return ["%s %s｜%s" % item for item in sorted(tagged, key=lambda t: (t[0], order[t[1]]))]


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
    parser.add_argument(
        "--timeline", type=Path, metavar="FILE",
        help="只写出解说/画面交错的阅读稿到 FILE，不生成、不改动任何证据文件；已发布的剧集也可用",
    )
    args = parser.parse_args()
    if args.timeline:
        positioned = HERE / ("%s.boxes.json" % args.episode)
        if not positioned.exists():
            print("没有 %s，先运行 prep.py boxes %s" % (positioned.name, args.episode))
            return 2
        lines = timeline(json.loads(positioned.read_text(encoding="utf-8"))["frames"])
        args.timeline.parent.mkdir(parents=True, exist_ok=True)
        args.timeline.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("-> %s  %d 行" % (args.timeline, len(lines)))
        return 0

    episode = args.episode
    frames = json.loads((HERE / ("%s.ocr.json" % episode)).read_text(encoding="utf-8"))
    positioned = HERE / ("%s.boxes.json" % episode)
    if positioned.exists():
        # Material 0 stays the narration, which is what ocr-narration-<EP> resolves to;
        # material 1 is ocr-screen-<EP>. Citations follow.
        materials = list(narration_by_position(
            json.loads(positioned.read_text(encoding="utf-8"))["frames"], episode))
    else:
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
    print("-> %s   %s + 引用 %d 条" % (target.name, "解说 + 画面其他文字" if positioned.exists() else "旁白 1 条",
                                         len(materials) - (2 if positioned.exists() else 1)))
    if missing:
        print("   ! 没找到对应帧：%s" % ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
