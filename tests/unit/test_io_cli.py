import io
import subprocess
import sys
from pathlib import Path

import pytest

from geo_audit.io import FIELDS, format_number, parse_rows, read_csv
from geo_audit.timecut import report_day


def test_valid_normalized(valid_row):
    row = {**valid_row, "ts_utc": "2026-11-04T12:00:00+09:00"}
    parsed = parse_rows([row])[0]
    assert parsed.reasons == ()
    assert parsed.ping.timestamp.isoformat() == "2026-11-04T03:00:00+00:00"
    assert parsed.assignable
    assert parsed.raw == tuple(row.items())


@pytest.mark.parametrize(
    "field,value,reason",
    [
        ("driver_id", " ", "BAD_DRIVER_ID"),
        ("ping_id", "é", "BAD_PING_ID"),
        ("lat", "nan", "BAD_COORDINATE"),
        ("lon", "inf", "BAD_COORDINATE"),
        ("lon", "0", "BAD_COORDINATE"),
        ("lat", None, "BAD_COORDINATE"),
        ("ts_utc", None, "ts_utc:MISSING_TIMESTAMP"),
        ("received_at_utc", None, "received_at_utc:MISSING_TIMESTAMP"),
        ("received_at_utc", "2026-11-04T02:00:00Z", "RECEIPT_BEFORE_DEVICE"),
        ("is_synthetic", "yes", "BAD_SYNTHETIC_FLAG"),
    ],
)
def test_invalid_rows(valid_row, field, value, reason):
    rows = parse_rows([{**valid_row, field: value}])
    assert len(rows) == 1
    assert rows[0].ping is None
    assert reason in rows[0].reasons


def test_s12_quarantine_allocation(valid_row):
    changes = [
        {"lat": None},
        {"ts_utc": "invalid"},
        {"ts_utc": "2026-11-04T03:00:00"},
        {"driver_id": None},
    ]
    rows = parse_rows(
        [{**valid_row, **change, "ping_id": f"Q{i}"} for i, change in enumerate(changes)]
    )
    assert len(rows) == 4
    assert all(row.reasons and row.ping is None for row in rows)
    assert sum(row.assignable for row in rows) == 1
    assert sum(not row.assignable for row in rows) == 3
    assert str(report_day(rows[0].timestamp)) == "2026-11-04"


def test_csv_preserves_records(valid_row):
    text = ",".join(FIELDS) + "\n" + ",".join(valid_row[k] for k in FIELDS) + "\n\nshort\n"
    rows = read_csv(io.StringIO(text))
    assert len(rows) == 3
    assert [r.source_row for r in rows] == [1, 2, 3]
    assert rows[0].ping is not None
    assert all("BAD_FIELDS" in row.reasons for row in rows[1:])
    assert read_csv(io.StringIO("")) == ()
    with pytest.raises(ValueError):
        read_csv(io.StringIO("ping_id,ping_id\n"))


@pytest.mark.parametrize(
    "places,expected", [(10, "1.2345678901"), (6, "1.234568"), (3, "1.235"), (2, "1.23")]
)
def test_serialization(places, expected):
    value = 1.23456789012
    serialized = format_number(value, places)
    assert serialized == expected
    assert abs(float(serialized) - value) <= 0.5 * 10 ** (-places)


@pytest.mark.parametrize(
    "invocation",
    [[sys.executable, "-m", "geo_audit"], [str(Path(sys.executable).parent / "geo-audit")]],
)
def test_cli(invocation):
    result = subprocess.run(invocation + ["--version"], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "0.1.0"
    for command in ("demo", "generate", "check", "compare"):
        result = subprocess.run(invocation + [command], capture_output=True, text=True)
        assert result.returncode == 2
        assert "--output is required" in result.stderr


def test_parser_does_not_select_duplicates(valid_row):
    rows = parse_rows([valid_row, valid_row])
    assert len(rows) == 2
    assert all(row.ping is not None for row in rows)
    assert [row.source_row for row in rows] == [1, 2]


def test_receipt_naive_and_extra_csv(valid_row):
    row = parse_rows([{**valid_row, "received_at_utc": "2026-11-04T03:00:01"}])[0]
    assert "received_at_utc:NAIVE_TIMESTAMP" in row.reasons
    assert row.assignable
    text = ",".join(FIELDS) + "\n" + ",".join(valid_row[k] for k in FIELDS) + ",extra\n"
    result = read_csv(io.StringIO(text))
    assert len(result) == 1
    assert "BAD_FIELDS" in result[0].reasons
    assert dict(result[0].raw)["extra_7"] == "extra"


@pytest.mark.parametrize("value,places", [(float("nan"), 3), (float("inf"), 6), (1.0, 4)])
def test_invalid_serialization(value, places):
    with pytest.raises(ValueError):
        format_number(value, places)


@pytest.mark.parametrize(
    "timestamp",
    [
        "9999-12-31T23:00:00Z",
        "9999-12-31T15:00:00Z",
        "0001-01-01T00:00:00+09:00",
        "9999-12-31T23:59:59-01:00",
    ],
)
def test_out_of_range_row_preserved(valid_row, timestamp):
    raw = {**valid_row, "ts_utc": timestamp, "received_at_utc": timestamp}
    rows = parse_rows([raw])
    assert len(rows) == 1
    row = rows[0]
    assert dict(row.raw) == raw
    assert row.source_row == 1
    assert row.ping is None and row.timestamp is None and not row.assignable
    assert row.reasons == (
        "ts_utc:TIMESTAMP_OUT_OF_RANGE",
        "received_at_utc:TIMESTAMP_OUT_OF_RANGE",
    )
