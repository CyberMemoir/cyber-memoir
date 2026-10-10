import { Fragment } from "react";
import type { TextRange } from "@/lib/text-find";

/** React text nodes only: markup-looking source text remains literal and selectable. */
export function FindText({
  text,
  ranges,
  offset,
  active,
}: {
  text: string;
  ranges: TextRange[];
  offset: number;
  active: number;
}) {
  let end = 0;
  const parts = ranges.map((range, i) => {
    const prefix = text.slice(end, range.start);
    end = range.end;
    return (
      <Fragment key={range.start}>
        {prefix}
        <mark
          className="evidence-find-mark"
          data-find-index={offset + i}
          aria-current={active === offset + i ? "true" : undefined}
          tabIndex={-1}
        >
          {text.slice(range.start, range.end)}
        </mark>
      </Fragment>
    );
  });
  return (
    <>
      {parts}
      {text.slice(end)}
    </>
  );
}
