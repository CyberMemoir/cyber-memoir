import json
from pathlib import Path

from cyber_memoir.api.main import app

root = Path(__file__).resolve().parents[1]
target = root / "packages/contracts/openapi.json"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
print("Exported packages/contracts/openapi.json")
