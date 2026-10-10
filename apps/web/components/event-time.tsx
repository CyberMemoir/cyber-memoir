import { eventTimeRange, type EventTimePoint } from "@/lib/event-time";

function Point({ point }: { point: EventTimePoint }) {
  return point.dateTime ? (
    <time dateTime={point.dateTime}>{point.label}</time>
  ) : (
    <span>{point.label}</span>
  );
}
export function EventTime({
  start,
  end,
  precision,
}: {
  start: string | null;
  end: string | null;
  precision: string;
}) {
  const range = eventTimeRange(start, end, precision);
  return (
    <>
      <div className="timeline-date">
        <Point point={range.start} />
        {range.end && (
          <span className="timeline-range-end">
            {" "}
            至 <Point point={range.end} />
          </span>
        )}
      </div>
      {range.notes.map((note) => (
        <p className="timeline-time-note" key={note}>
          {note}
        </p>
      ))}
    </>
  );
}
