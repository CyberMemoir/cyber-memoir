"""Synthetic provider tests; these prove cache contracts, not real model speed."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from cyber_memoir.adapters import inference


@pytest.fixture
def provider(monkeypatch):
    cfg = SimpleNamespace(
        embedding_backend="local", embedding_model="synthetic", embedding_device="cpu", embedding_threads=4
    )
    monkeypatch.setattr(inference, "settings", lambda: cfg)
    calls, active, peak = [], [0], [0]
    lock = threading.Lock()

    class Dense:
        def __init__(self, texts):
            self.texts = texts

        def tolist(self):
            return [[float(len(text))] + [0.0] * 1023 for text in self.texts]

    class Model:
        def encode(self, texts, **kwargs):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
                calls.append(list(texts))
            time.sleep(0.005)
            with lock:
                active[0] -= 1
            return {"dense_vecs": Dense(texts)}

    monkeypatch.setattr(inference, "embedder", lambda: Model())
    inference._QUERY_VECTORS.clear()
    yield cfg, calls, peak
    inference._QUERY_VECTORS.clear()


def test_same_concurrent_query_is_computed_once(provider):
    _, calls, peak = provider
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(inference.embed_query, ["synthetic query"] * 6))
    assert len(calls) == 1 and peak[0] == 1
    assert all(value == values[0] for value in values)
    values[0][0] = -123
    assert inference.embed_query("synthetic query")[0] > 0


def test_different_queries_still_serialize_and_document_batches_bypass_cache(provider):
    _, calls, peak = provider
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(inference.embed_query, [f"query {i}" for i in range(6)]))
    assert len(calls) == 6 and peak[0] == 1
    inference.embed(["query 0", "query 1"])
    inference.embed(["query 0", "query 1"])
    assert len(calls) == 8 and len(inference._QUERY_VECTORS) == 6


@pytest.mark.parametrize("field", ["embedding_model", "embedding_device", "embedding_threads"])
def test_configuration_change_cannot_reuse_vector(provider, field):
    cfg, calls, _ = provider
    inference.embed_query("synthetic")
    setattr(cfg, field, 2 if field == "embedding_threads" else "different")
    inference.embed_query("synthetic")
    assert len(calls) == 2


def test_provider_replacement_cannot_reuse_vector(provider, monkeypatch):
    _, calls, _ = provider
    inference.embed_query("synthetic")
    original = inference.embedder
    monkeypatch.setattr(inference, "embedder", lambda: original())
    inference.embed_query("synthetic")
    assert len(calls) == 2


def test_expiry_lru_and_bound(provider, monkeypatch):
    _, calls, _ = provider
    now = [1.0]
    monkeypatch.setattr(inference.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(inference, "_QUERY_VECTOR_LIMIT", 2)
    inference.embed_query("one")
    inference.embed_query("two")
    inference.embed_query("one")
    inference.embed_query("three")
    assert len(calls) == 3 and len(inference._QUERY_VECTORS) == 2
    inference.embed_query("two")
    assert len(calls) == 4
    now[0] += inference._QUERY_VECTOR_TTL
    inference.embed_query("two")
    assert len(calls) == 5


def test_disabled_backend_never_serves_cached_vector(provider):
    cfg, calls, _ = provider
    inference.embed_query("synthetic")
    cfg.embedding_backend = "disabled"
    assert inference.embed_query("synthetic") is None
    assert len(calls) == 1


def test_invalid_vector_is_never_cached(provider, monkeypatch):
    monkeypatch.setattr(inference, "_encode", lambda *args: (_ for _ in ()).throw(ValueError("invalid")))
    with pytest.raises(ValueError):
        inference.embed_query("synthetic")
    assert not inference._QUERY_VECTORS


def test_changed_query_requires_encoding_even_if_vectors_happen_to_match(provider):
    _, calls, _ = provider
    assert inference.embed_query("same length A") == inference.embed_query("same length B")
    assert len(calls) == 2


@pytest.mark.parametrize(
    "bad", [[], [[1.0] * 1023], [[1.0] * 1024] * 2, [[float("nan")] * 1024], [[float("inf")] * 1024]]
)
def test_malformed_query_output_is_checked_before_caching(provider, monkeypatch, bad):
    attempts = []

    class Dense:
        def tolist(self):
            return bad if len(attempts) == 1 else [[1.0] * 1024]

    class Model:
        def encode(self, texts, **kwargs):
            attempts.append(texts)
            return {"dense_vecs": Dense()}

    monkeypatch.setattr(inference, "embedder", lambda: Model())
    with pytest.raises(ValueError, match="Invalid BGE-M3"):
        inference.embed_query("synthetic")
    assert not inference._QUERY_VECTORS
    assert inference.embed_query("synthetic") == [1.0] * 1024
    assert len(attempts) == 2
