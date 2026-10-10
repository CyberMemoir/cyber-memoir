"""All completed example assessments are synthetic fixtures, not cultural grading."""

import copy
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("semantic_review")


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode()


def queue(module):
    claim = {
        "meme_id": "synthetic-meme",
        "meme_revision": 1,
        "key": "definition",
        "statement": "合成测试定义",
        "stance": "supports",
        "evidence_ids": ["synthetic-evidence"],
    }
    row = {
        "audit_id": module.digest({key: claim.get(key) for key in module.IDENTITY_FIELDS}),
        "claim": claim,
        "queries": ["合成描述"],
        "assessment": None,
        "reviewer": None,
        "reason": None,
        "evidence": [
            {
                "id": "synthetic-evidence",
                "source_id": "synthetic-source",
                "source": {"id": "synthetic-source"},
                "content_hash": "a" * 64,
                "verified": True,
                "retracted": False,
                "text": "星😀合成测试原文。",
            }
        ],
    }
    return encode(row) + b"\n"


def assessed(module, raw, label="supported"):
    file = module.prepare(raw)
    file["reviews"][0].update(
        assessment=label,
        reviewer="synthetic-test-reviewer",
        reviewed_at="2026-10-10T12:00:00+00:00",
        reason="合成测试理由，不是真实文化判断。",
        quotes=[
            {
                "evidence_id": "synthetic-evidence",
                "content_hash": "a" * 64,
                "start": 1,
                "end": 2,
                "exact": "😀",
            }
        ],
    )
    return file


def test_prepare_never_invents_assessment_and_pending_is_not_complete(module):
    raw = queue(module)
    file = module.prepare(raw)
    report = module.validate(raw, encode(file))
    assert report["status"] == "partial" and report["pending"] == 1 and report["assessed"] == 0
    assert not any(report["assessment_counts"].values())
    assert file["reviews"][0]["assessment"] is None


@pytest.mark.parametrize("label", ["supported", "partial", "unsupported", "contradicted", "unverifiable"])
def test_explicit_attributed_reviews_count_separately_not_as_truth_precision(module, label):
    raw = queue(module)
    report = module.validate(raw, encode(assessed(module, raw, label)))
    assert report["status"] == "complete" and report["assessment_counts"][label] == 1
    assert "precision" not in report and report["pending"] == 0
    assert report["scope"] == "saved_evidence_text_not_publication"


@pytest.mark.parametrize("change", ["id", "hash", "text", "offset", "boolean_offset", "duplicate_quote"])
def test_quoted_passage_cannot_be_rebound_or_invented(module, change):
    raw = queue(module)
    file = assessed(module, raw)
    quote = file["reviews"][0]["quotes"][0]
    if change == "id":
        quote["evidence_id"] = "other-evidence"
    elif change == "hash":
        quote["content_hash"] = "b" * 64
    elif change == "text":
        quote["exact"] = "编造的摘录"
    elif change == "offset":
        quote["end"] = 3  # Python codepoints, not JS UTF-16 units.
    elif change == "boolean_offset":
        quote["start"] = True
    else:
        file["reviews"][0]["quotes"] *= 2
    with pytest.raises(ValueError):
        module.validate(raw, encode(file))


@pytest.mark.parametrize(
    "change", ["reviewer", "reason", "timestamp", "naive_time", "no_quote", "unknown_verdict"]
)
def test_incomplete_or_unattributed_support_is_refused(module, change):
    raw = queue(module)
    file = assessed(module, raw)
    row = file["reviews"][0]
    if change in ["reviewer", "reason"]:
        row[change] = " "
    elif change == "timestamp":
        row["reviewed_at"] = None
    elif change == "naive_time":
        row["reviewed_at"] = "2026-10-10T12:00:00"
    elif change == "no_quote":
        row["quotes"] = []
    else:
        row["assessment"] = "correct"
    with pytest.raises(ValueError):
        module.validate(raw, encode(file))


@pytest.mark.parametrize(
    "change", ["changed_queue", "unknown_id", "duplicate_review", "pending_metadata", "extra_field"]
)
def test_reviews_must_bind_the_exact_queue_and_known_identities(module, change):
    raw = queue(module)
    file = module.prepare(raw)
    if change == "changed_queue":
        raw += b"\n"
    elif change == "unknown_id":
        file["reviews"][0]["audit_id"] = "0" * 64
    elif change == "duplicate_review":
        file["reviews"] *= 2
    elif change == "pending_metadata":
        file["reviews"][0]["reviewer"] = "someone"
    else:
        file["publish"] = True
    with pytest.raises(ValueError):
        module.validate(raw, encode(file))


@pytest.mark.parametrize("change", ["identity", "retracted", "source", "already_assessed", "empty"])
def test_invalid_or_already_graded_queue_cannot_be_reset(module, change):
    raw = queue(module)
    row = json.loads(raw)
    if change == "identity":
        row["claim"]["statement"] = "另一合成定义"
    elif change == "retracted":
        row["evidence"][0]["retracted"] = True
    elif change == "source":
        row["evidence"][0]["source"]["id"] = "other"
    elif change == "already_assessed":
        row["assessment"] = "supported"
    else:
        raw = b""
    with pytest.raises(ValueError):
        module.prepare(raw if change == "empty" else encode(row))


def test_shared_evidence_must_have_one_frozen_representation(module):
    first = json.loads(queue(module))
    second = copy.deepcopy(first)
    second["claim"]["key"] = "usage_context"
    second["audit_id"] = module.digest({key: second["claim"].get(key) for key in module.IDENTITY_FIELDS})
    second["evidence"][0]["text"] = "另一份不一致原文"
    with pytest.raises(ValueError, match="conflicting"):
        module.prepare(encode(first) + b"\n" + encode(second))


def test_omitted_reviews_remain_pending(module):
    raw = queue(module)
    file = module.prepare(raw)
    file["reviews"] = []
    report = module.validate(raw, encode(file))
    assert report["pending"] == 1 and report["status"] == "partial"


def test_cli_outputs_are_private_and_do_not_overwrite_inputs(module, monkeypatch, tmp_path):
    raw = queue(module)
    source = tmp_path / "queue.jsonl"
    source.write_bytes(raw)
    target = tmp_path / "private" / "reviews.json"
    monkeypatch.setattr(
        "sys.argv", ["semantic_review", "prepare", "--queue", str(source), "--out", str(target)]
    )
    module.main()
    import os

    if os.name == "posix":
        assert target.stat().st_mode & 0o777 == 0o600
        assert target.parent.stat().st_mode & 0o777 == 0o700
    assert source.read_bytes() == raw
    with pytest.raises(SystemExit):
        module.main()
    monkeypatch.setattr(
        "sys.argv", ["semantic_review", "prepare", "--queue", str(source), "--out", str(source)]
    )
    with pytest.raises(SystemExit):
        module.main()
    assert source.read_bytes() == raw


def test_changed_review_input_does_not_write_a_report(module, monkeypatch, tmp_path):
    source = tmp_path / "queue.jsonl"
    raw = queue(module)
    source.write_bytes(raw)
    reviews = tmp_path / "reviews.json"
    reviews.write_bytes(encode(module.prepare(raw)))
    target = tmp_path / "report.json"
    original = module.validate

    def changes_input(*args):
        result = original(*args)
        reviews.write_bytes(reviews.read_bytes() + b"\n")
        return result

    monkeypatch.setattr(module, "validate", changes_input)
    monkeypatch.setattr(
        "sys.argv",
        [
            "semantic_review",
            "validate",
            "--queue",
            str(source),
            "--reviews",
            str(reviews),
            "--out",
            str(target),
        ],
    )
    with pytest.raises(ValueError, match="reviews changed"):
        module.main()
    assert not target.exists()


def test_boolean_schema_version_is_not_an_integer_version(module):
    raw = queue(module)
    file = module.prepare(raw)
    file["schema_version"] = True
    with pytest.raises(ValueError):
        module.validate(raw, encode(file))


@pytest.mark.parametrize(
    "key,value", [("meme_id", None), ("key", ""), ("stance", " "), ("evidence_ids", [False])]
)
def test_empty_or_malformed_claim_identities_cannot_be_signed_by_a_matching_digest(module, key, value):
    row = json.loads(queue(module))
    row["claim"][key] = value
    row["audit_id"] = module.digest({field: row["claim"].get(field) for field in module.IDENTITY_FIELDS})
    with pytest.raises(ValueError):
        module.prepare(encode(row))
