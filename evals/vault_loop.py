"""Batch-scoped model review, human approval and resumable publication.

    python evals/vault_loop.py status --batch 4
    python evals/vault_loop.py bundle --batch 4 --out ai_context/batch4_review.json
    python evals/vault_loop.py publish --batch 4 [--dry-run]

Model judgement happens in the browser/chat, never by treating validator success as
semantic review. The reviewer writes curation.automated_review with the bundle's
fingerprint and six check explanations. Uncertain records remain quarantined.
"""
import argparse
import csv
import json
import subprocess
import sys
from pathlib import Path

import yaml
from automation_review import fingerprint, review_error
from human_review import approval_error, write_cards
from materials_index import load_material_index, resolve_placeholder
from validate_curation import check_relation_targets, cross_check, validate

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "evals/curation"


def batch_paths(batch: int) -> list[Path]:
    episodes = set((ROOT / f"ai_context/batch{batch}.txt").read_text(encoding="utf-8-sig").split())
    with (ROOT / "evals/feasibility/lineage.csv").open(encoding="utf-8-sig", newline="") as handle:
        names = {name.strip() for row in csv.DictReader(handle) if row["episode_id"] in episodes
                 for name in row["meme_name"].split("&") if name.strip()}
    paths = []
    for path in sorted(CURATION.glob("*.yaml")):
        if not path.name.startswith("_"):
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
            explicit = set((doc.get("curation") or {}).get("source_episodes") or []) & episodes
            bound = any("ocr-narration-" + episode in (doc.get("evidence_map") or {}) for episode in explicit)
            if doc.get("canonical_name") in names or bound:
                paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["status", "bundle", "human-review", "publish"])
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    args = parser.parse_args()
    index = load_material_index()
    paths = batch_paths(args.batch)
    packets, accepted = [], []
    for path in paths:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        result = validate(path)
        error = review_error(doc, index)
        hold = (doc.get("curation") or {}).get("automation_hold")
        state = "published" if doc.get("resolved") else "quarantined" if hold else "invalid" if result.errors else "needs_review" if error else "ready"
        if state == "ready" and approval_error(doc, index, path):
            state = "awaiting_human"
        print(f"{path.name}: {doc['canonical_name']} [{state}]")
        if state == "ready":
            accepted.append(path)
        if args.action in {"bundle", "human-review"} and state != "published":
            packets.append({"path": str(path), "record": doc, "errors": result.errors,
                            "fingerprint": fingerprint(doc, index),
                            "materials": {key: resolve_placeholder(key, index) for key in doc.get("evidence_map") or {}}})
    if args.action == "human-review":
        output = args.out or ROOT / f"ai_context/batch{args.batch}_human_review.md"
        write_cards(packets, args.batch, output)
        print(f"审核卡：{output}")
    if args.action == "bundle":
        if not args.out:
            parser.error("bundle requires --out")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(packets, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    if args.action == "publish":
        if not accepted:
            print("No human-approved records ready; nothing published.")
            return 1 if any(not yaml.safe_load(path.read_text(encoding="utf-8")).get("resolved") for path in paths) else 0
        # Compare the candidate batch with the rest of the vault for identity collisions.
        all_records = [validate(p) for p in CURATION.glob("*.yaml") if not p.name.startswith("_")]
        problems = cross_check(all_records) + check_relation_targets(all_records)
        if problems:
            print("\n".join(problems))
            return 1
        command = [sys.executable, str(ROOT / "evals/load_curation.py"), *map(str, accepted), "--api", args.api]
        if args.dry_run:
            command.append("--dry-run")
        return subprocess.call(command, cwd=ROOT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
