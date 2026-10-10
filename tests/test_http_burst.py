import importlib
from pathlib import Path

import pytest


@pytest.fixture
def module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("http_burst")


def test_nearest_rank_small_sample_p95_is_not_extrapolated(module):
    result = module.timing_summary([6, 1, 5, 2, 4, 3])
    assert result == {"n": 6, "median": 3.5, "p95_nearest_rank": 6, "max": 6}


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")], [-1]])
def test_invalid_timings_are_refused(module, values):
    with pytest.raises(ValueError):
        module.timing_summary(values)


@pytest.mark.parametrize("change", ["paired", "no_trace", "disabled"])
def test_burst_context_cannot_claim_normal_model_measurements(module, change):
    context = {
        "models": {
            role: {
                "enabled": role != "llm",
                "identifier": "synthetic-model" if role != "llm" else "disabled",
                **({"sha256": "0" * 64} if role != "llm" else {}),
            }
            for role in ["embedding", "reranker", "llm"]
        },
        "configuration": {"inference_tracing": True, "paired_cpu_profiling": False},
    }
    module.validate_burst_context(context)
    if change == "paired":
        context["configuration"]["paired_cpu_profiling"] = True
    elif change == "no_trace":
        context["configuration"]["inference_tracing"] = False
    else:
        context["models"]["embedding"] = {"enabled": False, "identifier": "disabled"}
    with pytest.raises(ValueError):
        module.validate_burst_context(context)
