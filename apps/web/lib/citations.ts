import type { Claim, Evidence, Meme } from "@/lib/api";

export type EvidenceUse = {
  anchor: string;
  label: string;
  statement: string;
  stance: string;
};
export type IndexedEvidence = {
  number: number;
  evidence: Evidence;
  uses: EvidenceUse[];
};
export type EvidenceIndex = Map<string, IndexedEvidence>;

export function claimAnchor(meme: Meme, claim: Claim, index: number) {
  if (claim.key === "definition" && claim.statement === meme.definition)
    return "claim-definition";
  if (claim.key === "usage_context" && claim.statement === meme.usage_context)
    return "claim-usage_context";
  return `claim-${claim.key === "origin" ? "origin" : "extra"}-${index}`;
}

export function evidenceIndex(meme: Meme | null): EvidenceIndex {
  const index: EvidenceIndex = new Map();
  if (!meme) return index;
  meme.evidence.forEach((evidence, i) =>
    index.set(evidence.id, { number: i + 1, evidence, uses: [] }),
  );
  function add(ids: string[], use: EvidenceUse) {
    for (const id of new Set(ids)) {
      const item = index.get(id);
      if (
        item &&
        !item.uses.some(
          (old) =>
            old.anchor === use.anchor &&
            old.stance === use.stance &&
            old.statement === use.statement,
        )
      )
        item.uses.push(use);
    }
  }
  const labels: Record<string, string> = {
    definition: "返回含义",
    usage_context: "返回使用语境",
    origin: "返回起源主张",
    alias: "返回别名断言",
  };
  meme.claims.forEach((claim, i) => {
    // The API also aggregates event/relation links into `claims`. Their real
    // targets below have IDs; do not create phantom field-claim destinations.
    if (["event", "relation"].includes(claim.key)) return;
    add(claim.evidence_ids, {
      anchor: claimAnchor(meme, claim, i),
      label: labels[claim.key] || "返回补充断言",
      statement: claim.statement,
      stance: claim.stance,
    });
  });
  meme.events.forEach((event) =>
    add(event.evidence_ids || [], {
      anchor: `event-${event.id}`,
      label: "返回传播事件",
      statement: event.description,
      stance: "context",
    }),
  );
  meme.relations.forEach((relation) =>
    add(relation.evidence_ids || [], {
      anchor: `relation-${relation.id}`,
      label: "返回关联关系",
      statement: relation.target?.label || relation.predicate,
      stance: relation.assertion_status === "disputed" ? "disputed" : "context",
    }),
  );
  return index;
}

export function referenceUrl(
  memeId: string,
  revision: number | undefined,
  evidenceId: string,
) {
  const version =
    revision && Number.isSafeInteger(revision) && revision > 0
      ? `?expected_revision=${revision}`
      : "";
  return `/memes/${encodeURIComponent(memeId)}${version}#${encodeURIComponent(`evidence-${evidenceId}`)}`;
}

export function stanceLabel(stance: string) {
  return stance === "contradicts"
    ? "相矛盾材料"
    : stance === "supports"
      ? "支持材料"
      : stance === "disputed"
        ? "有争议的关联"
        : "事件或关联引用";
}
