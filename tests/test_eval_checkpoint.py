import importlib.util
from pathlib import Path

import httpx
import pytest

spec = importlib.util.spec_from_file_location(
    "eval_checkpoint", Path(__file__).resolve().parents[1] / "evals/checkpoint.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Checkpoint = module.Checkpoint


def test_resume_keeps_only_committed_completed_cases(tmp_path):
    path = tmp_path / "audit.sqlite"
    context = {"gold": "frozen", "corpus": "revision-7", "model": "snapshot"}
    first = Checkpoint(path, context)
    first.save(1, {"query": "human description", "recall_at_10": 1})
    first.close()  # simulates stopping without a finished aggregate
    resumed = Checkpoint(path, context)
    assert resumed.get(1)["recall_at_10"] == 1
    assert resumed.get(2) is None
    resumed.save(2, {"query": "second", "recall_at_10": 0})
    resumed.finish(True)
    assert resumed.db.execute("SELECT status FROM run").fetchone()[0] == "complete"
    resumed.close()


@pytest.mark.parametrize("field", ["gold", "corpus", "model", "configuration", "runner"])
def test_changed_context_cannot_mix_results(tmp_path, field):
    path = tmp_path / "audit.sqlite"
    context = {key: "original" for key in ("gold", "corpus", "model", "configuration", "runner")}
    first = Checkpoint(path, context)
    first.save(1, {"query": "original"})
    first.close()
    with pytest.raises(ValueError, match="context changed"):
        Checkpoint(path, {**context, field: "changed"})


def test_second_worker_cannot_own_same_journal(tmp_path):
    path = tmp_path / "audit.sqlite"
    first = Checkpoint(path, {"gold": "original"})
    try:
        with pytest.raises(OSError):
            Checkpoint(path, {"gold": "original"})
    finally:
        first.close()


def test_public_snapshot_binds_cited_evidence_content():
    evidence = {"id": "e1", "text": "original", "verified": True}

    def respond(request):
        if request.url.path == "/v1/universe":
            payload = {"galaxies": [{"meme_id": "m1"}]}
        elif request.url.path == "/v1/memes/m1":
            payload = {"id": "m1", "claims": [{"evidence_ids": ["e1"]}]}
        else:
            assert request.url.path == "/v1/evidence/e1"
            payload = evidence
        return httpx.Response(200, json=payload)

    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
        first = module.public_snapshot(client)
        assert first == module.public_snapshot(client)
        evidence["text"] = "changed"
        assert first != module.public_snapshot(client)
