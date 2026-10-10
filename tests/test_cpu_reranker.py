"""Synthetic algorithm/dispatch tests; real parity is measured in the isolated probe."""

import contextlib
import math
import sys
from types import SimpleNamespace

import pytest

from cyber_memoir.adapters.cpu_reranker import cpu_reranker, score_cpu


@pytest.fixture
def ranker(monkeypatch):
    calls, preparation, tokenization = [], [], []

    def argsort(values):
        return sorted(range(len(values)), key=lambda i: values[i])

    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(argsort=argsort, exp=math.exp))
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(no_grad=contextlib.nullcontext))

    def prepare(tokenizer, query, passage, **kwargs):
        preparation.append(kwargs)
        return {"input_ids": query + passage}

    class Batch(dict):
        def to(self, device):
            assert device == "cpu"
            return self

    def pad(tokenizer, rows, **kwargs):
        return Batch(rows=rows)

    monkeypatch.setitem(
        sys.modules,
        "FlagEmbedding.utils.tokenizer_compat",
        SimpleNamespace(prepare_for_model_compat=prepare, pad_with_compat=pad),
    )

    class Values:
        def __init__(self, values):
            self.values = values

        def view(self, shape):
            return self

        def float(self):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self

        def tolist(self):
            return self.values

    class Model:
        def to(self, device):
            assert device == "cpu"

        def eval(self):
            pass

        def __call__(self, rows, return_dict):
            calls.append(rows)
            return SimpleNamespace(logits=Values([len(row["input_ids"]) for row in rows]))

    def tokenize(texts, **kwargs):
        tokenization.append(kwargs)
        return {"input_ids": [[1] * min(len(text), kwargs["max_length"]) for text in texts]}

    model = SimpleNamespace(
        batch_size=2,
        max_length=512,
        query_max_length=None,
        normalize=False,
        tokenizer=tokenize,
        model=Model(),
        use_fp16=True,
    )
    return model, calls, preparation, tokenization


def test_single_pass_and_original_order_restoration(ranker):
    model, calls, preparation, tokenization = ranker
    assert score_cpu(model, [["q", "a"], ["q", "longest"], ["q", "mid"]], normalize=False) == [2, 8, 4]
    assert [len(batch) for batch in calls] == [2, 1]
    assert model.use_fp16 is False
    assert all(p == {"truncation": "only_second", "max_length": 512, "padding": False} for p in preparation)
    assert tokenization[0]["max_length"] == 384
    assert tokenization[1]["max_length"] == 512


def test_normalization_and_single_pair(ranker):
    model, *_ = ranker
    assert score_cpu(model, ["q", "a"], normalize=True) == [1 / (1 + math.exp(-2))]
    model.normalize = True
    assert score_cpu(model, [["q", "a"]]) == [1 / (1 + math.exp(-2))]


@pytest.mark.parametrize(
    "options",
    [
        {"batch_size": 0},
        {"batch_size": True},
        {"max_length": 0},
        {"query_max_length": -1},
        {"device": "cuda"},
    ],
)
def test_invalid_options_do_not_run_model(ranker, options):
    model, calls, *_ = ranker
    with pytest.raises(ValueError):
        score_cpu(model, [["q", "a"]], **options)
    assert not calls


def test_empty_batch_never_runs_model(ranker):
    model, calls, *_ = ranker
    assert score_cpu(model, []) == []
    assert not calls


def test_runtime_errors_are_not_swallowed_or_retried_forever(ranker):
    model, calls, *_ = ranker

    class Failing:
        def to(self, device):
            pass

        def eval(self):
            pass

        def __call__(self, **kwargs):
            calls.append("failed")
            raise RuntimeError("synthetic model error")

    model.model = Failing()
    with pytest.raises(RuntimeError, match="synthetic"):
        score_cpu(model, [["q", "a"]])
    assert calls == ["failed"]


def test_other_device_delegates_to_original_implementation(monkeypatch):
    calls = []

    class Base:
        def compute_score_single_gpu(self, pairs, **options):
            calls.append(options)
            return "upstream"

    model = cpu_reranker(Base)
    assert model.compute_score_single_gpu([["q", "a"]], device="mps") == "upstream"
    assert calls == [{"device": "mps"}]
