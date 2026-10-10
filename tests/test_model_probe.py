"""Offline probe integrity and ranking math; synthetic fixtures, no model stand-in metrics."""

import hashlib
import importlib
import json
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def probe(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("model_probe")


def files(directory):
    values = {
        "record.yaml": {
            "resolved": True,
            "canonical_name": "合成定义",
            "aliases": ["合成别名"],
            "definition": "仅用于软件测试的虚构定义。",
            "gold": {"description": ["模型自己生成的测试查询"]},
        },
        "_descriptions.yaml": {"合成定义": ["人写的合成场景问题"], "没有本地定义": ["缺少目标的合成问题"]},
        "_negatives.yaml": {"negatives": [{"query": "未收录合成词", "kind": "fabricated"}]},
    }
    for name, value in values.items():
        (directory / name).write_text(yaml.safe_dump(value, allow_unicode=True))


def test_queries_only_come_from_independent_file_and_missing_targets_are_explicit(probe, tmp_path):
    files(tmp_path)
    docs, cases, excluded, hashes = probe.inputs(tmp_path)
    assert len(docs) == 1 and len(cases) == 2 and len(excluded) == 1
    assert cases[0]["query"] == "人写的合成场景问题"
    assert not any(case["query"] == "模型自己生成的测试查询" for case in cases)
    assert hashes == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.glob("*.yaml")}


@pytest.mark.parametrize(
    "change", ["aliases", "query_type", "duplicate_query", "negative_is_alias", "normalized_duplicate_name"]
)
def test_bad_inputs_are_not_silently_scored(probe, tmp_path, change):
    files(tmp_path)
    name = "record.yaml"
    row = yaml.safe_load((tmp_path / name).read_text())
    if change == "aliases":
        row["aliases"] = "不是列表"
    elif change == "query_type":
        name, row = "_descriptions.yaml", {"合成定义": [{"不是": "字符串"}]}
    elif change == "duplicate_query":
        name, row = "_descriptions.yaml", {"合成定义": ["重复的合成问句", "重复的合成问句"]}
    elif change == "negative_is_alias":
        name, row = "_negatives.yaml", {"negatives": [{"query": "合成别名", "kind": "fabricated"}]}
    else:
        (tmp_path / "duplicate.yaml").write_text(
            yaml.safe_dump({**row, "canonical_name": " 合成定义 "}, allow_unicode=True)
        )
    (tmp_path / name).write_text(yaml.safe_dump(row, allow_unicode=True))
    with pytest.raises(ValueError):
        probe.inputs(tmp_path)


def test_ranking_math_and_target_eligibility(probe):
    docs = [{"name": "甲"}, {"name": "乙"}, {"name": "丙"}]
    ranked = probe.order([0.1, 0.9, 0.2], docs)
    assert ranked == [1, 2, 0]
    assert probe.metrics(ranked, docs, ["乙"])["recall_at_1"] == 1
    assert probe.metrics(ranked, docs, ["甲"])["reciprocal_rank"] == pytest.approx(1 / 3)
    assert probe.cosine([1.0, 0.0], [1.0, 0.0]) == 1
    for vectors in [([0.0], [0.0]), ([float("nan")], [1.0]), ([1.0], [1.0, 0.0])]:
        with pytest.raises(ValueError):
            probe.cosine(*vectors)
    with pytest.raises(ValueError):
        probe.metrics(ranked, docs, ["不存在"])
    with pytest.raises(ValueError):
        probe.order([0.1, float("inf"), 0.2], docs)


def test_model_files_match_lfs_or_git_blob(probe, tmp_path):
    assets = importlib.import_module("model_assets")
    target = tmp_path / "synthetic.bin"
    body = b"synthetic model bytes, not actual weights"
    target.write_bytes(body)
    sha = hashlib.sha256(body).hexdigest()
    lfs = {"size": len(body), "lfs": {"sha256": sha}}
    assert assets.verify(target, lfs)["sha256"] == sha
    blob = hashlib.sha1(f"blob {len(body)}\0".encode() + body).hexdigest()
    assert assets.verify(target, {"size": len(body), "blobId": blob})["sha256"] == sha
    target.write_bytes(b"X" * len(body))
    with pytest.raises(ValueError, match="SHA-256"):
        assets.verify(target, lfs)


def test_manifest_cannot_omit_weight_files_or_claim_an_unpinned_revision(probe, tmp_path):
    target = tmp_path / "manifest.json"
    target.write_text(
        json.dumps(
            {
                "kind": "embedder",
                "repo": "BAAI/bge-m3",
                "revision": "main",
                "directory": str(tmp_path),
                "files": {},
            }
        )
    )
    with pytest.raises(ValueError, match="complete expected"):
        probe.manifest(target, "embedder")


def test_fetch_never_resolves_mutable_main(probe, tmp_path):
    assets = importlib.import_module("model_assets")
    with pytest.raises(ValueError, match="explicit"):
        assets.fetch("embedder", "main", tmp_path)
