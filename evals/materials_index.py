"""Where an evidence_map placeholder's text lives on disk.

Shared by load_curation.py, which posts that text as Evidence, and validate_curation.py,
which checks drafted claims against it. One copy, so the two cannot disagree about what
a key such as ocr-narration-<EP> points at.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FEASIBILITY = ROOT / "evals" / "feasibility"
BV = re.compile(r"BV[0-9A-Za-z]{10}")


def load_material_index() -> dict[str, list[dict]]:
    """episode id -> its Material payloads, narration first."""
    index = {}
    for path in sorted(FEASIBILITY.glob("materials/*.materials.json")):
        episode = path.name.replace(".materials.json", "")
        index[episode] = json.loads(path.read_text(encoding="utf-8"))["materials"]
    return index


def resolve_placeholder(key: str, index: dict[str, list[dict]]) -> tuple[str, dict] | None:
    """Map an evidence_map key onto (episode, Material). Keys look like
    ocr-narration-<EP>, ocr-screen-<EP>, ocr-<BV of a cited work>, or asr-<EP>.

    ocr-narration is material 0. Episodes OCR'd with positions split the screen in two:
    material 0 is then only the narrator's subtitle band, and ocr-screen - material 1 -
    is everything else shown (quoted clips' captions, comments, credits)."""
    if key.startswith("ocr-narration-"):
        episode = key[len("ocr-narration-") :]
        return (episode, index[episode][0]) if episode in index else None
    if key.startswith("ocr-screen-"):
        episode = key[len("ocr-screen-") :]
        materials = index.get(episode) or []
        split = len(materials) > 1 and "画面其他文字" in materials[1]["locator"].get("note", "")
        return (episode, materials[1]) if split else None
    if key.startswith("asr-"):
        episode = key[len("asr-") :]
        transcript = FEASIBILITY / ("%s.transcript.txt" % episode)
        if not transcript.exists():
            return None
        return episode, {
            "text": transcript.read_text(encoding="utf-8"),
            "kind": "asr",
            "locator": {"start_ms": 0, "note": "%s 语音转写全文（faster-whisper）" % episode},
        }
    found = BV.search(key)
    if not found:
        return None
    target = found.group(0)
    # Only citation frames: the screen material's note names its own episode, and an
    # episode can cite another explainer episode by id. An exact match wins; an id that
    # differs only in letter case is the usual OCR misread (BV1XyJA6BEBN on screen for
    # BV1xyJA6BEBN, which is the id the platform resolved), so it is accepted second.
    for insensitive in (False, True):
        for episode, materials in index.items():
            for material in materials[1:]:
                note = material["locator"].get("note", "")
                if "画面出现" not in note:
                    continue
                cited = note.split("画面出现", 1)[1]
                if target in cited or (insensitive and target.lower() in cited.lower()):
                    return episode, material
    return None
