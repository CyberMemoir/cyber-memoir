"""Evidence-object export/import; restore only to an empty bucket."""

import hashlib
import json
import re
import sys
from pathlib import Path

from botocore.exceptions import ClientError

from cyber_memoir.adapters.storage import client, get, put
from cyber_memoir.config import settings


def keys():
    cfg = settings()
    if cfg.storage_backend == "local":
        root = Path(cfg.storage_path)
        return [str(p.relative_to(root)) for p in (root / "sha256").rglob("*") if p.is_file()]
    try:
        pages = client().get_paginator("list_objects_v2").paginate(Bucket=cfg.s3_bucket, Prefix="sha256/")
        return [x["Key"] for page in pages for x in page.get("Contents", [])]
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "NoSuchBucket":
            return []
        raise


def valid_key(key):
    if not re.fullmatch(r"sha256/[a-f0-9]{2}/[a-f0-9]{64}", key):
        raise ValueError("Unexpected artifact key in backup")


def export(directory: Path):
    manifest = []
    for key in keys():
        valid_key(key)
        data = get(key)
        digest = hashlib.sha256(data).hexdigest()
        if digest != key.split("/")[-1]:
            raise ValueError(f"Artifact integrity failure: {key}")
        path = directory / "objects" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        manifest.append({"key": key, "sha256": digest, "size": len(data)})
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return len(manifest)


def verify(directory: Path):
    manifest = json.loads((directory / "manifest.json").read_text())
    for item in manifest:
        valid_key(item["key"])
        data = (directory / "objects" / item["key"]).read_bytes()
        if (
            len(data) != item["size"]
            or hashlib.sha256(data).hexdigest() != item["sha256"]
            or item["sha256"] != item["key"].split("/")[-1]
        ):
            raise ValueError("Backup artifact integrity failure")
    return manifest


def restore(directory: Path):
    manifest = verify(directory)
    if keys():
        raise ValueError("Restore requires an empty evidence store; existing objects will not be overwritten")
    for item in manifest:
        key, _ = put((directory / "objects" / item["key"]).read_bytes())
        if key != item["key"]:
            raise ValueError("Restored key mismatch")
    return len(manifest)


if __name__ == "__main__":
    operation, directory = sys.argv[1:]
    result = {"export": export, "verify": verify, "restore": restore}[operation](Path(directory))
    print(f"{operation}: {len(result) if isinstance(result, list) else result} evidence objects")
