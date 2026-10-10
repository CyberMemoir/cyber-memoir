import type { components } from "../../../packages/contracts/api";
export type Source = components["schemas"]["SourceOut"];
export type Evidence = components["schemas"]["EvidenceOut"];
export type Claim = components["schemas"]["ClaimOut"];
export type TimelineEvent = components["schemas"]["EventOut"];
export type Relation = components["schemas"]["RelationOut"];
export type Meme = components["schemas"]["MemeOut"];
export type SearchResult = components["schemas"]["SearchOut"];
export type Answer = components["schemas"]["AnswerOut"];
export type Universe = components["schemas"]["UniverseOut"];
export type Galaxy = components["schemas"]["Galaxy"];
export type Star = components["schemas"]["Star"];
export type UniverseBand = components["schemas"]["UniverseBand"];
export type UniverseTick = components["schemas"]["UniverseTick"];
export type TargetRef = components["schemas"]["TargetRef"];
export type PublicationPackage = components["schemas"]["PublicationPackage"];
export type ImportPlan = components["schemas"]["ImportPlan"];
export type ImportResult = components["schemas"]["ImportResult"];
export type Draft = {
  canonical_name: string;
  aliases: string[];
  definition: string;
  usage_context: string;
  origin_status: string;
  claims: Claim[];
  events: unknown[];
  relations: unknown[];
  _source_id?: string;
  _import?: {
    operation: "create_new" | "append_derivatives";
    evidence_ids: string[];
    source_ids: string[];
    warnings: string[];
    entry_hash: string;
  };
};
export type Revision = {
  id: string;
  meme_id: string;
  payload: Draft;
  status: string;
  created_at: string;
  based_on_revision: number;
  edit_version: number;
  etag: string;
  review_reason?: string | null;
  reviewer?: string | null;
  reviewed_at?: string | null;
};
export type ReviewComparison = {
  draft: Revision;
  base: Revision | null;
  current: Revision | null;
  current_published_revision: number;
  meme_status: string;
  base_changed: boolean;
};
export type ReviewQueue = Omit<
  components["schemas"]["ReviewQueueOut"],
  "items"
> & { items: Revision[] };
export type Job = {
  id: string;
  status: string;
  attempts: number;
  error: string | null;
};

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code?: string,
    public readonly retryAfterSeconds?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function retryDelay(
  header: string | null,
  fallback: unknown,
  now = Date.now(),
): number | undefined {
  if (header && /^\d+$/.test(header.trim())) {
    const seconds = Number(header.trim());
    if (Number.isFinite(seconds)) return Math.min(60, seconds);
  }
  if (header && /^(Mon|Tue|Wed|Thu|Fri|Sat|Sun), /i.test(header)) {
    const date = Date.parse(header);
    if (Number.isFinite(date))
      return Math.min(60, Math.max(0, Math.ceil((date - now) / 1000)));
  }
  if (
    typeof fallback === "number" &&
    Number.isFinite(fallback) &&
    fallback >= 0
  )
    return Math.min(60, Math.ceil(fallback));
}

export async function api<T>(
  path: string,
  init?: RequestInit,
  token?: string,
): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      ...(init?.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: `服务暂不可用 (${response.status})` }));
    const error = data && typeof data === "object" ? data : {};
    throw new ApiError(
      typeof error.detail === "string"
        ? error.detail
        : error.detail !== undefined
          ? JSON.stringify(error.detail)
          : `服务暂不可用 (${response.status})`,
      response.status,
      typeof error.code === "string" ? error.code : undefined,
      retryDelay(
        response.headers.get("Retry-After"),
        error.retry_after_seconds,
      ),
    );
  }
  return response.json();
}

export const post = (body: unknown): RequestInit => ({
  method: "POST",
  body: JSON.stringify(body),
});
export function date(value: string | null) {
  return value
    ? new Date(value).toLocaleDateString("zh-CN", {
        year: "numeric",
        month: "long",
        day: "numeric",
        timeZone: "Asia/Shanghai",
      })
    : "时间未知";
}
