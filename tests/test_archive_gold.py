import importlib
from pathlib import Path

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("archive_gold")


def test_only_actual_public_identities_select_human_queries(module):
    rows, excluded = module.select_gold(
        {"records": [{"canonical_name": "合成公开", "aliases": ["合成别名"]}]},
        {"合成公开": ["合成描述"], "合成未发布": ["另一描述"]},
        {"negatives": [{"query": "未收录描述", "kind": "out_of_corpus"}]},
    )
    assert rows[0]["expected_names"] == ["合成公开"]
    assert rows[0]["query_source"] == "human"
    assert rows[1]["answerable"] is False
    assert excluded[0]["name"] == "合成未发布"


@pytest.mark.parametrize("query", ["合成公开", "合成别名"])
def test_public_surface_cannot_be_a_negative(module, query):
    with pytest.raises(ValueError, match="negative"):
        module.select_gold(
            {"records": [{"canonical_name": "合成公开", "aliases": ["合成别名"]}]},
            {},
            {"negatives": [{"query": query, "kind": "fabricated"}]},
        )


def test_duplicate_queries_are_refused_not_silently_reweighted(module):
    with pytest.raises(ValueError, match="duplicate"):
        module.select_gold({"records": [{"canonical_name": "合成公开"}]}, {"合成公开": ["重复", "重复"]}, {})
