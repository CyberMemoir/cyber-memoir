"""Disabled providers have no invented artifact hash; paced runs keep timing scope explicit."""

import importlib
from pathlib import Path

import pytest


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("run")


def test_disabled_provider_context_needs_no_fictional_weights(runner):
    context = {
        "models": {
            role: {"enabled": False, "identifier": "disabled"} for role in ["embedding", "reranker", "llm"]
        },
        "configuration": {"snapshot": "synthetic-only"},
    }
    runner.validate_context(context)


@pytest.mark.parametrize(
    "mutation", ["missing_role", "disabled_with_hash", "active_without_hash", "nonboolean"]
)
def test_provider_context_cannot_hide_missing_or_contradictory_identity(runner, mutation):
    models = {role: {"enabled": False, "identifier": "disabled"} for role in ["embedding", "reranker", "llm"]}
    if mutation == "missing_role":
        models.pop("embedding")
    elif mutation == "disabled_with_hash":
        models["embedding"]["sha256"] = "0" * 64
    elif mutation == "active_without_hash":
        models["embedding"] = {"enabled": True, "identifier": "synthetic-model"}
    else:
        models["embedding"]["enabled"] = "false"
    with pytest.raises(ValueError):
        runner.validate_context({"models": models, "configuration": {"snapshot": "synthetic-only"}})


def test_pacing_is_accounted_separately_from_http_time(runner, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(runner.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))

    class Client:
        def post(self, path, **kwargs):
            now[0] += 0.2
            return path

    client = runner.PacedClient(Client(), 1.0)
    assert client.post("/first") == "/first"
    assert client.post("/second") == "/second"
    assert client.sleep_seconds == pytest.approx(0.8)
    assert client.post_seconds == pytest.approx(0.4)
