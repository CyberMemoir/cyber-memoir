#!/usr/bin/env python3
"""Put hand-downloaded reranker weights where the containers can find them.

    python ops/install_reranker.py models/bge-reranker-v2-m3

INSTALL_MODELS bakes the model libraries into the image but not the 2.3GB of
weights, so the first search that needs the reranker downloads them - and from here
huggingface.co runs at roughly 40 bytes a second, inside a request that dies before
it finishes. Downloading by hand and copying the directory in is the way out.

Checks the files first, then copies into the `models` volume through the api
container, where the worker sees them too. Prints the .env line to point the app at
the directory rather than at the hub id.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# What transformers needs to load an XLM-RoBERTa cross-encoder from a directory,
# with the smallest size each file has any business being.
REQUIRED = {
    "config.json": 500,
    "model.safetensors": 2_000_000_000,
    "tokenizer.json": 10_000_000,
    "tokenizer_config.json": 200,
    "sentencepiece.bpe.model": 4_000_000,
    "special_tokens_map.json": 100,
}
TARGET = "/app/.models"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", help="下载好的权重目录")
    parser.add_argument("--container", default="cyber-memoir-api-1")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    source = Path(args.directory).resolve()
    if not source.is_dir():
        raise SystemExit("不是目录：%s" % source)

    problems = []
    for name, floor in REQUIRED.items():
        path = source / name
        if not path.exists():
            problems.append("缺少 %s" % name)
        elif path.stat().st_size < floor:
            problems.append(
                "%s 只有 %.1f MB，像是没下完或下到了错误页"
                % (name, path.stat().st_size / 1e6)
            )
    if (source / "config.json").exists():
        try:
            config = json.loads((source / "config.json").read_text(encoding="utf-8"))
            if config.get("model_type") != "xlm-roberta":
                problems.append("config.json 的 model_type 是 %r，不像 bge-reranker-v2-m3"
                                % config.get("model_type"))
        except ValueError:
            problems.append("config.json 不是合法 JSON —— 多半下到了一个 HTML 页面")
    for line in problems:
        print("x %s" % line)
    if problems:
        return 1
    total = sum(p.stat().st_size for p in source.iterdir() if p.is_file())
    print("权重齐全，共 %.2f GB" % (total / 1e9))
    if args.check_only:
        return 0

    print("复制进 %s:%s/%s …" % (args.container, TARGET, source.name))
    done = subprocess.run(
        ["docker", "cp", str(source), "%s:%s/" % (args.container, TARGET)],
        capture_output=True, text=True,
    )
    if done.returncode:
        print("x docker cp 失败：%s" % (done.stderr or done.stdout).strip()[:300])
        return 1
    print("完成。接着改 .env：")
    print("  RERANKER_MODEL=%s/%s" % (TARGET, source.name))
    print("  HF_HUB_OFFLINE=1")
    print("再重启：docker compose --env-file .env -f ops/compose/compose.yml up -d api worker")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
