import hashlib
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from cyber_memoir.config import settings


@lru_cache
def client():
    cfg = settings()
    return boto3.client(
        "s3",
        endpoint_url=cfg.s3_endpoint,
        aws_access_key_id=cfg.s3_access_key,
        aws_secret_access_key=cfg.s3_secret_key,
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},
            proxies={},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 2},
        ),
    )


def put(data: bytes, content_type="application/json", temporary=False) -> tuple[str, str]:
    digest = hashlib.sha256(data).hexdigest()
    key = f"temporary/{uuid4()}/{digest}" if temporary else f"sha256/{digest[:2]}/{digest}"
    cfg = settings()
    if cfg.storage_backend == "local":
        path = Path(cfg.storage_path) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
    else:
        try:
            client().head_bucket(Bucket=cfg.s3_bucket)
        except ClientError as exc:
            if str(exc.response["Error"]["Code"]) not in ("404", "NoSuchBucket"):
                raise
            client().create_bucket(Bucket=cfg.s3_bucket)
        client().put_object(Bucket=cfg.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return key, digest


def get(key: str) -> bytes:
    if not key.startswith(("sha256/", "temporary/")) or ".." in key:
        raise ValueError("Invalid artifact key")
    cfg = settings()
    if cfg.storage_backend == "local":
        return (Path(cfg.storage_path) / key).read_bytes()
    return client().get_object(Bucket=cfg.s3_bucket, Key=key)["Body"].read()


def remove_temporary(key: str):
    if not key.startswith("temporary/") or ".." in key:
        raise ValueError("Only temporary media can be deleted by this operation")
    cfg = settings()
    if cfg.storage_backend == "local":
        (Path(cfg.storage_path) / key).unlink(missing_ok=True)
    else:
        client().delete_object(Bucket=cfg.s3_bucket, Key=key)
