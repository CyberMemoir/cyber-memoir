#!/usr/bin/env python3
"""Plumbing for the explainer-video feasibility test. Does no judging.

Three modes:

    python evals/feasibility/prep.py videos BV1xx BV1yy BV1zz
        Probes subtitle availability (the step-0 gate), then writes
        <BV>.transcript.txt with mm:ss timestamps and <BV>.meta.json.

    python evals/feasibility/prep.py cnmeme 鸡你太美 尊嘟假嘟
        Pulls the competitor's public entry for the same memes (Part B),
        into cnmeme/<name>.json.

    python evals/feasibility/prep.py summarize annotations.csv
        Computes the decision metrics from your hand annotations.

Output goes to the directory holding this script unless --out is given.
Subtitle extraction leans on yt-dlp's own srt conversion rather than
reimplementing the parser in apps/backend/.../ingestion/subtitles.py.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import time
import sys
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
CLAIM_TYPES = ("origin", "version", "fork", "mutation", "spread", "definition", "usage")
# Written down before the test so the result cannot be rationalised afterwards.
THRESHOLDS = {
    # Split by format: a 2-minute single-meme explainer can never reach a roundup's count.
    "wellformed_per_video_roundup": 5.0,
    "wellformed_per_video_single": 2.0,
    "specific_rate": 0.30,
    "mutation_spread_share": 0.10,
}


# Bilibili answers unauthenticated bursts with HTTP 412. Slowing down, sending a
# Referer, and reusing browser cookies are the three things that clear it.
EXTRA: list[str] = []


def run(args: list[str], timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "yt_dlp", *EXTRA, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def as_url(token: str) -> str:
    if token.startswith("http"):
        return token
    return "https://www.bilibili.com/video/%s" % token


def video_id(token: str) -> str:
    match = re.search(r"(BV[0-9A-Za-z]{10})", token)
    return match.group(1) if match else re.sub(r"[^0-9A-Za-z_-]", "_", token)[:40]


def srt_to_lines(text: str) -> list[str]:
    """SRT blocks -> 'mm:ss  text', one cue per line."""
    lines = []
    for block in re.split(r"\n\s*\n", text.strip()):
        stamp = re.search(r"(\d{2}):(\d{2}):(\d{2})[,.]\d+\s*-->", block)
        if not stamp:
            continue
        body = " ".join(
            part.strip()
            for part in block.splitlines()[2:]
            if part.strip() and not part.strip().isdigit()
        )
        body = re.sub(r"<[^>]+>", "", body).strip()
        if not body:
            continue
        hours, minutes, seconds = (int(x) for x in stamp.groups())
        lines.append("%02d:%02d  %s" % (hours * 60 + minutes, seconds, body))
    return lines


def fetch_videos(tokens: list[str], out: Path, sleep: float = 4.0) -> int:
    out.mkdir(parents=True, exist_ok=True)
    gate = []
    for index, token in enumerate(tokens):
        if index:
            time.sleep(sleep)
        url, vid = as_url(token), video_id(token)
        print("\n=== %s ===" % vid)
        probe = run(["--dump-single-json", "--skip-download", "--no-warnings", "--", url])
        if probe.returncode != 0:
            tail = (probe.stderr.strip().splitlines() or ["?"])[-1][:200]
            print("  metadata failed: %s" % tail)
            if "412" in tail:
                print("    412 是 B 站风控，不是这个视频的问题。加大 --sleep，"
                      "或用 --cookies-from-browser chrome 复用你自己的登录态。")
            gate.append((vid, "http_412" if "412" in tail else "metadata_failed", 0))
            continue
        data = json.loads(probe.stdout)
        tracks = {**(data.get("subtitles") or {}), **(data.get("automatic_captions") or {})}
        tracks.pop("danmaku", None)
        print("  title: %s" % (data.get("title") or "")[:70])
        print("  uploaded: %s   duration: %ss" % (data.get("upload_date"), data.get("duration")))
        print("  subtitle tracks: %s" % (sorted(tracks) or "NONE"))
        (out / ("%s.meta.json" % vid)).write_text(
            json.dumps(
                {k: data.get(k) for k in ("id", "title", "uploader", "upload_date", "duration", "webpage_url")},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        if not tracks:
            gate.append((vid, "no_subtitles", 0))
            continue
        run([
            "--write-subs", "--write-auto-subs", "--convert-subs", "srt", "--skip-download",
            "--sub-langs", "zh.*,zh-Hans,zh-CN,ai-zh,en.*", "--no-warnings",
            "-o", str(out / "%(id)s.%(ext)s"), "--", url,
        ])
        srts = sorted(out.glob("%s*.srt" % vid)) or sorted(out.glob("%s*.srt" % data.get("id", vid)))
        cues = []
        for path in srts:
            cues = srt_to_lines(path.read_text(encoding="utf-8", errors="replace"))
            if cues:
                break
        if cues:
            target = out / ("%s.transcript.txt" % vid)
            target.write_text("\n".join(cues), encoding="utf-8")
            print("  -> %s  (%d cues)" % (target.name, len(cues)))
            gate.append((vid, "ok", len(cues)))
        else:
            print("  subtitle track listed but no cues extracted")
            gate.append((vid, "empty_subtitles", 0))
    usable = sum(1 for _, status, _ in gate if status == "ok")
    print("\n--- step 0 gate ---")
    for vid, status, count in gate:
        print("  %-14s %-16s %s" % (vid, status, count or ""))
    print("  usable transcripts: %d / %d" % (usable, len(gate)))
    if usable < len(gate):
        print("  没有字幕的视频要走 ASR/OCR，单条成本大幅上升 —— 这是决策依据之一。")
    return 0


def transcribe(tokens: list[str], out: Path, model_name: str, sleep: float = 4.0) -> int:
    """ASR fallback for videos with no subtitle track. Same transcript format as the subtitle path."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("需要 faster-whisper: pip install faster-whisper")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    print("loading model %r (first run downloads weights)..." % model_name)
    model = WhisperModel(model_name, device="cpu", compute_type="int8")
    for index, token in enumerate(tokens):
        if index:
            time.sleep(sleep)
        url, vid = as_url(token), video_id(token)
        print("\n=== %s ===" % vid)
        existing = sorted(out.glob("%s.audio.*" % vid))
        if not existing:
            got = run(["-f", "bestaudio/best", "--no-warnings", "-o", str(out / ("%s.audio.%%(ext)s" % vid)), "--", url])
            if got.returncode != 0:
                tail = (got.stderr.strip().splitlines() or ["?"])[-1][:200]
                print("  audio download failed: %s" % tail)
                continue
            existing = sorted(out.glob("%s.audio.*" % vid))
        if not existing:
            print("  no audio file produced")
            continue
        audio = existing[0]
        print("  transcribing %s ..." % audio.name)
        segments, info = model.transcribe(str(audio), language="zh", vad_filter=True)
        lines = []
        for segment in segments:
            body = segment.text.strip()
            if body:
                lines.append("%02d:%02d  %s" % (int(segment.start) // 60, int(segment.start) % 60, body))
        target = out / ("%s.transcript.txt" % vid)
        target.write_text("\n".join(lines), encoding="utf-8")
        (out / ("%s.transcript.json" % vid)).write_text(
            json.dumps(
                {"video_id": vid, "source": "asr", "model": model_name,
                 "language": info.language, "duration": info.duration, "cues": len(lines)},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )
        print("  -> %s  (%d segments, %.0fs audio)" % (target.name, len(lines), info.duration or 0))
    print("\n注意：ASR 对谐音梗的梗名最容易出错，而梗名恰恰是最关键的字段。"
          "\n标注时以画面上看到的写法为准，不要照抄转写结果。")
    return 0


def extract_derivatives(
    tokens: list[str], out: Path, every: float, sleep: float,
    video_path: Path | None = None, resolve: bool = True,
) -> int:
    """OCR burned-in BV ids off the canvas, then resolve each against the platform.

    A BV id is self-verifying: a misread character simply fails to resolve, so OCR
    noise costs recall, never correctness. The resolve rate is the feasibility metric.
    """
    try:
        import cv2
    except ImportError:
        print("需要 opencv: pip install opencv-python")
        return 2
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        print("需要 OCR: pip install rapidocr-onnxruntime")
        return 2
    out.mkdir(parents=True, exist_ok=True)
    ocr = RapidOCR()
    pattern = re.compile(r"BV[0-9A-Za-z]{10}")
    for token in tokens:
        url, vid = as_url(token), video_id(token)
        print("\n=== %s ===" % vid)
        existing = [video_path] if video_path else [
            p for p in out.glob("%s.video.*" % vid) if p.suffix != ".json"
        ]
        if not existing:
            # Bilibili serves DASH, so `best` (a single muxed file) often does not exist.
            # OCR needs pictures only, so take a video-only stream and skip the ffmpeg merge.
            target_arg = ["-o", str(out / ("%s.video.%%(ext)s" % vid)), "--", url]
            got = run(["-f", "bv*[height<=1080]/bv*", "--no-warnings", *target_arg], timeout=600)
            if got.returncode != 0 and "not available" in got.stderr:
                print("  format selector missed; retrying with yt-dlp defaults")
                got = run(["--no-warnings", *target_arg], timeout=600)
            if got.returncode != 0:
                tail = (got.stderr.strip().splitlines() or ["?"])[-1][:180]
                print("  download failed: %s" % tail)
                if "412" in tail:
                    print("    风控拦的是下载，不是 OCR。用浏览器把视频存下来，再："
                          "\n      prep.py derivatives %s --video 路径.mp4 --no-resolve" % vid)
                continue
            existing = [p for p in out.glob("%s.video.*" % vid) if p.suffix != ".json"]
        capture = cv2.VideoCapture(str(existing[0]))
        fps = capture.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(fps * every))
        hits: dict[str, float] = {}
        frame_text: list[dict] = []
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if index % step == 0:
                result, _ = ocr(frame)
                texts = [str(line[1]) for line in (result or [])]
                stamp = index / fps
                for found in pattern.findall(" ".join(texts)):
                    hits.setdefault(found, stamp)
                if texts:
                    frame_text.append({"at": round(stamp, 1), "text": texts})
            index += 1
        capture.release()
        (out / ("%s.ocr.json" % vid)).write_text(
            json.dumps(frame_text, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("  frames OCR'd: %d   BV ids found: %d" % (len(frame_text), len(hits)))
        # 0/o and 1/l confusions produce two ids for one card; flag them so counts stay honest.
        ordered = sorted(hits.items(), key=lambda kv: kv[1])
        for (a, at_a), (b, at_b) in zip(ordered, ordered[1:]):
            differing = sum(1 for x, y in zip(a, b) if x != y)
            if len(a) == len(b) and differing == 1 and abs(at_a - at_b) <= 5:
                print("    ! %s / %s 相差一个字符且相邻出现，多半是同一个号的误读" % (a, b))
        rows, resolved = [], 0
        for found, stamp in sorted(hits.items(), key=lambda kv: kv[1]):
            if not resolve:
                rows.append({"bv_id": found, "seen_at": round(stamp, 1), "resolved": False})
                print("    %s  %-6.1fs  (未解析)" % (found, stamp))
                continue
            time.sleep(sleep)
            probe = run(["--dump-single-json", "--skip-download", "--no-warnings", "--", as_url(found)])
            if probe.returncode != 0:
                rows.append({"bv_id": found, "seen_at": round(stamp, 1), "resolved": False})
                print("    %s  %-6.1fs  UNRESOLVED" % (found, stamp))
                continue
            data = json.loads(probe.stdout)
            resolved += 1
            rows.append({
                "bv_id": found, "seen_at": round(stamp, 1), "resolved": True,
                "title": data.get("title"), "uploader": data.get("uploader"),
                "upload_date": data.get("upload_date"), "duration": data.get("duration"),
            })
            print("    %s  %-6.1fs  %s  %s" % (found, stamp, data.get("upload_date"), (data.get("title") or "")[:36]))
        target = out / ("%s.derivatives.csv" % vid)
        with target.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(
                handle, fieldnames=["bv_id", "seen_at", "resolved", "title", "uploader", "upload_date", "duration"]
            )
            writer.writeheader()
            writer.writerows(rows)
        if not resolve:
            print("  -> %s   OCR 得到 %d 个 BV 号，未解析（--no-resolve）" % (target.name, len(hits)))
        else:
            rate = resolved / len(hits) if hits else 0.0
            print("  -> %s   resolve rate %.0f%% (%d/%d)" % (target.name, rate * 100, resolved, len(hits)))
            if hits and rate < 0.6:
                print("     解析率偏低：多半是 OCR 误读。提高分辨率或减小 --every 再试。")
    print("\n昵称等中文文本没有自动抽取，留在 *.ocr.json 里人工挑选。")
    return 0


def resolve_ids(out: Path, sleep: float) -> int:
    """Resolve rows left unresolved by --no-resolve, without re-running OCR."""
    paths = sorted(out.glob("*.derivatives.csv"))
    if not paths:
        print("没有找到 *.derivatives.csv")
        return 1
    fields = ["bv_id", "seen_at", "resolved", "title", "uploader", "upload_date", "duration"]
    # A refused request says nothing about OCR quality; only an answered one does.
    done = not_found = blocked = 0
    for path in paths:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        pending = [r for r in rows if (r.get("resolved") or "").strip().lower() not in {"true", "1"}]
        if not pending:
            continue
        print("\n=== %s  (%d pending) ===" % (path.name, len(pending)))
        for row in pending:
            time.sleep(sleep)
            probe = run(["--dump-single-json", "--skip-download", "--no-warnings", "--", as_url(row["bv_id"])])
            if probe.returncode != 0 or not probe.stdout.strip().startswith("{"):
                tail = (probe.stderr.strip().splitlines() or ["?"])[-1]
                if "412" in tail:
                    blocked += 1
                    print("    %s  BLOCKED     风控 412（未判定，稍后重跑）" % row["bv_id"])
                else:
                    not_found += 1
                    print("    %s  NOT FOUND   %s" % (row["bv_id"], tail[:60]))
                continue
            data = json.loads(probe.stdout)
            row.update({
                "resolved": "True", "title": data.get("title"), "uploader": data.get("uploader"),
                "upload_date": data.get("upload_date"), "duration": data.get("duration"),
            })
            done += 1
            print("    %s  %s  %s" % (row["bv_id"], data.get("upload_date"), (data.get("title") or "")[:40]))
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows([{k: r.get(k, "") for k in fields} for r in rows])
    answered = done + not_found
    if answered:
        print("\nOCR 准确率 %.0f%% (%d/%d 已应答请求)" % (done / answered * 100, done, answered))
    if blocked:
        print("另有 %d 条被风控拒绝，未计入准确率 —— 那是限流，不是识别错误。" % blocked)
    print("失败行保留 resolved=False，稍后重跑即可，不会丢。")
    return 0


# Bylines and handles sit in the same corner as the title card and were being picked as
# the meme name; BV1ii4C6QEk8 came out as "作者：@platsae".
BOILERPLATE = re.compile(r"bilibili|bilisili|梗百科|作者|^@|^[\d\s.:+=]+$|^.{0,1}$", re.I)


def guess_meme_name(ocr_path: Path) -> str:
    """The episode's title card sits in the first seconds; take the most persistent short line."""
    frames = json.loads(ocr_path.read_text(encoding="utf-8"))
    counts: Counter = Counter()
    for frame in frames:
        if frame["at"] > 14:
            continue
        for line in frame["text"]:
            line = line.strip()
            if 2 <= len(line) <= 16 and not BOILERPLATE.search(line):
                counts[line] += 1
    return counts.most_common(1)[0][0] if counts else ""


def build_sheet(out: Path) -> int:
    """Join resolved ids with their episode's meme name for the human role pass."""
    target = out / "lineage.csv"
    fields = ["episode_id", "meme_name", "bv_id", "upload_date", "title", "role", "notes"]
    prior = {}
    if target.exists():
        with target.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                prior[row["bv_id"]] = row
    rows = []
    for path in sorted(out.glob("*.derivatives.csv")):
        episode = path.name.replace(".derivatives.csv", "")
        ocr_path = out / ("%s.ocr.json" % episode)
        meme = guess_meme_name(ocr_path) if ocr_path.exists() else ""
        with path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                keep = prior.get(row["bv_id"], {})
                rows.append({
                    "episode_id": episode,
                    "meme_name": keep.get("meme_name") or meme,
                    "bv_id": row["bv_id"],
                    "upload_date": row.get("upload_date", ""),
                    "title": row.get("title", ""),
                    "role": keep.get("role", ""),
                    "notes": keep.get("notes", ""),
                })
    rows.sort(key=lambda r: (r["meme_name"], r["upload_date"] or "9"))
    with target.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    judged = sum(1 for r in rows if r["role"])
    print("-> %s   %d 行，其中 %d 行已判定 role" % (target.name, len(rows), judged))
    print("role 取值：source | popularized_by | derivative | reference | irrelevant（留空表示待判定）")
    print("meme_name 是从 OCR 首屏猜的，错了直接改，重跑不会覆盖你填过的内容。")
    return 0


def _iso_day(value: str) -> str:
    """Accept 20260812 and Excel's 2026/8/15 alike; Bilibili timestamps are CST."""
    value = (value or "").strip()
    if re.fullmatch(r"\d{8}", value):
        y, m, d = value[:4], value[4:6], value[6:]
    else:
        parts = re.split(r"[/\-.]", value)
        if len(parts) != 3:
            return ""
        y, m, d = parts
    return "%s-%02d-%02dT00:00:00+08:00" % (y, int(m), int(d))


def _scalar(value: str) -> str:
    """A YAML-safe double-quoted scalar. JSON is a YAML subset, so this always parses."""
    return json.dumps(value, ensure_ascii=False)


def build_drafts(sheet: Path, out: Path) -> int:
    """lineage.csv -> one curation YAML per meme, in the ADR 0002 format."""
    with sheet.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if (r.get("meme_name") or "").strip()]
    memes: dict[str, list[dict]] = {}
    for row in rows:
        # A fusion row like "A&B&C" belongs to every meme it names.
        for name in [n.strip() for n in (row["meme_name"] or "").split("&") if n.strip()]:
            memes.setdefault(name, []).append(row)
    out.mkdir(parents=True, exist_ok=True)
    # Never overwrite a record a human has touched: match on canonical_name, not filename,
    # so files renamed to proper pinyin slugs are still recognised.
    existing: dict[str, str] = {}
    for path in out.glob("*.y*ml"):
        if path.name.startswith("_"):
            continue
        match = re.search(r"^canonical_name:\s*(.+)$", path.read_text(encoding="utf-8"), re.M)
        if match:
            existing[match.group(1).strip()] = path.name
    written, warnings = 0, []
    for index, (name, items) in enumerate(sorted(memes.items()), 1):
        dated = [r for r in items if _iso_day(r.get("upload_date"))]
        usable = [r for r in dated if (r.get("role") or "").strip() == "derivative"]
        upstream = [r for r in dated if (r.get("role") or "").strip() == "source"]
        spreaders = [r for r in dated if (r.get("role") or "").strip() == "popularized_by"]
        if not (usable or upstream or spreaders):
            warnings.append("%s：没有可用的行（缺日期或未判定），跳过" % name)
            continue
        dates = sorted(_iso_day(r["upload_date"]) for r in (usable or dated))
        earliest, latest = dates[0][:10], dates[-1][:10]
        if usable and len(dates) > 1 and int(dates[0][:4]) < int(dates[1][:4]) - 1:
            warnings.append(
                "%s：最早一条 %s 比其余早多年，derivative 早于梗本身在时间上讲不通，"
                "多半应为 source" % (name, earliest))
        if name in existing:
            warnings.append("%s：已有 %s，保留人工内容不覆盖" % (name, existing[name]))
            continue
        ascii_slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        slug = ascii_slug or ("meme-%02d" % index)
        lines = [
            "# 由 evals/feasibility/prep.py drafts 从 lineage.csv 生成",
            "# definition / usage_context / claims 需要人工补齐，evidence 入库后再填 ID",
            "slug: %s" % slug,
            "resolved: false",
            "",
            "canonical_name: %s" % name,
            "aliases: []",
            "",
            "# definition 必填，且 claims 里要有逐字相同的 statement（用 |- 块标量）",
            'definition: ""',
            'usage_context: ""',
            "",
            "origin_status: unknown",
            "origin_type: unknown",
            'origin_ref: ""',
            "",
            "taxonomy: []",
            "platform_primary: bilibili",
            "material_path: ocr",
            "",
            "sources:",
        ]
        for row in upstream + spreaders + usable:
            lines += [
                "  - url: https://www.bilibili.com/video/%s" % row["bv_id"],
                "    role: %s" % (row.get("role") or "").strip(),
                "    note: %s"
                % _scalar(
                    "%s（%s 画面中引用）"
                    % ((row.get("title") or "").replace(chr(10), " ")[:40], row["episode_id"])
                ),
            ]
        lines += ["", "evidence_map:"]
        for row in upstream + spreaders + usable:
            lines.append("  ocr-%s: null" % row["bv_id"])
        lines += ["", "claims: []", "", "events:"]
        for row in usable:
            lines += [
                "  - event_type: remix",
                "    description: %s"
                % _scalar("%s 出现衍生作品《%s》" % (name, (row.get("title") or "")[:30])),
                "    occurred_at_start: %s" % _iso_day(row["upload_date"]),
                "    time_precision: day",
                "    time_basis: 平台显示的投稿时间，经 %s 画面引用发现" % row["episode_id"],
                "    evidence: [ocr-%s]" % row["bv_id"],
            ]
        lines += ["", "relations:"] if (upstream or spreaders) else ["", "relations: []"]
        for row in upstream:
            lines += [
                "  - predicate: derived_from",
                "    target_type: source",
                "    target_bv: %s" % row["bv_id"],
                "    assertion_status: supported",
                "    evidence: [ocr-%s]" % row["bv_id"],
            ]
        for row in spreaders:
            lines += [
                "  - predicate: popularized_by",
                "    target_type: source",
                "    target_bv: %s" % row["bv_id"],
                "    assertion_status: supported",
                "    evidence: [ocr-%s]" % row["bv_id"],
            ]
        lines += [
            "",
            "gold:", "  canonical:", "    - %s" % name,
            "  alias: []", "  origin_intent:", "    - %s的出处" % name,
            "  must_not_return: []", "",
            "curation:", '  curator: ""',
            "  started_at: 2026-09-09",
            "  ingestion_ok: true",
            "  findings:",
            "    - 衍生关系来自 %s 画面中的 BV 号 OCR，日期为平台元数据，非任何人的断言" % items[0]["episode_id"],
            "    - 传播区间 %s .. %s（%d 条）" % (earliest, latest, len(usable)),
        ]
        (out / ("%s.yaml" % slug)).write_text("\n".join(lines) + "\n", encoding="utf-8")
        written += 1
        print("  %-28s %d 条衍生   %s .. %s   -> %s.yaml" % (name, len(usable), earliest, latest, slug))
    for warning in warnings:
        print("  ! %s" % warning)
    print("\n写出 %d 个策展草稿到 %s" % (written, out))
    print("下一步：补 definition 与 claims，然后 python evals/validate_curation.py %s" % out)
    return 0


def fetch_cnmeme(names: list[str], out: Path) -> int:
    out = out / "cnmeme"
    out.mkdir(parents=True, exist_ok=True)
    base = "https://cnmeme.wiki/api/v1/public/memes"

    def get(url: str, attempts: int = 3):
        """Their endpoint drops TLS connections intermittently; retry before giving up."""
        last = None
        for _ in range(attempts):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(request, timeout=25) as response:
                    return json.loads(response.read().decode("utf-8"))
            except Exception as exc:
                last = exc
        raise last

    for name in names:
        print("\n=== %s ===" % name)
        try:
            listing = get("%s?%s" % (base, urllib.parse.urlencode({"q": name, "limit": 5})))
        except Exception as exc:
            print("  search failed: %s" % type(exc).__name__)
            continue
        items = listing.get("items") or listing.get("data") or []
        if not items:
            print("  竞品没有收录 —— 这本身是一条发现")
            (out / ("%s.json" % name)).write_text(
                json.dumps({"query": name, "found": False}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            continue
        titles = [str(x.get("title") or x.get("slug") or "") for x in items]
        if not any(name in title for title in titles):
            print("  ! 返回的条目标题都不含查询词：%s" % titles[:5])
            print("    先确认 q 参数是否真的在过滤，否则 Part B 比的是不相干的条目。")
        detail = next((x for x in items if name in str(x.get("title") or "")), items[0])
        slug = detail.get("slug")
        if slug:
            try:
                detail = get("%s/%s" % (base, urllib.parse.quote(str(slug))))
            except Exception as exc:
                print("  detail failed: %s" % type(exc).__name__)
        (out / ("%s.json" % name)).write_text(
            json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        blob = json.dumps(detail, ensure_ascii=False)
        print("  slug: %s   正文约 %d 字" % (slug, len(blob)))
        print("  含链接: %s   含年份: %s" % ("http" in blob, bool(re.search(r"20[012]\d", blob))))
        print("  -> 人工判断：有没有可核查的引用？日期有没有依据？分不分起源与走红？")
    return 0


def summarize(path: Path) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = [r for r in csv.DictReader(handle) if (r.get("video_id") or "").strip().upper() != "EXAMPLE"]
    rows = [r for r in rows if (r.get("meme") or "").strip()]
    if not rows:
        print("annotations.csv 里还没有真实标注行（EXAMPLE 行会被跳过）")
        return 1

    def yes(row, field):
        return (row.get(field) or "").strip().lower() in {"y", "yes", "true", "1", "是"}

    videos = {(r.get("video_id") or "?").strip() for r in rows}
    types = Counter((r.get("claim_type") or "?").strip() for r in rows)
    unknown = sorted(set(types) - set(CLAIM_TYPES) - {"?"})
    formats: dict[str, str] = {}
    for row in rows:
        vid = (row.get("video_id") or "?").strip()
        fmt = (row.get("video_format") or "").strip().lower()
        formats.setdefault(vid, fmt if fmt in {"single", "roundup"} else "single")
    specificity = Counter()
    wellformed_by_format: Counter = Counter()
    for row in rows:
        score = yes(row, "names_source") + yes(row, "gives_date")
        bucket = ("vague", "partial", "specific")[score]
        specificity[bucket] += 1
        if bucket == "specific" and yes(row, "verifiable"):
            wellformed_by_format[formats[(row.get("video_id") or "?").strip()]] += 1
    specific_rate = specificity["specific"] / len(rows)
    drift = types["mutation"] + types["spread"]
    drift_share = drift / len(rows)
    cite_rate = sum(1 for r in rows if yes(r, "video_cites")) / len(rows)

    print("视频 %d   标注 %d 条   涉及梗 %d 个"
          % (len(videos), len(rows), len({(r.get("meme") or "").strip() for r in rows})))
    print("\n类型分布：%s" % dict(types))
    if unknown:
        print("  ! 未知 claim_type：%s（允许值：%s）" % (unknown, list(CLAIM_TYPES)))
    print("具体度：%s" % dict(specificity))
    print("视频自身给出可核查引用：%.0f%%" % (cite_rate * 100))

    print("\n--- 决策指标（阈值写在 prep.py THRESHOLDS，测试前已固定）---")
    checks = []
    for fmt, label in (("roundup", "每视频良构断言(roundup)"), ("single", "每视频良构断言(single)")):
        count = sum(1 for f in formats.values() if f == fmt)
        if not count:
            continue
        threshold = THRESHOLDS["wellformed_per_video_%s" % fmt]
        checks.append((label, wellformed_by_format[fmt] / count, threshold,
                       "%d 个视频，阈值 ≥%.0f" % (count, threshold)))
    checks += [
        ("specific 占比", specific_rate, THRESHOLDS["specific_rate"],
         "低于 %.0f%% 说明多数是模糊断言" % (THRESHOLDS["specific_rate"] * 100)),
        ("mutation+spread 占比", drift_share, THRESHOLDS["mutation_spread_share"],
         "低于 %.0f%% 说明四轴方向没有素材支撑" % (THRESHOLDS["mutation_spread_share"] * 100)),
    ]
    for label, value, threshold, note in checks:
        mark = "PASS" if value >= threshold else "FAIL"
        shown = "%.2f" % value if label.startswith("每视频") else "%.0f%%" % (value * 100)
        print("  [%s] %-22s %-7s  %s" % (mark, label, shown, note))
    print("\n引用率低不是失败，它只是把证据层级固定在“有出处的说法”，不是“已确认的起源”。"
          "\n若如此，请在 ADR 里明说，不要让 verified 标记看起来像事实核查。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="mode", required=True)
    videos = sub.add_parser("videos", help="probe subtitles and dump timestamped transcripts")
    videos.add_argument("tokens", nargs="+", metavar="BV_OR_URL")
    videos.add_argument("--out", type=Path, default=HERE)
    videos.add_argument("--sleep", type=float, default=4.0, help="seconds between videos; raise on 412")
    videos.add_argument(
        "--cookies-from-browser",
        metavar="BROWSER",
        help="chrome / edge / firefox — reuses your own bilibili login to clear 412",
    )
    videos.add_argument("--cookies", metavar="FILE", help="cookies.txt; works with the browser open")
    asr = sub.add_parser("asr", help="transcribe videos that have no subtitle track")
    asr.add_argument("tokens", nargs="+", metavar="BV_OR_URL")
    asr.add_argument("--out", type=Path, default=HERE)
    asr.add_argument("--model", default="small", help="faster-whisper size: small / medium / large-v3")
    asr.add_argument("--sleep", type=float, default=4.0)
    asr.add_argument("--cookies-from-browser", metavar="BROWSER")
    asr.add_argument("--cookies", metavar="FILE", help="cookies.txt; works with the browser open")
    deriv = sub.add_parser("derivatives", help="OCR burned-in BV ids and resolve them to dated videos")
    deriv.add_argument("tokens", nargs="+", metavar="BV_OR_URL")
    deriv.add_argument("--out", type=Path, default=HERE)
    deriv.add_argument("--every", type=float, default=1.0, help="sample one frame per N seconds")
    deriv.add_argument("--sleep", type=float, default=4.0, help="seconds between resolve calls")
    deriv.add_argument("--cookies-from-browser", metavar="BROWSER")
    deriv.add_argument("--cookies", metavar="FILE", help="cookies.txt; works with the browser open")
    # PowerShell drops empty string arguments, so --proxy "" never survives. Use a flag.
    deriv.add_argument("--no-proxy", action="store_true", help="bypass any system proxy for bilibili")
    deriv.add_argument("--video", type=Path, help="OCR this local file instead of downloading")
    deriv.add_argument("--no-resolve", action="store_true", help="skip the resolve pass; OCR only")
    res = sub.add_parser("resolve", help="resolve pending rows in *.derivatives.csv without re-OCR")
    res.add_argument("--out", type=Path, default=HERE)
    res.add_argument("--sleep", type=float, default=12.0)
    res.add_argument("--cookies-from-browser", metavar="BROWSER")
    res.add_argument("--cookies", metavar="FILE", help="cookies.txt; works with the browser open")
    sheet = sub.add_parser("sheet", help="build lineage.csv for the human role pass")
    sheet.add_argument("--out", type=Path, default=HERE)
    dr = sub.add_parser("drafts", help="turn lineage.csv into curation YAML per meme")
    dr.add_argument("--sheet", type=Path, default=HERE / "lineage.csv")
    dr.add_argument("--out", type=Path, default=HERE.parent / "curation")
    cnmeme = sub.add_parser("cnmeme", help="pull competitor entries for the same memes")
    cnmeme.add_argument("names", nargs="+")
    cnmeme.add_argument("--out", type=Path, default=HERE)
    summary = sub.add_parser("summarize", help="compute decision metrics from annotations.csv")
    summary.add_argument("csv_path", type=Path)
    args = parser.parse_args()
    if args.mode == "videos":
        EXTRA.extend([
            "--add-header", "Referer:https://www.bilibili.com/",
            "--retries", "5", "--extractor-retries", "5",
        ])
        if args.cookies_from_browser:
            EXTRA.extend(["--cookies-from-browser", args.cookies_from_browser])
        if getattr(args, "cookies", None):
            EXTRA.extend(["--cookies", args.cookies])
        return fetch_videos(args.tokens, args.out, args.sleep)
    if args.mode == "derivatives":
        EXTRA.extend([
            "--add-header", "Referer:https://www.bilibili.com/",
            "--retries", "5", "--extractor-retries", "5",
        ])
        if args.cookies_from_browser:
            EXTRA.extend(["--cookies-from-browser", args.cookies_from_browser])
        if getattr(args, "cookies", None):
            EXTRA.extend(["--cookies", args.cookies])
        if args.no_proxy:
            EXTRA.extend(["--proxy", ""])
        return extract_derivatives(args.tokens, args.out, args.every, args.sleep,
                                   args.video, not args.no_resolve)
    if args.mode == "drafts":
        return build_drafts(args.sheet, args.out)
    if args.mode == "sheet":
        return build_sheet(args.out)
    if args.mode == "resolve":
        EXTRA.extend(["--add-header", "Referer:https://www.bilibili.com/",
                      "--retries", "3", "--extractor-retries", "3"])
        if args.cookies_from_browser:
            EXTRA.extend(["--cookies-from-browser", args.cookies_from_browser])
        if getattr(args, "cookies", None):
            EXTRA.extend(["--cookies", args.cookies])
        return resolve_ids(args.out, args.sleep)
    if args.mode == "asr":
        EXTRA.extend([
            "--add-header", "Referer:https://www.bilibili.com/",
            "--retries", "5", "--extractor-retries", "5",
        ])
        if args.cookies_from_browser:
            EXTRA.extend(["--cookies-from-browser", args.cookies_from_browser])
        if getattr(args, "cookies", None):
            EXTRA.extend(["--cookies", args.cookies])
        return transcribe(args.tokens, args.out, args.model, args.sleep)
    if args.mode == "cnmeme":
        return fetch_cnmeme(args.names, args.out)
    return summarize(args.csv_path)


if __name__ == "__main__":
    raise SystemExit(main())
