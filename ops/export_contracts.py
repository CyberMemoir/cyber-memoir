import json
from pathlib import Path

from cyber_memoir.api.main import app

root = Path(__file__).resolve().parents[1]
target = root / "packages/contracts/openapi.json"
target.parent.mkdir(parents=True, exist_ok=True)
# Explicit UTF-8: the schema carries Chinese, and write_text would otherwise use the locale
# encoding, which fails on a Windows default of cp1252.
target.write_text(
    json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print("Exported packages/contracts/openapi.json")
