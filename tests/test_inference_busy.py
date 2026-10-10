"""Bounded misses, immediate validated cache hits and truthful busy API responses."""

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from cyber_memoir.adapters import inference
from cyber_memoir.config import settings
from cyber_memoir.search.indexing import index_meme


@pytest.fixture
def fake(monkeypatch):
    cfg = SimpleNamespace(
        reranker_backend="local",
        reranker_model="synthetic",
        reranker_device="cpu",
        reranker_threads=4,
        embedding_backend="local",
        embedding_model="synthetic",
        embedding_device="cpu",
        embedding_threads=4,
        inference_queue_timeout_seconds=0,
    )
    monkeypatch.setattr(inference, "settings", lambda: cfg)
    calls = []

    class Dense:
        def tolist(self):
            return [[1.0] + [0.0] * 1023]

    class Model:
        def compute_score(self, pairs, **kwargs):
            calls.append("rerank")
            return [0.5] * len(pairs)

        def encode(self, texts, **kwargs):
            calls.append("embed")
            return {"dense_vecs": Dense()}

    monkeypatch.setattr(inference, "reranker", lambda: Model())
    monkeypatch.setattr(inference, "embedder", lambda: Model())
    inference._SCORES.clear()
    inference._QUERY_VECTORS.clear()
    yield cfg, calls
    inference._SCORES.clear()
    inference._QUERY_VECTORS.clear()


@pytest.mark.parametrize("kind", ["rerank", "embed"])
def test_cached_query_bypasses_busy_unrelated_model_slot(fake, kind):
    cfg, calls = fake
    query = (
        (lambda text: inference.rerank(text, ["synthetic passage"]))
        if kind == "rerank"
        else inference.embed_query
    )
    lock = inference._RERANK if kind == "rerank" else inference._EMBED
    expected = query("cached")
    with lock:
        assert query("cached") == expected
        with pytest.raises(inference.InferenceBusy):
            query("miss")
    assert calls == ["rerank" if kind == "rerank" else "embed"]
    assert query("miss") == expected


@pytest.mark.parametrize("kind", ["rerank", "embed"])
def test_waiting_does_not_load_or_compute_after_admission_timeout(fake, kind):
    _, calls = fake
    query = (
        (lambda: inference.rerank("new", ["passage"]))
        if kind == "rerank"
        else lambda: inference.embed_query("new")
    )
    lock = inference._RERANK if kind == "rerank" else inference._EMBED
    with lock:
        with pytest.raises(inference.InferenceBusy):
            query()
    assert not calls


@pytest.mark.parametrize("path", ["/v1/search", "/v1/answers"])
def test_busy_is_503_not_degraded_unscored_success(client, prepared, env, monkeypatch, path):
    item = prepared(name="合成忙碌测试")
    with Session(env) as db:
        index_meme(db, item["meme_id"])
        db.commit()
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    monkeypatch.setenv("INFERENCE_QUEUE_TIMEOUT_SECONDS", "0")
    settings.cache_clear()
    inference._SCORES.clear()
    with inference._RERANK:
        response = client.post(path, json={"query": "合成忙碌测试"})
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "inference_busy" and body["retry_after_seconds"] == 1
    assert response.headers["Retry-After"] == "1" and response.headers["Cache-Control"] == "no-store"
    assert "claims" not in body and "items" not in body


def test_vector_busy_propagates_without_falling_back_to_unscored_channel(client, prepared, monkeypatch):
    from cyber_memoir.search import retrieval

    prepared(name="合成向量忙碌")
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    settings.cache_clear()

    def busy(*args):
        raise inference.InferenceBusy("synthetic busy")

    monkeypatch.setattr(retrieval, "embed_query", busy)
    response = client.post("/v1/search", json={"query": "合成向量忙碌"})
    assert response.status_code == 503 and response.json()["code"] == "inference_busy"


def test_admitted_model_errors_release_slot(fake, monkeypatch):
    _, calls = fake

    class Broken:
        def compute_score(self, *args, **kwargs):
            raise RuntimeError("synthetic failure")

    monkeypatch.setattr(inference, "reranker", lambda: Broken())
    with pytest.raises(RuntimeError):
        inference.rerank("new", ["passage"])
    assert inference._RERANK.acquire(blocking=False)
    inference._RERANK.release()
    assert not inference._SCORES


@pytest.mark.parametrize("seconds", [-1, 61, float("nan"), float("inf")])
def test_invalid_admission_budget_is_rejected_at_configuration_load(seconds):
    from pydantic import ValidationError

    from cyber_memoir.config import Settings

    with pytest.raises(ValidationError):
        Settings(_env_file=None, inference_queue_timeout_seconds=seconds)


def test_offline_capacity_probe_declares_its_distinct_queue_budget(monkeypatch):
    import importlib
    from pathlib import Path

    from cyber_memoir.config import Settings

    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    module = importlib.import_module("model_probe")
    monkeypatch.setattr(module.os, "environ", {})
    monkeypatch.setitem(Settings.model_config, "env_file", Settings.model_config.get("env_file"))
    module.configure({"directory": "synthetic-embedder"}, {"directory": "synthetic-reranker"}, 4)
    assert module.os.environ["INFERENCE_QUEUE_TIMEOUT_SECONDS"] == "60"
