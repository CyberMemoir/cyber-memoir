"""Vincent's explicit approval, bound to the record and evidence he reviewed.

Approvals are recorded from an actual user reply, never from model review or
validator success. This module deliberately has no automatic approval command.
"""
import json
from datetime import datetime
from pathlib import Path

from automation_review import fingerprint

ROOT = Path(__file__).resolve().parents[1]


def approval_error(doc: dict, index: dict, path: Path) -> str | None:
    approval_path = ROOT / "ai_context/human_approvals" / (path.stem + ".json")
    try:
        approval = json.loads(approval_path.read_text(encoding="utf-8"))
        if approval.get("reviewer") != "Vincent" or approval.get("decision") != "approve":
            return "需要 Vincent 明确通过"
        if not isinstance(approval.get("authorization"), str) or not approval["authorization"].strip():
            return "缺少 Vincent 的实际确认原文"
        if datetime.fromisoformat(approval["approved_at"]).tzinfo is None:
            return "人工确认时间必须包含时区"
        if approval.get("canonical_name") != doc.get("canonical_name"):
            return "人工确认与条目不一致"
        if approval.get("fingerprint") != fingerprint(doc, index):
            return "审核后内容或证据已变化，需要重新确认"
    except (OSError, ValueError, KeyError, TypeError):
        return "待 Vincent 审核"
    return None


def write_cards(packets: list[dict], batch: int, output: Path) -> None:
    """Readable local review page; decisions happen in the conversation."""
    lines = [f"# 第 {batch} 批：待人工审核", "",
             "请回复整批通过，或逐条注明通过／需要修改／暂不入库。未明确通过不会公开入库。",
             "模型复核来自同一 Codex，不是独立模型或人工确认。", ""]
    for number, packet in enumerate(packets, 1):
        doc = packet["record"]
        lines += [f"## {number}. {doc['canonical_name']}", "",
                  "**解释**：" + str(doc.get("definition") or "待补充"), "",
                  "**用法**：" + str(doc.get("usage_context") or "见解释与证据"), "",
                  "**出处与疑点**："]
        for origin in doc.get("origins") or []:
            lines += ["- " + json.dumps(origin, ensure_ascii=False, default=str)]
        if not doc.get("origins"):
            lines += ["- 首次出处未确认；解说及示例不等于首发证据。"]
        review = (doc.get("curation") or {}).get("automated_review") or {}
        for key in ("identity", "origins", "events"):
            if review.get("checks", {}).get(key):
                lines += ["- " + review["checks"][key]]
        lines += ["", "**关键证据与回看**："]
        for key, found in packet["materials"].items():
            if not found:
                lines += [f"- {key}：证据缺失，不能通过。"]
                continue
            episode, material = found
            seconds = int((material.get("locator") or {}).get("start_ms") or 0) // 1000
            lines += [f"- [回看 {episode}，{seconds} 秒](https://www.bilibili.com/video/{episode}?t={seconds})；位置："
                      + json.dumps(material.get("locator") or {}, ensure_ascii=False)]
            # Keep the original evidence available without pretending an excerpt is complete.
            lines += ["", "<details><summary>展开原始证据文字</summary>", "",
                      str(material.get("text") or "无文字，请看原画面"), "", "</details>", ""]
        lines += ["**审核结果**：待 Vincent 确认", "",
                  f"记录：`{Path(packet['path']).name}`；内容与证据绑定：`{packet['fingerprint']}`", ""]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
