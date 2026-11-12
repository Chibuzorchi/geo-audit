"""Explicit-offset instants and fixed UTC+9 segment partitions."""

import re
from datetime import UTC, date, datetime, time, timedelta, timezone

from geo_audit.models import DayInterval

REPORT_ZONE = timezone(timedelta(hours=9))
_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})")


def as_utc(value: datetime) -> datetime:
    """Require an instant representable in both UTC and fixed UTC+9.

    UTC range: 0001-01-01T00:00:00 through 9999-12-31T14:59:59.999999.
    Out-of-range conversion raises ValueError(TIMESTAMP_OUT_OF_RANGE).
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    try:
        normalized = value.astimezone(UTC)
        normalized.astimezone(REPORT_ZONE)
    except OverflowError:
        raise ValueError("TIMESTAMP_OUT_OF_RANGE") from None
    return normalized


def parse_timestamp(value: str | None) -> datetime:
    if not value:
        raise ValueError("MISSING_TIMESTAMP")
    if not _PATTERN.fullmatch(value):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError("BAD_TIMESTAMP") from None
        if parsed.tzinfo is None:
            raise ValueError("NAIVE_TIMESTAMP")
        raise ValueError("BAD_TIMESTAMP")
    if value[-6:-5] in ("+", "-"):
        if int(value[-5:-3]) > 23 or int(value[-2:]) > 59:
            raise ValueError("BAD_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValueError("BAD_TIMESTAMP") from None
    return as_utc(parsed)


def report_day(value: datetime) -> date:
    return as_utc(value).astimezone(REPORT_ZONE).date()


def day_intervals(start: datetime, end: datetime) -> tuple[DayInterval, ...]:
    start, end = as_utc(start), as_utc(end)
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        raise ValueError("elapsed time must be positive")
    cursor = start
    pieces = []
    while cursor < end:
        day = report_day(cursor)
        if day == report_day(end):
            stop = end
        else:
            cut = datetime.combine(day + timedelta(days=1), time(), REPORT_ZONE)
            stop = min(end, cut.astimezone(UTC))
        pieces.append(
            DayInterval(
                day,
                (cursor - start).total_seconds() / seconds,
                (stop - start).total_seconds() / seconds,
            )
        )
        cursor = stop
    return tuple(pieces)
