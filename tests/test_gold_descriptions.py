import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "gold_builder", Path(__file__).resolve().parents[1] / "evals/build_gold.py"
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_human_file_is_independent_and_unpublished_queries_are_excluded(tmp_path, monkeypatch):
    human = {"已发布合成梗": ["人工独立描述"], "未发布合成梗": ["未发布描述"]}
    path = tmp_path / "_descriptions.yaml"
    path.write_text(json.dumps(human, ensure_ascii=False), encoding="utf-8")
    original = path.read_bytes()
    (tmp_path / "_negatives.yaml").write_text("{}", encoding="utf-8")
    for name, published in (("已发布合成梗", True), ("未发布合成梗", False)):
        (tmp_path / f"{name}.yaml").write_text(
            json.dumps(
                {
                    "canonical_name": name,
                    "resolved": published,
                    "definition": "合成测试",
                    "gold": {"description": ["模型描述"], "description_source": "model"},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    out = tmp_path / "gold.jsonl"
    monkeypatch.setattr(builder, "CURATION", tmp_path)
    monkeypatch.setattr("sys.argv", ["build_gold", "--out", str(out)])
    assert builder.main() == 0
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [(r["query"], r["bucket"]) for r in rows] == [
        ("人工独立描述", "description"),
        ("模型描述", "description_model"),
    ]
    monkeypatch.setattr("sys.argv", ["build_gold", "--out", str(out), "--descriptions-only"])
    assert builder.main() == 0
    assert len(out.read_text(encoding="utf-8").splitlines()) == 1
    assert path.read_bytes() == original


def test_claiming_human_in_a_record_does_not_replace_independent_human_file(tmp_path, monkeypatch):
    (tmp_path / "_descriptions.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "_negatives.yaml").write_text("{}", encoding="utf-8")
    (tmp_path / "record.yaml").write_text(
        json.dumps(
            {
                "canonical_name": "合成来源标记测试",
                "resolved": True,
                "definition": "合成测试，非文化事实",
                "gold": {"description": ["自称人工的记录查询"], "description_source": "human"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out = tmp_path / "gold.jsonl"
    monkeypatch.setattr(builder, "CURATION", tmp_path)
    monkeypatch.setattr("sys.argv", ["build_gold", "--out", str(out)])
    assert builder.main() == 0
    row = json.loads(out.read_text(encoding="utf-8"))
    assert row["bucket"] == "description_unattributed"
    assert row["query_source"] == "unattributed"


def test_gold_output_cannot_replace_independent_input(tmp_path, monkeypatch):
    path = tmp_path / "_descriptions.yaml"
    path.write_text('{"合成梗": ["独立人工查询"]}', encoding="utf-8")
    original = path.read_bytes()
    monkeypatch.setattr(builder, "CURATION", tmp_path)
    monkeypatch.setattr("sys.argv", ["build_gold", "--out", str(path)])
    with pytest.raises(SystemExit) as error:
        builder.main()
    assert error.value.code == 2
    assert path.read_bytes() == original
