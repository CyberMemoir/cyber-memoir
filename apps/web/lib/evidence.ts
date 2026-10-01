/**
 * Evidence metadata in the reader's language. The API stores a kind and a locator
 * for machines; a reader should see "画面文字（OCR） · 第 74 秒 · ..." rather than
 * `ocr` and a JSON object. Nothing here adds information: every word comes from the
 * stored fields, and an unknown field is shown as it is rather than dropped.
 */

const KINDS: Record<string, string> = {
  ocr: "画面文字（OCR）",
  asr: "语音转写（ASR）",
  subtitle: "平台字幕",
  manual: "人工摘录",
  text: "文本",
};

export function describeKind(kind: string | null | undefined): string {
  if (!kind) return "证据";
  return KINDS[kind] ?? kind;
}

function seconds(ms: number): string {
  const total = Math.round(ms / 1000);
  const minutes = Math.floor(total / 60);
  return minutes ? `${minutes} 分 ${total % 60} 秒` : `${total} 秒`;
}

export function describeLocator(locator: unknown): string {
  if (!locator || typeof locator !== "object") return "无定位信息";
  const fields = { ...(locator as Record<string, unknown>) };
  const parts: string[] = [];
  const start = typeof fields.start_ms === "number" ? fields.start_ms : null;
  const end = typeof fields.end_ms === "number" ? fields.end_ms : null;
  if (start !== null && end !== null)
    parts.push(`第 ${seconds(start)} 至 ${seconds(end)}`);
  else if (start !== null && start > 0) parts.push(`第 ${seconds(start)}`);
  else if (start === 0) parts.push("全片");
  delete fields.start_ms;
  delete fields.end_ms;
  if (typeof fields.note === "string" && fields.note.trim())
    parts.push(fields.note.trim());
  delete fields.note;
  for (const [key, value] of Object.entries(fields)) {
    if (value === null || value === undefined || value === "") continue;
    parts.push(
      `${key}：${typeof value === "string" ? value : JSON.stringify(value)}`,
    );
  }
  return parts.length ? parts.join(" · ") : "无定位信息";
}
