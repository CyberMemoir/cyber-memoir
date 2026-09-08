import json
import re


def parse_subtitles(body: str, fmt: str) -> list[dict]:
    """Normalize platform JSON and SRT/WebVTT cues without throwing away timestamps."""
    if fmt in {"json", "json3"}:
        data = json.loads(body)
        if "body" in data:
            return [
                {
                    "text": x["content"],
                    "locator": {"start_ms": round(x["from"] * 1000), "end_ms": round(x["to"] * 1000)},
                }
                for x in data["body"]
                if x.get("content", "").strip()
            ]
        return [
            {
                "text": "".join(y.get("utf8", "") for y in x.get("segs", [])),
                "locator": {
                    "start_ms": x.get("tStartMs", 0),
                    "end_ms": x.get("tStartMs", 0) + x.get("dDurationMs", 0),
                },
            }
            for x in data.get("events", [])
            if x.get("segs")
        ]

    def milliseconds(value):
        parts = value.replace(",", ".").split(":")
        return round(sum(float(p) * (60**i) for i, p in enumerate(reversed(parts))) * 1000)

    cues = []
    for block in re.split(r"\n\s*\n", body.replace("\r\n", "\n")):
        lines = block.strip().splitlines()
        for i, line in enumerate(lines):
            match = re.match(r"([\d:.,]+)\s*-->\s*([\d:.,]+)", line)
            if match:
                text = "\n".join(lines[i + 1 :]).strip()
                if text:
                    cues.append(
                        {
                            "text": text,
                            "locator": {"start_ms": milliseconds(match[1]), "end_ms": milliseconds(match[2])},
                        }
                    )
                break
    return cues
