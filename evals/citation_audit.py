"""Audit frozen approval bindings; emit an ungraded semantic-review queue, never auto-grade truth."""

import argparse
import hashlib
import json
from pathlib import Path

from checkpoint import digest


def audit(report, snapshot, gold=None):
    if report.get("status") != "complete" or report.get("failed"):
        raise ValueError("only complete, valid runs can be audited")
    if report.get("corpus_sha256") and report["corpus_sha256"] != digest(snapshot):
        raise ValueError("report belongs to a different public snapshot")
    if gold is not None:
        if hashlib.sha256(gold).hexdigest() != report.get("gold_sha256"):
            raise ValueError("gold bytes differ from the completed run")
        targets = [json.loads(line) for line in gold.decode("utf-8").splitlines() if line.strip()]
        if len(targets) != len(report["cases"]) or any(
            row["query"] != case["query"] for row, case in zip(targets, report["cases"], strict=True)
        ):
            raise ValueError("gold cases differ from the completed run")
    else:
        targets = report["cases"]
    records = {row["id"]: row for row in snapshot["records"]}
    evidence = {row["id"]: row for row in snapshot["evidence"]}
    results, queue = [], {}
    for case, target in zip(report["cases"], targets, strict=True):
        claims = case.get("answer_claims") or []
        citation_rows = case.get("answer_citations") or []
        citations = {row["evidence_id"]: row for row in citation_rows}
        if len(citations) != len(citation_rows):
            raise ValueError("duplicate citation identifiers are ambiguous")
        checks = []
        for claim in claims:
            record = records.get(claim["meme_id"])
            refs = set(claim["evidence_ids"])
            allowed = set()
            if record:
                for approved in record["claims"]:
                    if all(approved.get(key) == claim.get(key) for key in ["key", "statement", "stance"]):
                        allowed.update(approved["evidence_ids"])
            binding = bool(
                record
                and claim.get("meme_revision") == record["published_revision"]
                and refs
                and refs <= allowed
            )
            matching = True
            for identifier in refs:
                item, citation = evidence.get(identifier), citations.get(identifier)
                if not item or not citation or not item.get("verified") or item.get("retracted"):
                    matching = False
                    continue
                if (
                    citation.get("source_id") != item["source_id"]
                    or citation.get("content_hash") != item["content_hash"]
                    or citation.get("locator") != item["locator"]
                    or not item["text"].startswith(citation.get("text", ""))
                    or not citation.get("text")
                    or citation.get("url") != (item.get("source") or {}).get("canonical_url")
                ):
                    matching = False
            checks.append({"approved_binding_matches": binding, "citation_record_matches": matching})
            identity = digest(
                {
                    key: claim.get(key)
                    for key in ["meme_id", "meme_revision", "key", "statement", "stance", "evidence_ids"]
                }
            )
            row = queue.setdefault(
                identity,
                {
                    "audit_id": identity,
                    "claim": claim,
                    "queries": [],
                    "evidence": [evidence[eid] for eid in sorted(refs) if eid in evidence],
                    "assessment": None,
                    "reviewer": None,
                    "reason": None,
                },
            )
            row["queries"].append(case["query"])
        results.append(
            {
                "query": case["query"],
                "claim_count": len(claims),
                "approved_bindings_match": all(row["approved_binding_matches"] for row in checks)
                if checks
                else None,
                "citation_records_match": all(row["citation_record_matches"] for row in checks)
                if checks
                else None,
                "named_target_claim_fraction": sum(
                    claim.get("meme_name", "").strip().casefold()
                    in {name.strip().casefold() for name in target["expected_names"]}
                    for claim in claims
                )
                / len(claims)
                if claims and target.get("expected_names")
                else None,
                "semantic_support": "unassessed" if claims else "not_applicable",
            }
        )
    return {
        "scope": "approval_and_citation_record_audit_not_semantic_entailment",
        "snapshot_sha256": digest(snapshot),
        "cases": results,
        "unique_claims_requiring_semantic_review": len(queue),
    }, list(queue.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument(
        "--gold", type=Path, help="Original run bytes, required for target identity fractions"
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--review-queue", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.review_queue.exists():
        parser.error("audit outputs must be new files")
    raw = args.report.read_bytes()
    result, queue = audit(
        json.loads(raw), json.loads(args.snapshot.read_bytes()), args.gold.read_bytes() if args.gold else None
    )
    result["report_sha256"] = hashlib.sha256(raw).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.review_queue.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
    with args.review_queue.open("x", encoding="utf-8") as stream:
        for row in queue:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    print(
        json.dumps(
            {"cases": len(result["cases"]), "semantic_review_required": len(queue)}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
