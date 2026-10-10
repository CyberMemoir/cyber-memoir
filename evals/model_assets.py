"""Fetch explicitly pinned public BGE snapshots, then verify every selected byte."""

import argparse
import hashlib
import json
import re
from pathlib import Path

import httpx

MODELS = {
    "reranker": ("BAAI/bge-reranker-v2-m3", "model.safetensors"),
    "embedder": ("BAAI/bge-m3", "pytorch_model.bin"),
}
COMMON = {
    "config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "sentencepiece.bpe.model",
}


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def verify(path: Path, remote: dict) -> dict:
    size = path.stat().st_size
    if size != remote["size"]:
        raise ValueError(f"incomplete model file: {path.name}")
    actual = digest(path)
    if remote.get("lfs"):
        if actual != remote["lfs"]["sha256"]:
            raise ValueError(f"model SHA-256 mismatch: {path.name}")
    else:
        value = hashlib.sha1(f"blob {size}\0".encode())
        value.update(path.read_bytes())
        if value.hexdigest() != remote["blobId"]:
            raise ValueError(f"model Git blob mismatch: {path.name}")
    return {"bytes": size, "sha256": actual}


def fetch(kind: str, revision: str, cache: Path) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("model revision must be an explicit 40-character commit SHA, not main")
    repo, weights = MODELS[kind]
    names = COMMON | {weights}
    if kind == "embedder":
        names |= {"colbert_linear.pt", "sparse_linear.pt"}
    with httpx.Client(timeout=30, trust_env=False) as client:
        response = client.get(
            f"https://huggingface.co/api/models/{repo}/revision/{revision}", params={"blobs": "true"}
        )
        response.raise_for_status()
        data = response.json()
    if data["sha"] != revision:
        raise ValueError("Hub returned a different model revision")
    files = {row["rfilename"]: row for row in data["siblings"] if row["rfilename"] in names}
    if set(files) != names:
        raise ValueError(f"incomplete upstream snapshot: {sorted(names - set(files))}")
    from huggingface_hub import snapshot_download

    # No auth, no implicit user token, no custom endpoint, no remote Python files.
    directory = Path(
        snapshot_download(
            repo_id=repo,
            revision=revision,
            token=False,
            endpoint="https://huggingface.co",
            cache_dir=str(cache),
            allow_patterns=sorted(names),
            max_workers=2,
        )
    ).resolve()
    checked = {name: verify(directory / name, remote) for name, remote in sorted(files.items())}
    config = json.loads((directory / "config.json").read_text())
    if config.get("model_type") != "xlm-roberta":
        raise ValueError("unexpected BGE architecture")
    return {"kind": kind, "repo": repo, "revision": revision, "directory": str(directory), "files": checked}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=MODELS, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.manifest.suffix != ".json" or args.manifest.exists():
        parser.error("manifest must be a new .json file")
    result = fetch(args.kind, args.revision, args.cache.resolve())
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    with args.manifest.open("x", encoding="utf-8") as output:
        json.dump(result, output, ensure_ascii=False, sort_keys=True, indent=2)
        output.write("\n")
    print(
        json.dumps(
            {"repo": result["repo"], "revision": result["revision"], "manifest": str(args.manifest)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
