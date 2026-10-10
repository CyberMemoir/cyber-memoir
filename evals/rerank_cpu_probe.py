"""Paired actual-model profiling inside an owned evaluation API; no fake scores."""

import hashlib
import json
import math
import time


def attach(model, output):
    from FlagEmbedding.inference.reranker.encoder_only.base import BaseReranker

    if model.target_devices != ["cpu"]:
        raise ValueError("paired profiling requires the explicit CPU model")
    stream = output.open("x", encoding="utf-8")
    original = model.compute_score
    calls = []

    def observe(module, args, kwargs):
        calls.append(list(kwargs["input_ids"].shape))

    handle = model.model.register_forward_pre_hook(observe, with_kwargs=True)

    def measured(pairs, **options):
        calls.clear()
        began = time.perf_counter()
        reference = BaseReranker.compute_score_single_gpu(
            model, model.get_detailed_inputs(pairs), device="cpu", **options
        )
        baseline_seconds, baseline_shapes = time.perf_counter() - began, list(calls)
        calls.clear()
        began = time.perf_counter()
        actual = original(pairs, **options)
        optimized_seconds, optimized_shapes = time.perf_counter() - began, list(calls)
        values = [float(value) for value in actual]
        expected = [float(value) for value in reference]
        delta = max((abs(a - b) for a, b in zip(expected, values, strict=True)), default=0)
        valid = bool(delta == 0 and all(math.isfinite(x) for x in [*values, *expected]))
        stream.write(
            json.dumps(
                {
                    "pairs_sha256": hashlib.sha256(
                        json.dumps(pairs, ensure_ascii=False).encode()
                    ).hexdigest(),
                    "candidates": len(pairs),
                    "baseline_seconds": baseline_seconds,
                    "optimized_seconds": optimized_seconds,
                    "baseline_forward_shapes": baseline_shapes,
                    "optimized_forward_shapes": optimized_shapes,
                    "max_absolute_difference": delta,
                    "exact_parity": valid,
                },
                sort_keys=True,
            )
            + "\n"
        )
        stream.flush()
        if not valid:
            raise ValueError("CPU differential profiling found changed scores")
        return actual

    model.compute_score = measured
    # Hold hook and output until the process exits; this owned API's existing
    # inference lock serializes all calls. No shared production model is patched.
    return stream, handle
