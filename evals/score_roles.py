#!/usr/bin/env python3
"""Score a model's proposed roles against the curator's, per results-2026-09-19-roles.md.

    python evals/score_roles.py ai_context/role_calibration/answers.csv

The key is lineage.csv as committed in 2dfbf11, read from git rather than the working copy,
so a label edited after the answers arrive cannot move the score.
"""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from collections import Counter
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
KEY_COMMIT = "2dfbf11"
ORIGIN = {"source", "popularized_by"}
NON_ORIGIN = {"derivative", "irrelevant"}
# Written before the run; see results-2026-09-19-roles.md.
MAX_FALSE_ORIGIN = 2
MIN_ORIGIN_CAUGHT = 17
MIN_NON_ORIGIN_MATCH = 80


def key() -> dict[tuple[str, str], str]:
    text = subprocess.run(
        ["git", "show", "%s:evals/feasibility/lineage.csv" % KEY_COMMIT],
        cwd=ROOT, capture_output=True, check=True,
    ).stdout.decode("utf-8-sig")
    return {(r["episode_id"], r["bv_id"]): r["role"].strip()
            for r in csv.DictReader(io.StringIO(text)) if r["role"].strip()}


def main(answers_path: str) -> int:
    truth = key()
    rows = {r["row"]: r for r in csv.DictReader(
        open(ROOT / "ai_context/role_calibration/rows.csv", encoding="utf-8"))}
    answers = {r["row"]: r for r in csv.DictReader(open(answers_path, encoding="utf-8-sig"))}
    missing = sorted(set(rows) - set(answers), key=int)
    if missing:
        print("! %d rows unanswered: %s" % (len(missing), ", ".join(missing[:20])))

    false_origin, caught, matched = [], 0, 0
    origin_total = non_origin_total = 0
    swaps, disagreements, asked = [], [], 0
    for n, row in sorted(rows.items(), key=lambda kv: int(kv[0])):
        want = truth[(row["episode_id"], row["bv_id"])]
        got = (answers.get(n, {}).get("role") or "").strip()
        asked += got == "?"
        if want in ORIGIN:
            origin_total += 1
            caught += got in ORIGIN
            if got in ORIGIN and got != want:
                swaps.append(n)
        elif want in NON_ORIGIN:
            non_origin_total += 1
            matched += got == want
            if got in ORIGIN:
                false_origin.append(n)
        if got != want:
            disagreements.append((n, row, want, got, answers.get(n, {})))

    checks = [
        ("1 false origin claims", len(false_origin), "<= %d" % MAX_FALSE_ORIGIN,
         len(false_origin) <= MAX_FALSE_ORIGIN, "of %d" % non_origin_total),
        ("2 origin recall", caught, ">= %d" % MIN_ORIGIN_CAUGHT,
         caught >= MIN_ORIGIN_CAUGHT, "of %d" % origin_total),
        ("3 non-origin agreement", matched, ">= %d" % MIN_NON_ORIGIN_MATCH,
         matched >= MIN_NON_ORIGIN_MATCH, "of %d" % non_origin_total),
    ]
    for name, value, bar, ok, of in checks:
        print("%-24s %3d %-7s  need %-6s  %s" % (name, value, of, bar, "PASS" if ok else "FAIL"))
    print("source <-> popularized_by swaps: %d   answered ?: %d   disagreements: %d"
          % (len(swaps), asked, len(disagreements)))
    print("\nconfusion (curator -> model):")
    for (want, got), count in sorted(Counter((d[2], d[3]) for d in disagreements).items()):
        print("  %-15s -> %-15s %d" % (want, got or "(none)", count))
    print("\ndisagreements:")
    for n, row, want, got, ans in disagreements:
        print("  #%-3s %-12s %s  curator=%-14s model=%-14s %s"
              % (n, row["meme_name"][:12], row["bv_id"], want, got or "-", (ans.get("note") or "")[:60]))
    return 0 if all(c[3] for c in checks) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "ai_context/role_calibration/answers.csv"))
