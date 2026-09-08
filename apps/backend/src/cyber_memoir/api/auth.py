import hashlib
import secrets

from fastapi import Header, HTTPException

from cyber_memoir.config import settings


def reviewer(authorization: str = Header(default="")):
    token = settings().reviewer_token
    if not token or not secrets.compare_digest(authorization, f"Bearer {token}"):
        raise HTTPException(401, "需要审核者令牌")
    return "reviewer:" + hashlib.sha256(token.encode()).hexdigest()[:12]


def submitter(authorization: str = Header(default="")):
    cfg = settings()
    if cfg.submitter_token and not any(
        secrets.compare_digest(authorization, f"Bearer {token}")
        for token in (cfg.submitter_token, cfg.reviewer_token)
        if token
    ):
        raise HTTPException(401, "需要提交者令牌")
