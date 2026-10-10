"""Single-pass CPU adaptation of FlagEmbedding 1.4.2 BaseReranker.

Preserves pair preparation, truncation, length sorting, batch order and sigmoid.
Only omits the discarded batch-size probe; GPU paths remain upstream.
Upstream MIT copyright/permission: see THIRD_PARTY_NOTICES.md.
"""


def score_cpu(
    ranker,
    pairs,
    batch_size=None,
    query_max_length=None,
    max_length=None,
    normalize=None,
    device=None,
    **kwargs,
):
    import numpy as np
    import torch
    from FlagEmbedding.utils.tokenizer_compat import pad_with_compat, prepare_for_model_compat

    if device not in {None, "cpu"}:
        raise ValueError("single-pass scoring is CPU-only")
    if not pairs:
        return []
    if isinstance(pairs[0], str):
        pairs = [pairs]
    size = ranker.batch_size if batch_size is None else batch_size
    length = ranker.max_length if max_length is None else max_length
    qlength = (
        query_max_length
        if query_max_length is not None
        else (ranker.query_max_length if ranker.query_max_length is not None else length * 3 // 4)
    )
    if any(type(value) is not int or value < 1 for value in [size, length, qlength]):
        raise ValueError("batch size and token limits must be positive integers")
    normalized = ranker.normalize if normalize is None else normalize
    prepared = []
    for start in range(0, len(pairs), size):
        group = pairs[start : start + size]
        queries = ranker.tokenizer(
            [p[0] for p in group],
            return_tensors=None,
            add_special_tokens=False,
            max_length=qlength,
            truncation=True,
            **kwargs,
        )["input_ids"]
        passages = ranker.tokenizer(
            [p[1] for p in group],
            return_tensors=None,
            add_special_tokens=False,
            max_length=length,
            truncation=True,
            **kwargs,
        )["input_ids"]
        for query, passage in zip(queries, passages, strict=True):
            prepared.append(
                prepare_for_model_compat(
                    ranker.tokenizer,
                    query,
                    passage,
                    truncation="only_second",
                    max_length=length,
                    padding=False,
                )
            )
    order = np.argsort([-len(row["input_ids"]) for row in prepared])
    sorted_inputs = [prepared[i] for i in order]
    scores = []
    with torch.no_grad():
        ranker.use_fp16 = False
        ranker.model.to("cpu")
        ranker.model.eval()
        for start in range(0, len(sorted_inputs), size):
            inputs = pad_with_compat(
                ranker.tokenizer,
                sorted_inputs[start : start + size],
                padding=True,
                return_tensors="pt",
                **kwargs,
            ).to("cpu")
            output = ranker.model(**inputs, return_dict=True).logits.view(-1).float()
            scores.extend(output.cpu().numpy().tolist())
    restored = [scores[i] for i in np.argsort(order)]
    return [float(1 / (1 + np.exp(-value))) for value in restored] if normalized else restored


def cpu_reranker(base, *args, **kwargs):
    class SinglePassCpuReranker(base):
        def compute_score_single_gpu(self, pairs, **options):
            device = options.get("device")
            if device is not None and device != "cpu":
                return super().compute_score_single_gpu(pairs, **options)
            return score_cpu(self, pairs, **options)

    return SinglePassCpuReranker(*args, **kwargs)
