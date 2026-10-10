/** Local-only counterpart of evals/semantic_review.py. No network or publication. */
export const ASSESSMENTS = [
  "supported",
  "partial",
  "unsupported",
  "contradicted",
  "unverifiable",
] as const;
export type Assessment = (typeof ASSESSMENTS)[number];
export type EvidenceRecord = {
  id: string;
  source_id: string;
  content_hash: string;
  text: string;
  verified: true;
  retracted: false;
  locator: Record<string, unknown>;
  source: { id: string; canonical_url?: string; title?: string };
};
export type QueueRow = {
  audit_id: string;
  claim: {
    meme_id: string;
    meme_revision: number;
    key: string;
    statement: string;
    stance: string;
    evidence_ids: string[];
    meme_name?: string;
  };
  evidence: EvidenceRecord[];
  queries?: string[];
};
export type Quote = {
  evidence_id: string;
  content_hash: string;
  start: number;
  end: number;
  exact: string;
};
export type Review = {
  audit_id: string;
  assessment: Assessment | null;
  reviewer: string | null;
  reviewed_at: string | null;
  reason: string | null;
  quotes: Quote[];
};
export type ReviewFile = {
  schema_version: 1;
  scope: "saved_evidence_text_not_publication";
  queue_sha256: string;
  reviews: Review[];
};
export type LoadedQueue = { sha: string; rows: QueueRow[] };
const IDENTITY = [
  "meme_id",
  "meme_revision",
  "key",
  "statement",
  "stance",
  "evidence_ids",
];
const SHA = /^[0-9a-f]{64}$/;
const LIMIT = 16 * 1024 * 1024;
function required(value: unknown, message: string): asserts value {
  if (!value) throw new Error(message);
}
function record(value: unknown): Record<string, unknown> {
  required(
    value && typeof value === "object" && !Array.isArray(value),
    "需要 JSON 对象",
  );
  return value as Record<string, unknown>;
}
function nonempty(value: unknown): value is string {
  return (
    typeof value === "string" &&
    !!value.trim() &&
    Array.from(value).every((character) => {
      const point = character.codePointAt(0)!;
      return point < 0xd800 || point > 0xdfff;
    })
  );
}
function awareISO(value: string) {
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.exec(
      value,
    );
  if (!match) return false;
  const [, year, month, day, hour, minute, second, zone] = match;
  const y = Number(year),
    m = Number(month),
    d = Number(day);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return (
    y > 0 &&
    m >= 1 &&
    m <= 12 &&
    d >= 1 &&
    d <= days[m - 1] &&
    Number(hour) < 24 &&
    Number(minute) < 60 &&
    Number(second) < 60 &&
    (zone === "Z" ||
      (Number(zone.slice(1, 3)) < 24 && Number(zone.slice(4, 6)) < 60)) &&
    Number.isFinite(Date.parse(value))
  );
}
function pythonJSON(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(pythonJSON).join(", ")}]`;
  if (value && typeof value === "object")
    return `{${Object.keys(value)
      .sort()
      .map(
        (k) =>
          `${JSON.stringify(k)}: ${pythonJSON((value as Record<string, unknown>)[k])}`,
      )
      .join(", ")}}`;
  return JSON.stringify(value);
}
export async function sha256(bytes: Uint8Array): Promise<string> {
  const result = await crypto.subtle.digest(
    "SHA-256",
    new Uint8Array(bytes).buffer,
  );
  return Array.from(new Uint8Array(result), (v) =>
    v.toString(16).padStart(2, "0"),
  ).join("");
}
export async function fileBytes(file: File): Promise<Uint8Array> {
  required(file.size <= LIMIT, "文件超过 16 MB 本地限制");
  return new Uint8Array(await file.arrayBuffer());
}
export function decode(bytes: Uint8Array) {
  return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(
    bytes,
  );
}
export async function loadQueue(bytes: Uint8Array): Promise<LoadedQueue> {
  required(bytes.length <= LIMIT, "队列超过 16 MB 本地限制");
  const raw = decode(bytes);
  const rows = raw
    .split(/\r?\n/)
    .filter((line) => line.trim())
    .map((line) => record(JSON.parse(line)));
  required(rows.length > 0, "队列不能为空");
  const ids = new Set<string>();
  const evidenceVersions = new Map<string, string>();
  for (const row of rows) {
    const c = record(row.claim);
    required(
      c.meme_name == null || typeof c.meme_name === "string",
      "断言名称类型无效",
    );
    required(
      nonempty(c.meme_id) &&
        nonempty(c.key) &&
        nonempty(c.stance) &&
        nonempty(c.statement),
      "断言缺少身份或文字",
    );
    required(
      Number.isSafeInteger(c.meme_revision) && Number(c.meme_revision) > 0,
      "公开修订必须是正整数",
    );
    required(
      Array.isArray(c.evidence_ids) &&
        c.evidence_ids.length > 0 &&
        c.evidence_ids.every(nonempty) &&
        new Set(c.evidence_ids).size === c.evidence_ids.length,
      "断言必须绑定独立证据",
    );
    const identity = Object.fromEntries(IDENTITY.map((key) => [key, c[key]]));
    const expected = await sha256(
      new TextEncoder().encode(pythonJSON(identity)),
    );
    required(
      row.audit_id === expected && !ids.has(expected),
      "断言摘要不匹配或重复",
    );
    ids.add(expected);
    required(
      ["assessment", "reviewer", "reason"].every(
        (key) => row[key] === null || row[key] === undefined,
      ),
      "只能导入未评级审计队列；复核文件请单独加载",
    );
    required(Array.isArray(row.evidence), "缺少保存证据");
    const evidenceIds = new Set<string>();
    for (const value of row.evidence) {
      const e = record(value);
      const s = record(e.source);
      required(
        s.title == null || typeof s.title === "string",
        "来源标题类型无效",
      );
      required(
        e.locator == null ||
          (typeof e.locator === "object" && !Array.isArray(e.locator)),
        "定位字段类型无效",
      );
      required(
        nonempty(e.id) &&
          nonempty(e.source_id) &&
          s.id === e.source_id &&
          e.verified === true &&
          e.retracted === false &&
          nonempty(e.text) &&
          typeof e.content_hash === "string" &&
          SHA.test(e.content_hash),
        "证据/来源绑定或保存文本无效",
      );
      required(!evidenceIds.has(e.id), "重复证据标识");
      evidenceIds.add(e.id);
      const version = pythonJSON(e);
      required(
        !evidenceVersions.has(e.id) || evidenceVersions.get(e.id) === version,
        "同一证据有不一致表示",
      );
      evidenceVersions.set(e.id, version);
    }
    required(
      evidenceIds.size === c.evidence_ids.length &&
        c.evidence_ids.every((id) => evidenceIds.has(id)),
      "证据列表与断言绑定不符",
    );
  }
  return { sha: await sha256(bytes), rows: rows as unknown as QueueRow[] };
}
export function pending(audit_id: string): Review {
  return {
    audit_id,
    assessment: null,
    reviewer: null,
    reviewed_at: null,
    reason: null,
    quotes: [],
  };
}
function exactKeys(value: Record<string, unknown>, keys: string[]) {
  required(
    Object.keys(value).every((key) => keys.includes(key)),
    "复核文件包含未知字段",
  );
}
export function validateReview(value: unknown, row: QueueRow): Review {
  const r = record(value);
  exactKeys(r, [
    "audit_id",
    "assessment",
    "reviewer",
    "reviewed_at",
    "reason",
    "quotes",
  ]);
  required(r.audit_id === row.audit_id, "复核断言身份不匹配");
  const quotes = r.quotes ?? [];
  required(Array.isArray(quotes), "摘录必须是列表");
  if (r.assessment == null) {
    required(
      [r.reviewer, r.reviewed_at, r.reason].every((v) => v == null) &&
        quotes.length === 0,
      "待复核记录不可半填归属或摘录",
    );
    return pending(row.audit_id);
  }
  required(ASSESSMENTS.includes(r.assessment as Assessment), "未知复核结论");
  required(
    nonempty(r.reviewer) && nonempty(r.reason) && nonempty(r.reviewed_at),
    "已评级记录必须有复核者、理由与时间",
  );
  required(awareISO(r.reviewed_at), "复核时间必须是合法、含时区的 ISO 时间");
  required(
    !["supported", "partial", "contradicted"].includes(
      r.assessment as string,
    ) || quotes.length > 0,
    "此结论需要至少一条保存原文摘录",
  );
  const seen = new Set<string>();
  for (const value of quotes) {
    const q = record(value);
    exactKeys(q, ["evidence_id", "content_hash", "start", "end", "exact"]);
    const e = row.evidence.find((e) => e.id === q.evidence_id);
    const key = `${q.evidence_id}:${q.start}:${q.end}`;
    required(
      e &&
        q.content_hash === e.content_hash &&
        Number.isSafeInteger(q.start) &&
        Number.isSafeInteger(q.end) &&
        Number(q.start) >= 0 &&
        Number(q.end) > Number(q.start) &&
        Number(q.end) <= Array.from(e.text).length &&
        !seen.has(key) &&
        nonempty(q.exact),
      "摘录身份、摘要或位置无效",
    );
    required(
      Array.from(e.text).slice(Number(q.start), Number(q.end)).join("") ===
        q.exact,
      "摘录与保存原文不一致",
    );
    seen.add(key);
  }
  return {
    audit_id: row.audit_id,
    assessment: r.assessment as Assessment,
    reviewer: r.reviewer,
    reason: r.reason,
    reviewed_at: r.reviewed_at,
    quotes: quotes as Quote[],
  };
}
export function importReviews(
  bytes: Uint8Array,
  queue: LoadedQueue,
): ReviewFile {
  const f = record(JSON.parse(decode(bytes)));
  exactKeys(f, ["schema_version", "scope", "queue_sha256", "reviews"]);
  required(
    f.schema_version === 1 &&
      f.scope === "saved_evidence_text_not_publication" &&
      f.queue_sha256 === queue.sha,
    "复核文件不属于当前固定队列",
  );
  required(Array.isArray(f.reviews), "缺少复核列表");
  const seen = new Set<string>();
  const map = new Map<string, Review>();
  for (const value of f.reviews) {
    const r = record(value);
    const row = queue.rows.find((row) => row.audit_id === r.audit_id);
    required(row && !seen.has(row.audit_id), "未知或重复复核标识");
    seen.add(row.audit_id);
    map.set(row.audit_id, validateReview(r, row));
  }
  return {
    schema_version: 1,
    scope: "saved_evidence_text_not_publication",
    queue_sha256: queue.sha,
    reviews: queue.rows.map(
      (row) => map.get(row.audit_id) ?? pending(row.audit_id),
    ),
  };
}
export function reviewFile(queue: LoadedQueue, reviews: Review[]): ReviewFile {
  return importReviews(
    new TextEncoder().encode(
      JSON.stringify({
        schema_version: 1,
        scope: "saved_evidence_text_not_publication",
        queue_sha256: queue.sha,
        reviews,
      }),
    ),
    queue,
  );
}
export function quoteFromSelection(
  evidence: EvidenceRecord,
  startUTF16: number,
  endUTF16: number,
): Quote {
  required(
    Number.isInteger(startUTF16) &&
      Number.isInteger(endUTF16) &&
      startUTF16 >= 0 &&
      endUTF16 > startUTF16 &&
      endUTF16 <= evidence.text.length,
    "请在一份原文内选择连续文字",
  );
  const start = Array.from(evidence.text.slice(0, startUTF16)).length;
  const end = Array.from(evidence.text.slice(0, endUTF16)).length;
  const exact = evidence.text.slice(startUTF16, endUTF16);
  required(
    Array.from(evidence.text).slice(start, end).join("") === exact,
    "选择截断了 Unicode 字符，请重新选择",
  );
  return {
    evidence_id: evidence.id,
    content_hash: evidence.content_hash,
    start,
    end,
    exact,
  };
}
export function sourceUrl(value: string | undefined) {
  try {
    const url = new URL(value ?? "");
    return ["https:", "http:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : undefined;
  } catch {
    return undefined;
  }
}
