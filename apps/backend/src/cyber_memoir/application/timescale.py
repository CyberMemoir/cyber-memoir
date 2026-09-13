"""Map dated evidence onto a 0..1 axis without letting quiet years swallow the story.

A meme's lineage is usually long silence and then a burst. 闹吃VS古振兴 draws on
material from 2021 and spreads in 25 days of 2026-08; on a linear axis those 25 days
are 1.3% of the length and every star that makes it a meme lands in one pixel.
狼王撕衣 is the same shape with five and a half years of nothing in the middle.

So gaps longer than QUIET_GAP_DAYS are cut out and replaced by a fixed-width band
that says how long they were, and the active stretches share the rest of the axis in
proportion to how long they actually lasted.

What this must never do is change order. Position is the one thing on the picture
taken from evidence rather than judgement, so an earlier instant is never placed
after a later one. The tests hold it to that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# China has observed no daylight saving since 1991, so a fixed offset is exact for
# every date this archive holds, and needs no tzdata in the container.
CHINA = timezone(timedelta(hours=8), "Asia/Shanghai")

# Measured 2026-09-13 over 29 gaps between consecutive dated stars in 14 memes: inside
# a burst the largest gap was 15 days, and the smallest gap that was not a burst was
# 30. 21 sits in the empty space between. Revisit as the corpus grows.
QUIET_GAP_DAYS = 21
# Axis share given to each compressed quiet period, and the most they may take in all.
GAP_SHARE = 0.12
MAX_GAP_TOTAL = 0.5

DAY = 86400.0


def as_utc(value: datetime) -> datetime:
    """PostgreSQL returns aware UTC; SQLite drops the zone. Naive means UTC here."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def china_date(value: datetime | None) -> str | None:
    """The calendar date a Beijing viewer would read.

    2021-05-04T00:00+08:00 is stored as 2021-05-03T16:00Z, so the first ten characters
    of the ISO string name the wrong day. Every date shown to a reader goes through here.
    """
    return None if value is None else as_utc(value).astimezone(CHINA).date().isoformat()


@dataclass
class Band:
    start: float
    end: float
    date_from: str
    date_to: str
    days: int


@dataclass
class Tick:
    t: float
    date: str


@dataclass
class Scale:
    positions: dict[datetime, float] = field(default_factory=dict)
    bands: list[Band] = field(default_factory=list)
    ticks: list[Tick] = field(default_factory=list)

    def at(self, value: datetime | None) -> float | None:
        return None if value is None else self.positions.get(as_utc(value))


def build(instants: list[datetime | None]) -> Scale:
    points = sorted({as_utc(x) for x in instants if x is not None})
    if not points:
        return Scale()

    segments: list[list[datetime]] = [[points[0]]]
    for previous, current in zip(points, points[1:]):
        if (current - previous).total_seconds() / DAY > QUIET_GAP_DAYS:
            segments.append([current])
        else:
            segments[-1].append(current)

    quiet = len(segments) - 1
    gap_total = min(GAP_SHARE * quiet, MAX_GAP_TOTAL)
    per_gap = gap_total / quiet if quiet else 0.0
    # Each stretch is weighted by its length plus one day, so a burst on a single day
    # still gets width instead of collapsing to a point.
    weights = [(seg[-1] - seg[0]).total_seconds() / DAY + 1.0 for seg in segments]
    active = 1.0 - gap_total

    scale = Scale()
    cursor = 0.0
    for index, (segment, weight) in enumerate(zip(segments, weights)):
        width = active * weight / sum(weights)
        for point in segment:
            offset = (point - segment[0]).total_seconds() / DAY
            scale.positions[point] = cursor + width * offset / weight
        scale.ticks.append(Tick(t=cursor, date=china_date(segment[0])))
        cursor += width
        if index < quiet:
            following = segments[index + 1][0]
            scale.bands.append(
                Band(
                    start=cursor,
                    end=cursor + per_gap,
                    date_from=china_date(segment[-1]),
                    date_to=china_date(following),
                    days=round((following - segment[-1]).total_seconds() / DAY),
                )
            )
            cursor += per_gap
    last = points[-1]
    if china_date(last) != scale.ticks[-1].date:
        scale.ticks.append(Tick(t=scale.positions[last], date=china_date(last)))
    return scale
