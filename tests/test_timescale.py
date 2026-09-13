"""The time axis may compress silence, but never reorder evidence or misdate it."""

import random
from datetime import datetime, timedelta, timezone

from cyber_memoir.application.timescale import QUIET_GAP_DAYS, build, china_date

CN = timezone(timedelta(hours=8))


def day(y, m, d):
    return datetime(y, m, d, tzinfo=CN)


# 闹吃VS古振兴, as dated by the platform: FNF mods 2021-2024, then the burst.
NAOCHI = [
    day(2021, 5, 4), day(2021, 6, 3), day(2021, 8, 28), day(2024, 4, 29),
    day(2026, 7, 26), day(2026, 7, 26), day(2026, 8, 5), day(2026, 8, 16), day(2026, 8, 20),
]


def test_nothing_dated_gives_an_empty_axis():
    scale = build([None, None])
    assert scale.positions == {} and scale.bands == [] and scale.ticks == []
    assert scale.at(None) is None


def test_a_single_date_sits_at_the_start_with_no_bands():
    scale = build([day(2026, 8, 9)])
    assert scale.at(day(2026, 8, 9)) == 0.0
    assert scale.bands == []


def test_order_is_never_changed():
    """Position is the one evidenced thing on the picture. Checked on random lineages."""
    rng = random.Random(20260913)
    base = day(2020, 1, 1)
    for _ in range(300):
        points = [base + timedelta(days=rng.choice([rng.randint(0, 20), rng.randint(0, 3000)]))
                  for _ in range(rng.randint(2, 25))]
        scale = build(points)
        ordered = sorted(set(points))
        ts = [scale.at(p) for p in ordered]
        assert all(0.0 <= t <= 1.0 for t in ts)
        assert ts == sorted(ts), "an earlier instant was placed after a later one"
        assert len(set(ts)) == len(ts), "two different instants collapsed onto one position"


def test_the_threshold_is_exclusive():
    at_threshold = build([day(2026, 1, 1), day(2026, 1, 1) + timedelta(days=QUIET_GAP_DAYS)])
    past_it = build([day(2026, 1, 1), day(2026, 1, 1) + timedelta(days=QUIET_GAP_DAYS + 1)])
    assert at_threshold.bands == []
    assert len(past_it.bands) == 1 and past_it.bands[0].days == QUIET_GAP_DAYS + 1


def test_the_burst_is_visible_instead_of_one_pixel():
    """Linear, the 25 days of 2026-07-26..08-20 are 1.3% of the axis."""
    scale = build(NAOCHI)
    burst = scale.at(day(2026, 8, 20)) - scale.at(day(2026, 7, 26))
    linear = (day(2026, 8, 20) - day(2026, 7, 26)) / (day(2026, 8, 20) - day(2021, 5, 4))
    assert linear < 0.02
    assert burst > 0.3
    assert [b.days for b in scale.bands] == [30, 86, 975, 818]
    assert sum(b.end - b.start for b in scale.bands) <= 0.5


def test_bands_name_the_calendar_dates_either_side():
    scale = build(NAOCHI)
    assert (scale.bands[-1].date_from, scale.bands[-1].date_to) == ("2024-04-29", "2026-07-26")
    assert scale.ticks[0].date == "2021-05-04"
    assert scale.ticks[-1].date == "2026-08-20"


def test_dates_are_read_in_beijing_not_sliced_from_utc():
    """How the day-early bug looked: 2021-05-04 00:00 Beijing is 2021-05-03T16:00Z."""
    stored = datetime(2021, 5, 3, 16, 0, tzinfo=timezone.utc)
    assert stored.isoformat()[:10] == "2021-05-03"
    assert china_date(stored) == "2021-05-04"
    # SQLite hands back naive datetimes; they are UTC, not local.
    assert china_date(datetime(2021, 5, 3, 16, 0)) == "2021-05-04"
