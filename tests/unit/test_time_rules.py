import math
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest

from geo_audit.geo import zone_intervals
from geo_audit.rules import excessive_speed, off_road, speed_kmh
from geo_audit.timecut import day_intervals, parse_timestamp, report_day


@pytest.mark.parametrize(
    "text,day",
    [
        ("2026-11-04T14:59:59Z", date(2026, 11, 4)),
        ("2026-11-04T15:00:00Z", date(2026, 11, 5)),
        ("2026-11-05T00:00:00+09:00", date(2026, 11, 5)),
    ],
)
def test_day(text, day):
    assert report_day(parse_timestamp(text)) == day


def test_equivalent_instants():
    assert parse_timestamp("2026-11-05T00:00:00+09:00") == datetime(2026, 11, 4, 15, tzinfo=UTC)


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "garbage",
        "2026-11-04T15:00:00",
        "2026-11-04T15:00:00.1234567Z",
        "2026-02-30T00:00:00Z",
        "2026-11-04T15:00:00+09:99",
    ],
)
def test_bad_time(text):
    with pytest.raises(ValueError):
        parse_timestamp(text)


def test_equal_midnight_split():
    pieces = day_intervals(
        parse_timestamp("2026-11-04T14:59:55Z"), parse_timestamp("2026-11-04T15:00:05Z")
    )
    assert [(p.day, 100 * (p.end - p.start)) for p in pieces] == [
        (date(2026, 11, 4), 50),
        (date(2026, 11, 5), 50),
    ]


def test_combined_split(zone):
    spatial = zone_intervals((2000, 0), (2100, 0), zone)
    days = day_intervals(
        parse_timestamp("2026-11-04T14:59:53Z"), parse_timestamp("2026-11-04T15:00:03Z")
    )
    # Independent intersection arithmetic: 100 m × [.5,.7] and [.7,1].
    values = [
        100 * sum(max(0, min(hi, d.end) - max(lo, d.start)) for lo, hi in spatial) for d in days
    ]
    assert values == pytest.approx([20, 30], abs=1e-6)


def test_end_at_cut_and_multiple_days():
    start = parse_timestamp("2026-11-04T14:59:50Z")
    cut = parse_timestamp("2026-11-04T15:00:00Z")
    assert [(p.day, p.start, p.end) for p in day_intervals(start, cut)] == [
        (date(2026, 11, 4), 0, 1)
    ]
    end = parse_timestamp("2026-11-06T15:00:00Z")
    parts = day_intervals(cut, end)
    assert [(p.day, p.start, p.end) for p in parts] == [
        (date(2026, 11, 5), 0, 0.5),
        (date(2026, 11, 6), 0.5, 1),
    ]
    with pytest.raises(ValueError):
        day_intervals(cut, cut)


@pytest.mark.parametrize("tz", ["Pacific/Kiritimati", "America/Los_Angeles"])
def test_host_timezone(tz):
    code = "from geo_audit.timecut import *; print(report_day(parse_timestamp('2026-11-04T15:00:00Z')))"
    result = subprocess.run(
        [sys.executable, "-c", code],
        env={**os.environ, "TZ": tz},
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == "2026-11-05"


def test_exact_thresholds():
    assert not off_road(100)
    assert off_road(math.nextafter(100, math.inf))
    assert speed_kmh(1250, 30) == 150
    assert not excessive_speed(150)
    assert excessive_speed(math.nextafter(150, math.inf))
    assert speed_kmh(200, 20) == 36


@pytest.mark.parametrize("elapsed", [0, -1, math.nan, math.inf])
def test_invalid_elapsed(elapsed):
    with pytest.raises(ValueError):
        speed_kmh(100, elapsed)


@pytest.mark.parametrize("value", [-1, math.nan, math.inf])
def test_invalid_threshold_input(value):
    for predicate in (off_road, excessive_speed):
        with pytest.raises(ValueError):
            predicate(value)


def test_naive_datetime_and_reverse_interval():
    with pytest.raises(ValueError, match="NAIVE_TIMESTAMP"):
        report_day(datetime(2026, 11, 4))
    with pytest.raises(ValueError, match="positive"):
        day_intervals(
            parse_timestamp("2026-11-05T00:00:00Z"), parse_timestamp("2026-11-04T00:00:00Z")
        )


@pytest.mark.parametrize(
    "text,expected",
    [
        ("0001-01-01T00:00:00Z", datetime(1, 1, 1, tzinfo=UTC)),
        ("0001-01-01T09:00:00+09:00", datetime(1, 1, 1, tzinfo=UTC)),
        ("9999-12-31T14:59:59.999999Z", datetime(9999, 12, 31, 14, 59, 59, 999999, tzinfo=UTC)),
        (
            "9999-12-31T23:59:59.999999+09:00",
            datetime(9999, 12, 31, 14, 59, 59, 999999, tzinfo=UTC),
        ),
    ],
)
def test_supported_time_boundaries(text, expected):
    from geo_audit.timecut import as_utc

    assert parse_timestamp(text) == expected
    assert as_utc(datetime.fromisoformat(text)) == expected
    assert report_day(expected) == expected.date()


@pytest.mark.parametrize(
    "text",
    [
        "9999-12-31T23:00:00Z",
        "9999-12-31T15:00:00Z",
        "9999-12-31T23:59:59.999999-01:00",  # UTC normalization overflow.
        "0001-01-01T00:00:00+09:00",  # Local date exists, but UTC does not.
        "0001-01-01T08:59:59.999999+09:00",  # One microsecond before supported UTC.
    ],
)
def test_unsupported_time_boundaries(text):
    from geo_audit.timecut import as_utc

    value = datetime.fromisoformat(text)
    for operation in (
        lambda: parse_timestamp(text),
        lambda: as_utc(value),
        lambda: report_day(value),
        lambda: day_intervals(value, value),
    ):
        with pytest.raises(ValueError, match="TIMESTAMP_OUT_OF_RANGE"):
            operation()


def test_boundary_day_partitions():
    for start, end in [
        ("0001-01-01T00:00:00Z", "0001-01-01T00:00:01Z"),
        ("9999-12-31T14:59:59Z", "9999-12-31T14:59:59.999999Z"),
    ]:
        pieces = day_intervals(parse_timestamp(start), parse_timestamp(end))
        assert len(pieces) == 1
        assert (pieces[0].start, pieces[0].end) == (0, 1)
