"""Reranking is serialised, because the alternative measured worse than slow.

Three searches at once left the API pegged and finished none of them inside thirty
seconds; the proxy in front of it answered 500 to requests that never reached
uvicorn. One at a time is slower for the second caller and it completes.
"""

import threading
import time

import pytest

from cyber_memoir.adapters import inference


class Recorder:
    """Stands in for the cross-encoder and remembers how many ran at once."""

    def __init__(self):
        self.live = 0
        self.peak = 0
        self.calls = 0
        self.guard = threading.Lock()

    def compute_score(self, pairs, normalize=True):
        with self.guard:
            self.live += 1
            self.peak = max(self.peak, self.live)
            self.calls += 1
        time.sleep(0.05)
        with self.guard:
            self.live -= 1
        return [0.5] * len(pairs)


def run_together(count: int, *, unique=False) -> list:
    out: list = [None] * count
    threads = [
        threading.Thread(
            target=lambda i=i: out.__setitem__(i, inference.rerank(f"q{i}" if unique else "q", ["a", "b"]))
        )
        for i in range(count)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a reranking thread never finished"
    return out


def test_only_one_rerank_runs_at_a_time(monkeypatch, env):
    recorder = Recorder()
    monkeypatch.setattr(inference, "reranker", lambda: recorder)
    monkeypatch.setattr(inference, "settings", lambda: type("S", (), {"reranker_backend": "local"})())

    results = run_together(6)

    assert recorder.calls == 1, "identical queued callers reuse validated scores"
    assert recorder.peak == 1, "two reranks overlapped: %d" % recorder.peak
    assert all(scores == [0.5, 0.5] for scores in results)


def test_a_queued_caller_is_never_handed_uncalibrated_scores(monkeypatch, env):
    """Waiting is the price. Returning None under load would drop the retrieval floor."""
    recorder = Recorder()
    monkeypatch.setattr(inference, "reranker", lambda: recorder)
    monkeypatch.setattr(inference, "settings", lambda: type("S", (), {"reranker_backend": "local"})())

    assert all(scores is not None for scores in run_together(4))


def test_the_backend_switch_still_short_circuits(monkeypatch, env):
    monkeypatch.setattr(inference, "settings", lambda: type("S", (), {"reranker_backend": "disabled"})())
    assert inference.rerank("q", ["a"]) is None


@pytest.fixture(autouse=True)
def clear_scores():
    if hasattr(inference, "_SCORES"):
        inference._SCORES.clear()
    yield
    if hasattr(inference, "_SCORES"):
        inference._SCORES.clear()


def test_different_concurrent_queries_still_serialize(monkeypatch, env):
    recorder = Recorder()
    monkeypatch.setattr(inference, "reranker", lambda: recorder)
    monkeypatch.setattr(inference, "settings", lambda: type("S", (), {"reranker_backend": "local"})())
    assert all(scores == [0.5, 0.5] for scores in run_together(6, unique=True))
    assert recorder.calls == 6
    assert recorder.peak == 1


def test_cache_does_not_reuse_changed_inputs_or_mutable_results(monkeypatch, env):
    recorder = Recorder()
    monkeypatch.setattr(inference, "reranker", lambda: recorder)
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    from cyber_memoir.config import settings

    settings.cache_clear()
    first = inference.rerank("q", ["a", "b"])
    first[0] = 99
    assert inference.rerank("q", ["a", "b"]) == [0.5, 0.5]
    inference.rerank("changed query", ["a", "b"])
    inference.rerank("q", ["b", "a"])
    inference.rerank("q", ["changed evidence", "b"])
    assert recorder.calls == 4
    monkeypatch.setenv("RERANKER_MODEL", "different-snapshot")
    settings.cache_clear()
    inference.rerank("q", ["a", "b"])
    assert recorder.calls == 5
    monkeypatch.setattr(inference, "_SCORE_TTL", 0)
    inference.rerank("q", ["a", "b"])
    assert recorder.calls == 6


@pytest.mark.parametrize("scores", [[float("nan")], [float("inf")], [0.1, 0.2], [-0.1], [1.1]])
def test_invalid_normalized_scores_are_never_cached(monkeypatch, env, scores):
    class Invalid:
        def compute_score(self, *args, **kwargs):
            return scores

    monkeypatch.setattr(inference, "reranker", lambda: Invalid())
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    from cyber_memoir.config import settings

    settings.cache_clear()
    with pytest.raises(ValueError, match="Invalid reranker scores"):
        inference.rerank("q", ["a"])
    assert not inference._SCORES


def test_score_cache_is_bounded(monkeypatch, env):
    recorder = Recorder()
    monkeypatch.setattr(inference, "reranker", lambda: recorder)
    monkeypatch.setattr(inference, "settings", lambda: type("S", (), {"reranker_backend": "local"})())
    monkeypatch.setattr(inference, "_SCORE_LIMIT", 2)
    for query in ("a", "b", "c", "a"):
        inference.rerank(query, ["text"])
    assert recorder.calls == 4
    assert len(inference._SCORES) == 2
