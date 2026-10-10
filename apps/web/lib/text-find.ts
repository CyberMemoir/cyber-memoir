/** Browser-local compatibility/case-insensitive literal search; never edits source text. */
export type TextRange = { start: number; end: number };
export const MAX_FIND_MARKS = 500;
export const MAX_FIND_TEXT = 200_000;
export function normalizeFind(text: string) {
  return text.normalize("NFKC").toLocaleLowerCase("zh-CN");
}

export function findText(
  text: string,
  query: string,
): {
  ranges: TextRange[];
  limited: boolean;
  unavailable: boolean;
} {
  const needle = normalizeFind(query.trim());
  if (!needle) return { ranges: [], limited: false, unavailable: false };
  if (text.length > MAX_FIND_TEXT || typeof Intl.Segmenter !== "function")
    return { ranges: [], limited: false, unavailable: true };
  // Map normalized UTF-16 positions back to whole original graphemes. This
  // handles fullwidth forms, ligature expansion, combining accents and emoji.
  const starts: number[] = [],
    ends: number[] = [],
    chunks: string[] = [];
  for (const { segment, index } of new Intl.Segmenter("zh-CN", {
    granularity: "grapheme",
  }).segment(text)) {
    chunks.push(segment.normalize("NFKC"));
    for (const point of segment.normalize("NFKC")) {
      const size = point.toLocaleLowerCase("zh-CN").length;
      for (let i = 0; i < size; i++) {
        starts.push(index);
        ends.push(index + segment.length);
      }
    }
  }
  // Lowercase the complete string to retain contextual forms (e.g. final sigma).
  const normalized = chunks.join("").toLocaleLowerCase("zh-CN");
  if (normalized !== normalizeFind(text) || normalized.length !== starts.length)
    return { ranges: [], limited: false, unavailable: true };
  const ranges: TextRange[] = [];
  let position = 0;
  while ((position = normalized.indexOf(needle, position)) !== -1) {
    const start = starts[position],
      end = ends[position + needle.length - 1];
    const previous = ranges[ranges.length - 1];
    if (previous && start < previous.end)
      previous.end = Math.max(previous.end, end);
    else ranges.push({ start, end });
    if (ranges.length > MAX_FIND_MARKS)
      return { ranges, limited: true, unavailable: false };
    position += needle.length;
  }
  return { ranges, limited: false, unavailable: false };
}
