/** Format only the precision and timezone information actually saved in an event. */
export type EventTimePoint = {
  label: string;
  dateTime?: string;
  note?: string;
  zoneKnown?: boolean;
  order?: number;
  subMillisecond?: number;
};
const PRECISIONS = new Set(["year", "month", "day", "second"]);

export function eventTimePoint(
  value: string | null,
  precision: string,
): EventTimePoint {
  if (precision === "unknown" || !value) return { label: "时间未知" };
  if (!PRECISIONS.has(precision)) return { label: "时间精度待核对" };
  const match =
    /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})?$/.exec(
      value,
    );
  const invalid = { label: "时间格式待核对" };
  if (!match) return invalid;
  const [, year, month, day, hour, minute, second, fraction, zone] = match;
  const y = Number(year),
    m = Number(month),
    d = Number(day);
  const leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  if (
    !y ||
    m < 1 ||
    m > 12 ||
    d < 1 ||
    d > days[m - 1] ||
    Number(hour) > 23 ||
    Number(minute) > 59 ||
    Number(second) > 59 ||
    (zone &&
      zone !== "Z" &&
      (Number(zone.slice(1, 3)) > 23 || Number(zone.slice(4, 6)) > 59))
  )
    return invalid;
  // Missing-zone legacy values are calendar fields, not the reader's local time
  // and not an inferred UTC instant. UTC is only a deterministic formatting frame.
  const zoneKnown = !!zone;
  const date = new Date(zoneKnown ? value : `${value}Z`);
  if (
    !Number.isFinite(date.getTime()) ||
    date.getUTCFullYear() < 1 ||
    date.getUTCFullYear() > 9999
  )
    return invalid;
  const timeZone = zoneKnown ? "Asia/Shanghai" : "UTC";
  const options: Intl.DateTimeFormatOptions = { year: "numeric", timeZone };
  if (precision !== "year") options.month = "long";
  if (precision === "day" || precision === "second") options.day = "numeric";
  if (precision === "second")
    Object.assign(options, {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
    });
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      timeZone,
    })
      .formatToParts(date)
      .map(({ type, value }) => [type, value]),
  );
  if (Number(parts.year) < 1 || Number(parts.year) > 9999) return invalid;
  const calendar = `${parts.year.padStart(4, "0")}-${parts.month}-${parts.day}`;
  const dateTime =
    precision === "year"
      ? calendar.slice(0, 4)
      : precision === "month"
        ? calendar.slice(0, 7)
        : precision === "day"
          ? calendar
          : zoneKnown
            ? `${date.toISOString().slice(0, 19)}Z`
            : value.slice(0, 19);
  return {
    label: date.toLocaleDateString("zh-CN", options),
    dateTime,
    zoneKnown,
    order: date.getTime(),
    subMillisecond: Number((fraction ?? "").padEnd(6, "0").slice(3)),
    note: zoneKnown
      ? undefined
      : "时区未记录；按保存的日历字段显示，不推定时区或实际时刻。",
  };
}

export function eventTimeRange(
  start: string | null,
  end: string | null,
  precision: string,
) {
  if (precision === "unknown")
    return {
      start: { label: "时间未知" } as EventTimePoint,
      end: null,
      notes: start || end ? ["已保存时间字段，但精度未知，不展开日期。"] : [],
    };
  const a = eventTimePoint(start, precision);
  const b = end ? eventTimePoint(end, precision) : null;
  const notes = new Set<string>();
  for (const point of [a, b]) if (point?.note) notes.add(point.note);
  if (!start && end) notes.add("开始时间未记录，不从结束时间倒推。");
  if (a.order !== undefined && b?.order !== undefined) {
    const comparison =
      b.order - a.order || (b.subMillisecond ?? 0) - (a.subMillisecond ?? 0);
    if (a.zoneKnown !== b.zoneKnown)
      notes.add("起止字段时区信息不一致，无法核对先后。");
    else if (comparison < 0)
      notes.add(
        a.zoneKnown
          ? "结束时间早于开始时间，范围待核对。"
          : "结束日历字段早于开始字段，范围待核对。",
      );
    else if (a.label === b.label && comparison !== 0)
      notes.add("起止落在同一已记录时间单位，按保存精度显示，不展开更细时间。");
  }
  return { start: a, end: b, notes: [...notes] };
}
