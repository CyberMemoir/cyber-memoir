"""Select independent human queries against captured public identities, not local resolved flags."""

import argparse
import hashlib
import json
from pathlib import Path

import yaml
from checkpoint import digest


def select_gold(snapshot, descriptions, negatives):
    names = {record["canonical_name"] for record in snapshot["records"]}
    surfaces = {
        name.strip().casefold()
        for record in snapshot["records"]
        for name in [record["canonical_name"], *(record.get("aliases") or [])]
    }
    rows, excluded = [], []
    for name, queries in descriptions.items():
        for query in queries or []:
            if name not in names:
                excluded.append(
                    {"name": name, "query": query, "reason": "not currently public in captured source"}
                )
                continue
            rows.append(
                {
                    "query": query,
                    "expected_names": [name],
                    "answerable": True,
                    "bucket": "description",
                    "query_source": "human",
                }
            )
    for row in negatives.get("negatives") or []:
        if row["query"].strip().casefold() in surfaces:
            raise ValueError("negative query names a currently public identity or alias")
        rows.append(
            {
                "query": row["query"],
                "expected_names": [],
                "answerable": False,
                "bucket": "negative",
                "query_source": "local_annotation",
                "negative_kind": row["kind"],
            }
        )
    queries = [row["query"].strip().casefold() for row in rows]
    if not all(queries) or len(queries) != len(set(queries)):
        raise ValueError("empty or duplicate gold queries")
    return rows, excluded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--descriptions", type=Path, required=True)
    parser.add_argument("--negatives", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.selection.exists() or args.out.resolve() == args.selection.resolve():
        parser.error("outputs must be distinct new files; original inputs are never overwritten")
    snapshot = json.loads(args.snapshot.read_bytes())
    descriptions, negatives = args.descriptions.read_bytes(), args.negatives.read_bytes()
    rows, excluded = select_gold(snapshot, yaml.safe_load(descriptions), yaml.safe_load(negatives))
    raw = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows).encode()
    selection = {
        "source_public_sha256": digest(snapshot),
        "descriptions_sha256": hashlib.sha256(descriptions).hexdigest(),
        "negatives_sha256": hashlib.sha256(negatives).hexdigest(),
        "gold_sha256": hashlib.sha256(raw).hexdigest(),
        "excluded": excluded,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.selection.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("xb") as stream:
        stream.write(raw)
    with args.selection.open("x", encoding="utf-8") as stream:
        json.dump(selection, stream, ensure_ascii=False, indent=2, sort_keys=True)
    print(json.dumps({"cases": len(rows), "excluded": len(excluded)}))


if __name__ == "__main__":
    main()
