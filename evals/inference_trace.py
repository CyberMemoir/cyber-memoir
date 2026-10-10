"""Optional timing-only instrumentation for an owned, read-only evaluation process."""

import contextvars
import functools
import json
import threading
import time

REQUEST_ID = contextvars.ContextVar("memoir_eval_request_id", default=None)


class TimedLock:
    def __init__(self, lock, emit, stage):
        self.lock, self.emit, self.stage = lock, emit, stage

    def acquire(self, *args, **kwargs):
        began = time.perf_counter()
        acquired = self.lock.acquire(*args, **kwargs)
        try:
            self.emit(self.stage, time.perf_counter() - began, acquired)
        except BaseException:
            if acquired:
                self.lock.release()
            raise
        return acquired

    def release(self):
        self.lock.release()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()


class InferenceTrace:
    def __init__(self, path, inference):
        self.stream = path.open("x", encoding="utf-8")
        self.writer = threading.Lock()
        self.changes, self.models = [], []
        for name, stage in [("_EMBED", "embedding_lock_wait"), ("_RERANK", "reranker_lock_wait")]:
            self.replace(inference, name, TimedLock(getattr(inference, name), self.emit, stage))
        for name, stage in [("embed_query", "embedding_total"), ("rerank", "reranker_total")]:
            self.replace(inference, name, self.timed(getattr(inference, name), stage))
        for name, stage, method in [
            ("_load_embedder", "embedding", "encode"),
            ("_load_reranker", "reranker", "compute_score"),
        ]:
            self.replace(inference, name, self.loader(getattr(inference, name), stage, method))

    def replace(self, obj, name, value):
        self.changes.append((obj, name, getattr(obj, name)))
        setattr(obj, name, value)

    def emit(self, stage, seconds, ok, error=None):
        row = {"request_id": REQUEST_ID.get(), "stage": stage, "seconds": seconds, "ok": ok}
        if error:
            row["error_type"] = error
        with self.writer:
            self.stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            self.stream.flush()

    def timed(self, function, stage):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            began = time.perf_counter()
            if stage.endswith("_compute"):
                self.emit(stage + "_start", 0.0, True)
            try:
                value = function(*args, **kwargs)
            except BaseException as exc:
                self.emit(stage, time.perf_counter() - began, False, type(exc).__name__)
                raise
            self.emit(stage, time.perf_counter() - began, True)
            return value

        return wrapped

    def loader(self, function, stage, method):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            before = function.cache_info().misses
            began = time.perf_counter()
            try:
                model = function(*args, **kwargs)
            except BaseException as exc:
                self.emit(stage + "_load", time.perf_counter() - began, False, type(exc).__name__)
                raise
            if function.cache_info().misses != before:
                self.emit(stage + "_load", time.perf_counter() - began, True)
            if not any(existing is model for existing in self.models):
                self.models.append(model)
                self.replace(model, method, self.timed(getattr(model, method), stage + "_compute"))
            return model

        return wrapped

    def close(self):
        # Only close after all owned requests have finished, never mid-inference.
        for obj, name, original in reversed(self.changes):
            setattr(obj, name, original)
        self.changes.clear()
        self.stream.close()
