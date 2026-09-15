"""Generate deployment-only credentials; never print or commit them."""

import os
import secrets
import sys
from pathlib import Path

# Windows consoles default to cp1252 and would fail on the Chinese success message,
# reporting a non-zero exit for a run that already wrote .env.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

root = Path(__file__).resolve().parents[1]
target = root / ".env"
if target.exists():
    raise SystemExit(".env 已存在，未覆盖。")
password = secrets.token_hex(24)
values = {
    "POSTGRES_PASSWORD": password,
    "DATABASE_URL": f"postgresql+psycopg://memoir:{password}@localhost:55432/memoir",
    "REVIEWER_TOKEN": secrets.token_urlsafe(36),
    "S3_ACCESS_KEY": "memoir" + secrets.token_hex(8),
    "S3_SECRET_KEY": secrets.token_urlsafe(36),
}
lines = []
for line in (root / ".env.example").read_text().splitlines():
    key = line.split("=", 1)[0]
    lines.append(f"{key}={values[key]}" if key in values else line)
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as file:
    file.write("\n".join(lines) + "\n")
print("已创建 .env（权限 0600）。审核者令牌在该文件中，请勿提交到 Git。")
