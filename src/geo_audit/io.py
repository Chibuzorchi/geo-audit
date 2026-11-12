"""Row parsing preserves source evidence. No deduplication or billing selection."""

import csv
import math
import re
from collections.abc import Iterable, Mapping
from typing import TextIO

from geo_audit.config import validate_coordinate
from geo_audit.models import ParsedRow, Ping
from geo_audit.timecut import parse_timestamp

FIELDS = ("ping_id", "driver_id", "ts_utc", "lat", "lon", "received_at_utc", "is_synthetic")


def _identifier(value: str | None) -> str | None:
    return value if value and re.fullmatch(r"[A-Za-z0-9_-]+", value) else None


def parse_row(raw: Mapping[str, str | None], source_row: int) -> ParsedRow:
    reasons = []
    ping_id, driver_id = _identifier(raw.get("ping_id")), _identifier(raw.get("driver_id"))
    if ping_id is None:
        reasons.append("BAD_PING_ID")
    if driver_id is None:
        reasons.append("BAD_DRIVER_ID")
    times = []
    for field in ("ts_utc", "received_at_utc"):
        try:
            times.append(parse_timestamp(raw.get(field)))
        except ValueError as error:
            reasons.append(f"{field}:{error}")
            times.append(None)
    timestamp, received = times
    if timestamp is not None and received is not None and received < timestamp:
        reasons.append("RECEIPT_BEFORE_DEVICE")
    lon = lat = None
    try:
        lon, lat = float(raw.get("lon")), float(raw.get("lat"))
        validate_coordinate(lon, lat)
    except (TypeError, ValueError):
        reasons.append("BAD_COORDINATE")
    synthetic = raw.get("is_synthetic")
    if synthetic not in ("true", "false"):
        reasons.append("BAD_SYNTHETIC_FLAG")
    if set(raw) != set(FIELDS):
        reasons.append("BAD_FIELDS")
    ping = None
    if not reasons:
        ping = Ping(ping_id, driver_id, timestamp, received, lon, lat, synthetic == "true")
    return ParsedRow(source_row, tuple(raw.items()), ping, driver_id, timestamp, tuple(reasons))


def parse_rows(rows: Iterable[Mapping[str, str | None]]) -> tuple[ParsedRow, ...]:
    return tuple(parse_row(row, number) for number, row in enumerate(rows, 1))


def read_csv(stream: TextIO) -> tuple[ParsedRow, ...]:
    """Preserve every CSV record, including blank/mis-sized records; reject bad headers."""
    reader = csv.reader(stream, strict=True)
    header = next(reader, None)
    if header is None:
        return ()
    if len(header) != len(FIELDS) or set(header) != set(FIELDS):
        raise ValueError("CSV header must contain each required field exactly once")
    records = []
    for number, cells in enumerate(reader, 1):
        row = {name: cells[i] if i < len(cells) else None for i, name in enumerate(header)}
        for i in range(len(header), len(cells)):
            row[f"extra_{i}"] = cells[i]
        if len(cells) < len(header):
            row["short_record"] = str(len(cells))
        records.append(parse_row(row, number))
    return tuple(records)


def format_number(value: float, places: int) -> str:
    """Output rounding only; supported precision: geographic, ledger, report, display."""
    if not math.isfinite(value) or places not in (10, 6, 3, 2):
        raise ValueError("invalid serialization value or precision")
    return f"{value:.{places}f}"


def normalized_payload(row: ParsedRow) -> tuple:
    """Canonical field identity, including malformed fields for ID-conflict checks.

    Valid field values normalize even when another field quarantines the row.
    Invalid values retain their literal representation; none are silently repaired.
    """
    values = []
    for field, value in sorted(row.raw):
        canonical = ("raw", value)
        if field in ("ts_utc", "received_at_utc"):
            try:
                canonical = ("instant", parse_timestamp(value).isoformat())
            except ValueError:
                pass
        elif field in ("lon", "lat"):
            try:
                number = float(value)
                if math.isfinite(number):
                    canonical = ("number", number)
            except (TypeError, ValueError):
                pass
        values.append((field, canonical))
    return tuple(values)
