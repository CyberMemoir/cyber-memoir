#!/usr/bin/env python3
"""Alias proposals: build blind reading packets, check proposals, apply what the curator keeps.

    python evals/feasibility/alias_packets.py build              # -> ai_context/alias_packets/
    python evals/feasibility/alias_packets.py check-screen ai_context/aliases_from_screen.csv
    python evals/feasibility/alias_packets.py check-guessed ai_context/aliases_guessed.csv
    python evals/feasibility/alias_packets.py apply <kept.csv> [<kept.csv> ...]

The 2026-09-20 baseline found every missed description query was a vocabulary gap, and
23 of 26 memes had no alias at all. A model can read the episodes' OCR, which the curator
has not memorised, so it proposes. Two kinds, kept apart because they are different
claims:

  from the screen   an alternative name that appears verbatim in the episode's OCR, cited
                    by second and line. Checked mechanically: the line must be on screen
                    at that second and the alias must be inside it.
  guessed           how a reader might plausibly search. Not evidence of anything, so the
                    curator keeps one only if it is genuinely another name for the meme -
                    an alias is published as fact, as 也叫 X.

WHY THE PACKETS EXIST. The curation YAMLs hold gold.description, the name-free queries
that are the test this work will be measured by. A model that can read them will propose
aliases that match them, innocently or not, and recall will rise without meaning anything.
So the model reads packets built from the YAMLs with every gold field left out, and the
check commands never consult the gold set or the negatives, so their messages cannot leak
them either. The collision audit against the gold set is the curator's, at apply time.

ASR is included for meaning only. It mishears names - the one transcript here opens with
松珍大油煸 for 松针大油边 - so a name heard in the transcript and not seen on screen is a
mishearing until proven otherwise, and can only ever be a guess.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

import yaml

from build_materials import timeline

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CURATION = ROOT / "evals" / "curation"
PACKETS = ROOT / "ai_context" / "alias_packets"
AT_TOLERANCE = 2.0  # seconds either side of `at` in which the cited line must appear


def flat(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", str(text)).split()).lower()


def records() -> dict[str, tuple[Path, dict]]:
    out = {}
    for path in sorted(CURATION.glob("*.y*ml")):
        if path.name.startswith("_"):
            continue
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("canonical_name"):
            out[str(data["canonical_name"])] = (path, data)
    return out


def episodes(data: dict) -> tuple[list[str], list[str]]:
    keys = list((data.get("evidence_map") or {}).keys())
    ocr = [k[len("ocr-narration-"):] for k in keys if k.startswith("ocr-narration-")]
    asr = [k[len("asr-"):] for k in keys if k.startswith("asr-")]
    return ocr, asr


def screen(episode: str) -> list[tuple[float, str, str]]:
    boxes = HERE / ("%s.boxes.json" % episode)
    if not boxes.exists():
        return []
    frames = json.loads(boxes.read_text(encoding="utf-8"))["frames"]
    out = []
    for line in timeline(frames):
        second, rest = line.split("s ", 1)
        kind, text = rest.split("｜", 1)
        out.append((float(second), kind, text))
    return out


def transcript(episode: str) -> list[str]:
    path = HERE / ("%s.transcript.txt" % episode)
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def segment(name: str, episode: str) -> str:
    """Where this meme's cited ids appeared, so a multi-meme episode's reader knows which
    stretch is theirs. Mechanical, from lineage.csv and the episode's seen_at column."""
    lineage = HERE / "lineage.csv"
    derivs = HERE / ("%s.derivatives.csv" % episode)
    if not (lineage.exists() and derivs.exists()):
        return ""
    ids = {r["bv_id"].lower() for r in csv.DictReader(lineage.open(encoding="utf-8-sig"))
           if r["episode_id"] == episode and name in (r["meme_name"] or "").split("&")}
    seen = [float(r["seen_at"]) for r in csv.DictReader(derivs.open(encoding="utf-8-sig"))
            if r["bv_id"].lower() in ids and r.get("seen_at")]
    return "%.0fs .. %.0fs" % (min(seen), max(seen)) if seen else ""


def build(_args) -> int:
    PACKETS.mkdir(parents=True, exist_ok=True)
    for old in PACKETS.glob("*.txt"):
        old.unlink()
    index = []
    for name, (path, data) in records().items():
        ocr, asr = episodes(data)
        lines = [
            "梗名        %s" % name,
            "已有别名    %s" % ("、".join(map(str, data.get("aliases") or [])) or "（无）"),
            "定义        %s" % str(data.get("definition") or "").strip(),
            "用法        %s" % str(data.get("usage_context") or "").strip(),
            "",
        ]
        for episode in ocr:
            span = segment(name, episode)
            lines += ["=" * 70,
                      "画面 OCR  %s%s" % (episode, ("   本梗引用出现在 %s" % span) if span else ""),
                      "（一集可能讲好几个梗；只为本梗提别名）", "=" * 70]
            lines += ["%05.1fs %s｜%s" % item for item in screen(episode)]
            lines.append("")
        for episode in asr:
            lines += ["=" * 70, "语音转写 ASR  %s   只能读意思，名字常听错，不能作为画面别名的依据" % episode,
                      "=" * 70]
            lines += transcript(episode)
            lines.append("")
        (PACKETS / ("%s.txt" % path.stem)).write_text("\n".join(lines) + "\n", encoding="utf-8")
        index.append("%-24s %s" % (path.stem + ".txt", name))
    (PACKETS / "_index.txt").write_text("\n".join(index) + "\n", encoding="utf-8")
    print("-> %s   %d 个梗" % (PACKETS, len(index)))
    return 0


def _common(row: dict, known: dict, taken: dict) -> list[str]:
    problems = []
    name, alias = (row.get("meme") or "").strip(), (row.get("alias") or "").strip()
    if name not in known:
        problems.append("梗名《%s》不在库里（照 _index.txt 抄）" % name)
        return problems
    if not alias:
        problems.append("别名为空")
        return problems
    _, data = known[name]
    if flat(alias) == flat(name):
        problems.append("和梗名本身相同")
    if flat(alias) in {flat(a) for a in data.get("aliases") or []}:
        problems.append("已经是现有别名")
    other = taken.get(flat(alias))
    if other and other != name:
        problems.append("已是《%s》的名字或别名；同一个词不能指向两个梗" % other)
    return problems


def _taken(known: dict) -> dict[str, str]:
    taken = {}
    for name, (_, data) in known.items():
        for n in [name, *(data.get("aliases") or [])]:
            taken[flat(n)] = name
    return taken


def check_screen(args) -> int:
    known = records()
    taken = _taken(known)
    rows = list(csv.DictReader(Path(args.file).open(encoding="utf-8-sig")))
    refused = 0
    for number, row in enumerate(rows, 2):
        problems = _common(row, known, taken)
        if not problems:
            name, alias = row["meme"].strip(), row["alias"].strip()
            episode, line = (row.get("episode_id") or "").strip(), row.get("line") or ""
            ocr, _ = episodes(known[name][1])
            if episode not in ocr:
                problems.append("%s 不是《%s》的画面 OCR 来源（可用：%s）" % (episode, name, "、".join(ocr) or "无"))
            elif flat(alias) not in flat(line):
                problems.append("别名不在所引的那一行里")
            else:
                try:
                    at = float(row.get("at") or "")
                except ValueError:
                    at = None
                hits = [s for s, _, text in screen(episode) if flat(text) == flat(line)]
                if not hits:
                    problems.append("这一行在画面 OCR 里逐字对不上：%s" % line[:30])
                elif at is None or not any(abs(s - at) <= AT_TOLERANCE for s in hits):
                    problems.append("这一行出现在 %s，不在所写的 %s"
                                    % ("/".join("%.0fs" % s for s in hits), row.get("at")))
        if problems:
            refused += 1
            print("第 %d 行  %s → %s" % (number, row.get("meme"), row.get("alias")))
            for problem in problems:
                print("    - %s" % problem)
    print("%d 条画面别名，%d 条被拒" % (len(rows), refused))
    return 1 if refused else 0


def check_guessed(args) -> int:
    known = records()
    taken = _taken(known)
    rows = list(csv.DictReader(Path(args.file).open(encoding="utf-8-sig")))
    refused = 0
    for number, row in enumerate(rows, 2):
        problems = _common(row, known, taken)
        if not (row.get("why") or "").strip():
            problems.append("没写理由")
        if problems:
            refused += 1
            print("第 %d 行  %s → %s" % (number, row.get("meme"), row.get("alias")))
            for problem in problems:
                print("    - %s" % problem)
    print("%d 条猜测别名，%d 条被拒" % (len(rows), refused))
    return 1 if refused else 0


def apply(args) -> int:
    """Write the aliases the curator kept into the records' `aliases:` line.

    Run by the curator after deleting the rows he rejects. Refuses an alias that is a
    gold query or a negative, because that would turn a test case into its own answer -
    this is the one place the gold set is consulted, and it is the curator's command."""
    known = records()
    taken = _taken(known)
    gold, negatives = set(), set()
    for name, (_, data) in known.items():
        for bucket, queries in (data.get("gold") or {}).items():
            if bucket != "must_not_return":
                gold.update(flat(q) for q in queries or [])
    neg_path = CURATION / "_negatives.yaml"
    if neg_path.exists():
        doc = yaml.safe_load(neg_path.read_text(encoding="utf-8")) or []
        rows = doc if isinstance(doc, list) else (doc.get("negatives") or doc.get("cases") or [])
        negatives = {flat(r.get("query") or "") for r in rows}
    wanted: dict[str, list[str]] = {}
    refused = 0
    for file in args.files:
        for row in csv.DictReader(Path(file).open(encoding="utf-8-sig")):
            problems = _common(row, known, taken)
            alias = (row.get("alias") or "").strip()
            if flat(alias) in negatives:
                problems.append("是一条反例查询；加成别名会让本该弃答的问题有了答案")
            elif flat(alias) in gold:
                problems.append("和一条金标准查询一字不差；加成别名等于把答案写进考题")
            if problems:
                refused += 1
                print("  x %s → %s：%s" % (row.get("meme"), alias, "；".join(problems)))
                continue
            wanted.setdefault(row["meme"].strip(), [])
            if alias not in wanted[row["meme"].strip()]:
                wanted[row["meme"].strip()].append(alias)
    for name, aliases in wanted.items():
        path, data = known[name]
        merged = list(map(str, data.get("aliases") or [])) + aliases
        text = path.read_text(encoding="utf-8")
        line = "aliases: [%s]" % ", ".join(json.dumps(a, ensure_ascii=False) for a in merged)
        new, count = re.subn(r"^aliases:.*$", lambda _: line, text, count=1, flags=re.M)
        if not count:
            print("  ! %s 没有 aliases 行，没有写入" % path.name)
            continue
        path.write_text(new, encoding="utf-8")
        print("  %-24s + %s" % (path.name, "、".join(aliases)))
    print("写入 %d 个记录，拒绝 %d 条" % (len(wanted), refused))
    if wanted:
        print("然后：validate_curation.py，再用 load_curation.py 只加载改过的这些文件")
    return 1 if refused else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("build").set_defaults(run=build)
    s = sub.add_parser("check-screen")
    s.add_argument("file")
    s.set_defaults(run=check_screen)
    g = sub.add_parser("check-guessed")
    g.add_argument("file")
    g.set_defaults(run=check_guessed)
    a = sub.add_parser("apply")
    a.add_argument("files", nargs="+")
    a.set_defaults(run=apply)
    args = parser.parse_args()
    return args.run(args)


if __name__ == "__main__":
    sys.exit(main())
