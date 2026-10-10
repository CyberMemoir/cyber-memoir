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


def test_failed_initialization_releases_ownership(tmp_path, monkeypatch):
    path = tmp_path / "broken.sqlite"
    original = module.sqlite3.connect

    def broken(*args, **kwargs):
        raise module.sqlite3.OperationalError("synthetic disk failure")

    monkeypatch.setattr(module.sqlite3, "connect", broken)
    with pytest.raises(module.sqlite3.OperationalError):
        Checkpoint(path, {"gold": "frozen"})
    monkeypatch.setattr(module.sqlite3, "connect", original)
    with Checkpoint(path, {"gold": "frozen"}) as recovered:
        recovered.save(1, {"query": "synthetic"})


def test_invalidated_journal_cannot_reuse_cases_even_if_context_matches(tmp_path):
    path = tmp_path / "invalid.sqlite"
    with Checkpoint(path, {"gold": "frozen"}) as first:
        first.save(1, {"query": "synthetic"})
        first.invalidate("ContextChanged")
    with pytest.raises(ValueError, match="invalidated"):
        Checkpoint(path, {"gold": "frozen"})


def test_snapshot_sees_membership_and_embedded_evidence_not_just_claim_links():
    text = "original"

    def respond(request):
        if request.url.path == "/v1/universe":
            return httpx.Response(200, json={"galaxies": [{"meme_id": "m1"}]})
        if request.url.path == "/v1/memes/m1":
            return httpx.Response(200, json={"id": "m1", "evidence": [{"id": "e1", "text": text}]})
        return httpx.Response(200, json={"id": "e1", "text": text})

    with httpx.Client(base_url="http://fixture", transport=httpx.MockTransport(respond)) as client:
        first = module.public_snapshot(client)
        text = "changed"
        assert first != module.public_snapshot(client)
