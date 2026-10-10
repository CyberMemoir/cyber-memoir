import type { Draft } from "./api";

export const diffFields = [
  ["canonical_name", "梗名称"],
  ["aliases", "别名"],
  ["definition", "定义"],
  ["usage_context", "使用语境"],
  ["origin_status", "起源状态"],
  ["claims", "断言与证据绑定"],
  ["events", "传播事件"],
  ["relations", "衍生与关联"],
] as const;
export type DiffField = (typeof diffFields)[number][0];

function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(",")}]`;
  if (value && typeof value === "object")
    return `{${Object.entries(value)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`)
      .join(",")}}`;
  return JSON.stringify(value) ?? "null";
}

function comparable(field: DiffField, draft: Draft | null): string {
  if (!draft)
    draft = {
      canonical_name: "",
      aliases: [],
      definition: "",
      usage_context: "",
      origin_status: "unknown",
      claims: [],
      events: [],
      relations: [],
    };
  if (field === "claims") {
    const groups = new Map<string, Set<string>>();
    for (const claim of draft.claims) {
      const key = stable({
        key: claim.key,
        statement: claim.statement,
        stance: claim.stance,
      });
      const refs = groups.get(key) || new Set<string>();
      claim.evidence_ids.forEach((id) => refs.add(id));
      groups.set(key, refs);
    }
    return stable(
      Array.from(groups, ([claim, refs]) => [claim, [...refs].sort()]).sort(
        ([a], [b]) => String(a).localeCompare(String(b)),
      ),
    );
  }
  if (field === "aliases") return stable([...new Set(draft.aliases)].sort());
  if (field === "events" || field === "relations")
    return stable(draft[field].map(stable).sort());
  return stable(draft[field]);
}

export function revisionChanges(before: Draft | null, after: Draft) {
  return diffFields.filter(
    ([field]) => comparable(field, before) !== comparable(field, after),
  );
}

export function showDiffValue(draft: Draft | null, field: DiffField) {
  if (!draft) return "（尚无这份内容）";
  const value = draft[field];
  if (field === "aliases") return draft.aliases.join(" / ") || "（无别名）";
  if (typeof value === "string") return value || "（空）";
  return JSON.stringify(value, null, 2);
}
