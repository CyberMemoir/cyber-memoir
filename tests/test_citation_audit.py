"""Approval matches are structural evidence, not automatic semantic support."""

import copy
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("citation_audit")


def fixture():
    evidence = {
        "id": "e1",
        "source_id": "s1",
        "verified": True,
        "retracted": False,
        "content_hash": "synthetic-hash",
        "text": "合成测试原文，不是文化证据。",
        "locator": {"note": "synthetic"},
        "source": {"canonical_url": "https://example.org/synthetic"},
    }
    claim = {
        "key": "definition",
        "statement": "合成测试定义。",
        "stance": "supports",
        "evidence_ids": ["e1"],
        "meme_id": "m1",
        "meme_name": "合成测试条目",
        "meme_revision": 3,
    }
    citation = {
        "evidence_id": "e1",
        "source_id": "s1",
        "content_hash": evidence["content_hash"],
        "text": evidence["text"],
        "locator": evidence["locator"],
        "url": evidence["source"]["canonical_url"],
    }
    return {
        "status": "complete",
        "cases": [
            {
                "query": "合成查询",
                "expected_names": ["合成测试条目"],
                "answer_claims": [claim],
                "answer_citations": [citation],
            }
        ],
    }, {
        "records": [{"id": "m1", "published_revision": 3, "claims": [copy.deepcopy(claim)]}],
        "evidence": [evidence],
    }


def test_matching_approval_and_record_still_requires_semantic_review(module):
    report, snapshot = fixture()
    result, queue = module.audit(report, snapshot)
    assert result["cases"][0]["approved_bindings_match"] is True
    assert result["cases"][0]["citation_records_match"] is True
    assert queue[0]["assessment"] is None
    assert result["cases"][0]["semantic_support"] == "unassessed"


@pytest.mark.parametrize("change", ["revision", "statement", "evidence", "citation"])
def test_stale_or_mismatched_citations_are_detected(module, change):
    report, snapshot = fixture()
    case = report["cases"][0]
    if change == "revision":
        case["answer_claims"][0]["meme_revision"] = 2
    elif change == "statement":
        case["answer_claims"][0]["statement"] = "未批准的另一合成断言。"
    elif change == "evidence":
        snapshot["evidence"][0]["retracted"] = True
    else:
        case["answer_citations"][0]["text"] = "不是所引的原文"
    result, _ = module.audit(report, snapshot)
    assert not all(result["cases"][0][key] for key in ["approved_bindings_match", "citation_records_match"])


def test_no_answer_is_not_vacuous_perfect_coverage(module):
    report, snapshot = fixture()
    report["cases"][0]["answer_claims"] = []
    report["cases"][0]["answer_citations"] = []
    result, queue = module.audit(report, snapshot)
    assert result["cases"][0]["approved_bindings_match"] is None
    assert queue == []
    report["status"] = "invalid"
    with pytest.raises(ValueError):
        module.audit(report, snapshot)


def test_wrong_snapshot_or_gold_cannot_be_used(module):
    import hashlib
    import json

    report, snapshot = fixture()
    report["corpus_sha256"] = "different-snapshot"
    with pytest.raises(ValueError, match="snapshot"):
        module.audit(report, snapshot)
    report["corpus_sha256"] = module.digest(snapshot)
    gold = (json.dumps({"query": "合成查询", "expected_names": ["合成测试条目"]}) + "\n").encode()
    report["gold_sha256"] = hashlib.sha256(gold).hexdigest()
    result, _ = module.audit(report, snapshot, gold)
    assert result["cases"][0]["named_target_claim_fraction"] == 1.0
    with pytest.raises(ValueError, match="gold bytes"):
        module.audit(report, snapshot, gold + b"\n")


def test_duplicate_citations_are_not_silently_overwritten(module):
    report, snapshot = fixture()
    report["cases"][0]["answer_citations"] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        module.audit(report, snapshot)
