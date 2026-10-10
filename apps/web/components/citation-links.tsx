"use client";

import type { MouseEvent } from "react";
import type { EvidenceIndex } from "@/lib/citations";

export type NavigateReference = (anchor: string) => void;

export function ReferenceLink({
  anchor,
  onNavigate,
  children,
  ...props
}: {
  anchor: string;
  onNavigate: NavigateReference;
  children: React.ReactNode;
} & Omit<React.AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "onClick">) {
  function follow(event: MouseEvent<HTMLAnchorElement>) {
    // Keep native open-in-new-tab / copy-link behaviour. Only normal activation
    // changes the local filters and moves keyboard focus.
    if (
      event.button ||
      event.metaKey ||
      event.ctrlKey ||
      event.altKey ||
      event.shiftKey
    )
      return;
    event.preventDefault();
    onNavigate(anchor);
  }
  return (
    <a {...props} href={`#${encodeURIComponent(anchor)}`} onClick={follow}>
      {children}
    </a>
  );
}

export function CitationLinks({
  ids,
  index,
  onNavigate,
}: {
  ids: string[];
  index: EvidenceIndex;
  onNavigate: NavigateReference;
}) {
  if (!ids.length) return null;
  return (
    <span className="inline-citations">
      {Array.from(new Set(ids)).map((id) => {
        const item = index.get(id);
        return item ? (
          <ReferenceLink
            key={id}
            anchor={`evidence-${id}`}
            onNavigate={onNavigate}
            aria-label={`查看证据 ${item.number}：${item.evidence.source?.title || "公开材料"}`}
          >
            [{item.number}]
          </ReferenceLink>
        ) : (
          <span key={id} className="muted">
            [引用暂不可定位]
          </span>
        );
      })}
    </span>
  );
}
