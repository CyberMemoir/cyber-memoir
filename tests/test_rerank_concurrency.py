"""Reranking is serialised, because the alternative measured worse than slow.

Three searches at once left the API pegged and finished none of them inside thirty
seconds; the proxy in front of it answered 500 to requests that never reached
uvicorn. One at a time is slower for the second caller and it completes.
"""

import threading
import time

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


def run_together(count: int) -> list:
    out: list = [None] * count
    threads = [
        threading.Thread(target=lambda i=i: out.__setitem__(i, inference.rerank("q", ["a", "b"])))
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

    assert recorder.calls == 6, "every caller must still get a score"
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
