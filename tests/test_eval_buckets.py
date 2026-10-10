import importlib.util
import json
from hashlib import sha256
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "score_buckets", Path(__file__).resolve().parents[1] / "evals/score_buckets.py"
)
scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scorer)


def inputs(tmp_path, rows, cases, **extra):
    gold = tmp_path / "gold.jsonl"
    raw = "".join(json.dumps(row) + "\n" for row in rows)
    gold.write_text(raw, encoding="utf-8")
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"cases": cases, "gold_sha256": sha256(raw.encode()).hexdigest(), **extra}),
        encoding="utf-8",
    )
    return str(report), str(gold)


def test_partial_failed_report_cannot_recalculate_successful_bucket_metrics(tmp_path, capsys):
    paths = inputs(
        tmp_path,
        [{"query": "a", "bucket": "description", "query_source": "human"}],
        [{"query": "a", "recall_at_10": 1, "reciprocal_rank": 1}],
        failed=[{"query": "b", "error": "HTTPError"}],
    )
    assert scorer.main(*paths) == 1
    assert "指标" in capsys.readouterr().out


def test_missing_cases_or_changed_gold_are_not_complete_reports(tmp_path):
    paths = inputs(
        tmp_path,
        [{"query": "a", "bucket": "canonical"}, {"query": "b", "bucket": "canonical"}],
        [{"query": "a", "recall_at_10": 1, "reciprocal_rank": 1}],
    )
    assert scorer.main(*paths) == 1
    Path(paths[1]).write_text(Path(paths[1]).read_text() + "\n", encoding="utf-8")
    assert scorer.main(*paths) == 1


def test_unmarked_descriptions_are_not_called_human_and_all_buckets_are_reported(tmp_path, capsys):
    rows = [{"query": "a", "bucket": "description"}, {"query": "b", "bucket": "polysemy"}]
    cases = [{"query": q, "recall_at_10": 1, "reciprocal_rank": 1} for q in ["a", "b"]]
    assert scorer.main(*inputs(tmp_path, rows, cases)) == 0
    output = capsys.readouterr().out
    assert "description_unattributed" in output
    assert "polysemy" in output
    assert "人工描述的 1 条" not in output
