import type { Claim, Draft } from "./api";

export const reviewedFields = ["definition", "usage_context"] as const;
export type ReviewedField = (typeof reviewedFields)[number];
export type FieldEvidence = Record<ReviewedField, string[]>;

function controlsField(claim: Claim, draft: Draft) {
  return (
    (claim.key === "definition" || claim.key === "usage_context") &&
    claim.stance === "supports" &&
    claim.statement === draft[claim.key]
  );
}

export function initialFieldEvidence(draft: Draft): FieldEvidence {
  return {
    definition: fieldIds("definition"),
    usage_context: fieldIds("usage_context"),
  };

  function fieldIds(field: ReviewedField) {
    return Array.from(
      new Set(
        draft.claims
          .filter((claim) => claim.key === field && controlsField(claim, draft))
          .flatMap((claim) => claim.evidence_ids),
      ),
    );
  }
}

export function supplementalClaims(draft: Draft, appendOnly: boolean) {
  return draft.claims.filter((claim) =>
    appendOnly
      ? !reviewedFields.some((field) => claim.key === field)
      : !controlsField(claim, draft),
  );
}

export function fieldClaims(
  original: Draft,
  values: Record<ReviewedField, string>,
  evidence: FieldEvidence,
  appendOnly: boolean,
): Claim[] {
  if (appendOnly)
    return original.claims.filter((claim) =>
      reviewedFields.some((field) => claim.key === field),
    );
  return reviewedFields.flatMap((field) =>
    values[field].trim() && evidence[field].length
      ? [
          {
            key: field,
            statement: values[field],
            stance: "supports",
            evidence_ids: Array.from(new Set(evidence[field])),
          },
        ]
      : [],
  );
}

export function missingFieldSupport(draft: Draft): ReviewedField | undefined {
  return reviewedFields.find(
    (field) =>
      draft[field] &&
      !draft.claims.some(
        (claim) =>
          claim.key === field &&
          controlsField(claim, draft) &&
          claim.evidence_ids.length,
      ),
  );
}
