#!/usr/bin/env python3
"""Find the sentences in which an episode says where a meme came from.

    python evals/feasibility/origin_cues.py BV1ysME67Em9 BV1G6tm6bEBT -o sheet.txt

Asking a model "what role does this cited video play" 117 times failed all three
criteria of evals/results-2026-09-19-roles.md: 4 of 23 origins found, because it judged
a clip by where it sat in the narration rather than by what the narration said the clip
was. The measurement that followed says the question was the wrong shape.

An episode states an origin in one or two sentences. Across the 21 calibration episodes
there are 32 such sentences - 1.5 an episode - against 117 cited ids. So this looks for
the sentences, not the ids, and hangs the ids on them. What is left over is derivative
by default, and nobody has to judge it.

WHAT THE NUMBERS ARE, AND WHAT THEY ARE NOT
  CUES was written by reading the 21 calibration episodes, and the window was fitted to
  the same 117 rows, so `22 of the 25 origins inside a 50-row shortlist of 117` is a
  description of that data and not a prediction. Both are frozen here so the next batch is an honest
  test: criteria go in evals/results-*.md before it runs.

  All 3 origins it misses are unreachable rather than missed: 2 are in episodes with
  no cue sentence at all - the episode never says where the meme came from - and 1 was
  never on screen (the curator added it by hand). 5 of 21 episodes have no cue
  sentence, and their citations are all derivative by default. Ids are joined
  case-insensitively: counting them exactly hid one origin that was on the shortlist
  under the spelling the OCR read.

  源头 and 火了 were added to CUES after they were seen to be missing - 源头呢不是他自己
  跳的 and 最近一种配音视频模板就火了 are origin sentences the first list walked past.
  That is one more turn of fitting on data already spent, and the reason the criteria
  for the real test are frozen in evals/results-2026-09-19-roles.md before it runs.

  The id lands AFTER the sentence: the narrator names the origin, then cuts to the clip
  with its BV id burned on. Hence the window is forward-biased rather than centred, which
  the curator confirmed from watching and the offsets bear out (median +11s, from -20 to
  +41 excluding one outlier at -108). An origin on Twitter or elsewhere off-platform
  appears as a screenshot with no id at all and can never produce a row here: ADR 0003.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import unicodedata
from pathlib import Path

from build_materials import timeline

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent

# Words that introduce an origin sentence. Read the sentence, never the word: 出处 also
# appears in 搜索右上角出处支持原作者, a watermark the channel puts on borrowed clips.
CUES = [
    "出处", "出自", "最早", "最初", "原版", "原视频", "原画面", "追溯", "源于",
    "源头", "来源", "来自", "火起来", "火了", "爆火", "走红", "带火", "红了", "兴起",
]
BACK, FORWARD = 20.0, 45.0  # seconds either side of the sentence
CONTEXT = 8.0  # narration either side of the sentence, for reading


def read_timeline(episode: str) -> list[tuple[float, str, str]]:
    """(second, 解说|画面, text) for one episode, from its positioned OCR."""
    boxes = HERE / ("%s.boxes.json" % episode)
    if not boxes.exists():
        raise SystemExit(
            "%s has no .boxes.json - the narrator's row is found by position, so an "
            "episode OCR'd without it cannot be read this way (prep.py boxes)" % episode
        )
    frames = json.loads(boxes.read_text(encoding="utf-8"))["frames"]
    out = []
    for line in timeline(frames):
        second, rest = line.split("s ", 1)
        kind, text = rest.split("｜", 1)
        out.append((float(second), kind, text))
    return out


def cited(episode: str) -> list[dict]:
    """The episode's cited works, with the second each id appeared."""
    path = HERE / ("%s.derivatives.csv" % episode)
    if not path.exists():
        return []
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    for row in rows:
        row["seen_at"] = float(row["seen_at"]) if row.get("seen_at") else None
    return [row for row in rows if row["seen_at"] is not None]


def memes(episode: str) -> dict[str, str]:
    """bv_id -> the meme the curator filed it under, where the sheet already says."""
    path = HERE / "lineage.csv"
    if not path.exists():
        return {}
    # Keyed lower-case: the same id is OCR'd in more than one case (BV1XyJA6BEBN on
    # screen for BV1xyJA6BEBN), and an exact join silently files the variant under no
    # meme at all. Searching the screen case-sensitively already cost 大狗叫 a true
    # relation once; see CLAUDE.md.
    return {
        row["bv_id"].lower(): row["meme_name"]
        for row in csv.DictReader(path.open(encoding="utf-8-sig"))
        if row["episode_id"] == episode
    }


def sheet(episode: str) -> tuple[list[str], list[dict]]:
    lines = read_timeline(episode)
    works = cited(episode)
    filed = memes(episode)
    cues = [
        (second, text)
        for second, kind, text in lines
        if kind == "解说" and any(cue in text for cue in CUES)
    ]
    out = ["=" * 78, "EPISODE %s   %d 条引用，%d 句可能的出处解说" % (episode, len(works), len(cues))]
    if not cues:
        out += ["", "  这一集没有出处解说。所有引用一律 derivative，除非策展人另有判断。"]
    shortlist = []
    for second, text in cues:
        out += ["", "-" * 78, "解说 %05.1fs  %s" % (second, text), ""]
        for near, kind, other in lines:
            if kind == "解说" and second - CONTEXT <= near <= second + CONTEXT and near != second:
                out.append("    %05.1fs %s" % (near, other))
        window = [w for w in works if -BACK <= w["seen_at"] - second <= FORWARD]
        out += ["", "  这句话前 %ds 后 %ds 出现的引用：" % (BACK, FORWARD)]
        if not window:
            out.append("    （没有。这句话没有对应的 BV 号——出处可能在站外，见 ADR 0003）")
        for work in window:
            out.append(
                "    %s  %+5.0fs  %s  %s"
                % (work["bv_id"], work["seen_at"] - second,
                   work.get("upload_date") or "无日期", (work.get("title") or "")[:46])
            )
            shortlist.append({
                "episode_id": episode, "bv_id": work["bv_id"],
                "meme_name": filed.get(work["bv_id"].lower(), ""),
                "cue_at": "%.1f" % second, "cue": text,
                "seen_at": "%.1f" % work["seen_at"],
                "offset": "%+.0f" % (work["seen_at"] - second),
                "upload_date": work.get("upload_date") or "",
                "title": work.get("title") or "",
            })
    picked = {row["bv_id"] for row in shortlist}
    rest = [w for w in works if w["bv_id"] not in picked]
    out += ["", "-" * 78,
            "  另外 %d 条引用不在任何出处解说附近，默认 derivative：" % len(rest)]
    for work in rest:
        out.append("    %s  %05.1fs  %s  %s"
                   % (work["bv_id"], work["seen_at"], work.get("upload_date") or "无日期",
                      (work.get("title") or "")[:46]))
    return out, shortlist


ROLES = {"source", "popularized_by"}


def flat(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).split())


def check(path: Path) -> int:
    """Refuse a proposed origin that the screen does not support.

    The same discipline the drafted definitions get: the claim names the sentence it
    rests on, and the sentence is looked up rather than believed. A model that cannot
    quote a real 解说 line for an origin has not found one. Constants live above, so
    the check and the sheet cannot drift apart the way validate_curation.py and
    content.py's review() already did once.
    """
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    cache: dict[str, list[tuple[float, str, str]]] = {}
    works: dict[str, list[dict]] = {}
    refused = 0
    for number, row in enumerate(rows, 2):
        episode, bv = row["episode_id"], row["bv_id"]
        problems = []
        if row.get("role") not in ROLES:
            problems.append("role 必须是 source 或 popularized_by，不是 %r" % row.get("role"))
        lines = cache.setdefault(episode, read_timeline(episode))
        cited_here = works.setdefault(episode, cited(episode))
        quoted = flat(row.get("cue") or "")
        said = [
            (second, text) for second, kind, text in lines
            if kind == "解说" and flat(text) == quoted
        ]
        if not quoted:
            problems.append("没有引用解说原文")
        elif not said:
            problems.append("解说里没有这句话，逐字对不上：%s" % (row.get("cue") or "")[:30])
        elif not any(cue in row["cue"] for cue in CUES):
            problems.append("这句话没有出处措辞（%s 之类），它没有说梗从哪来" % "、".join(CUES[:4]))
        else:
            at = min(said, key=lambda pair: abs(pair[0] - float(row["cue_at"] or 0)))[0]
            seen = [w for w in cited_here if w["bv_id"].lower() == bv.lower()]
            if not seen:
                problems.append("%s 不在这一集的引用里" % bv)
            elif not any(-BACK <= w["seen_at"] - at <= FORWARD for w in seen):
                problems.append(
                    "%s 出现在 %s，不在这句话（%.1fs）的 -%ds/+%ds 窗口内"
                    % (bv, "/".join("%.0fs" % w["seen_at"] for w in seen), at, BACK, FORWARD))
        if problems:
            refused += 1
            print("第 %d 行  %s %s" % (number, episode, bv))
            for problem in problems:
                print("    - %s" % problem)
    print("%d 条提案，%d 条被拒" % (len(rows), refused))
    return 1 if refused else 0


def apply(path: Path) -> int:
    """Write the confirmed origins into lineage.csv, and derivative for everything else.

    Run by the curator, never by the model, and only after he has been through
    origins.csv. It fills blank roles only: a role he has already written by hand is
    never overwritten, so running it twice is safe and so is running it after he has
    marked a few rows `irrelevant`.
    """
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    named = {(r["episode_id"], r["bv_id"].lower()): r["role"] for r in rows}
    episodes = {r["episode_id"] for r in rows}
    sheet_path = HERE / "lineage.csv"
    lineage = list(csv.DictReader(sheet_path.open(encoding="utf-8-sig")))
    fields = list(lineage[0].keys())
    origins = defaults = kept = 0
    for row in lineage:
        if row["episode_id"] not in episodes:
            continue
        if row["role"].strip():
            kept += 1
            continue
        role = named.get((row["episode_id"], row["bv_id"].lower()))
        row["role"] = role or "derivative"
        origins += bool(role)
        defaults += not role
    with sheet_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(lineage)
    print("lineage.csv：写入出处 %d 条，其余 %d 条记为 derivative，原有 %d 条未动"
          % (origins, defaults, kept))
    missing = sorted(set(named) - {(r["episode_id"], r["bv_id"].lower()) for r in lineage})
    for episode, bv in missing:
        print("  ! %s %s 不在 lineage.csv 里，没有写入" % (episode, bv))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("episodes", nargs="*")
    parser.add_argument("-o", "--out", type=Path,
                        help="阅读稿；同名 .csv 写出候选清单")
    parser.add_argument("--check", type=Path, metavar="FILE",
                        help="核对提案的 origins.csv：解说原文、措辞、窗口")
    parser.add_argument("--apply", type=Path, metavar="FILE",
                        help="把确认过的 origins.csv 写进 lineage.csv，其余记为 derivative")
    args = parser.parse_args()
    if args.check:
        return check(args.check)
    if args.apply:
        return apply(args.apply)
    if not (args.episodes and args.out):
        parser.error("要么 --check/--apply FILE，要么 <EP>... -o FILE")
    text: list[str] = []
    shortlist: list[dict] = []
    for episode in args.episodes:
        block, rows = sheet(episode)
        text += block + [""]
        shortlist += rows
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(text) + "\n", encoding="utf-8")
    table = args.out.with_suffix(".csv")
    with table.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "episode_id", "bv_id", "meme_name", "cue_at", "cue", "seen_at",
            "offset", "upload_date", "title"])
        writer.writeheader()
        writer.writerows(shortlist)
    distinct = len({(row["episode_id"], row["bv_id"]) for row in shortlist})
    print("-> %s   %d 集，%d 条引用进入候选（%d 个句子-引用配对）-> %s"
          % (args.out, len(args.episodes), distinct, len(shortlist), table.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
