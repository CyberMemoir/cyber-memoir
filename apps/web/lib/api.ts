import type { components } from "../../../packages/contracts/api";
export type Source = components["schemas"]["SourceOut"];
export type Evidence = components["schemas"]["EvidenceOut"];
export type Claim = components["schemas"]["ClaimOut"];
export type TimelineEvent = components["schemas"]["EventOut"];
export type Relation = components["schemas"]["RelationOut"];
export type Meme = components["schemas"]["MemeOut"];
export type SearchResult = components["schemas"]["SearchOut"];
export type Answer = components["schemas"]["AnswerOut"];
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
};
export type Revision = {
  id: string;
  meme_id: string;
  payload: Draft;
  status: string;
  created_at: string;
  based_on_revision: number;
};
export type Job = {
  id: string;
  status: string;
  attempts: number;
  error: string | null;
};

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
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
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
      })
    : "时间未知";
}
