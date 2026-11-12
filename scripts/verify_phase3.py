"""Verify executed Phase 3 totals against retained literals; no red/green runner."""

import argparse
import csv
import json
import math
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path

from geo_audit.calc_corrected import calculate
from geo_audit.calc_legacy import calculate as legacy_calculate
from geo_audit.geo import project_geojson
from geo_audit.io import parse_rows
from geo_audit.report import write_comparison


def finite_number(value, context):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"nonfinite or invalid numerical value: {context}")
    return value


def load_json(path):
    def invalid_constant(value):
        raise ValueError(f"nonfinite JSON value: {value}")

    return json.loads(path.read_text(), parse_constant=invalid_constant)


def keyed_totals(records, expected_keys, value_field, day_field):
    values = {}
    if not isinstance(records, list):
        raise ValueError("totals must be a list")
    for row in records:
        if set(row) != {"driver_id", day_field, value_field} | (
            {"date_basis"} if value_field == "legacy_m" else set()
        ):
            raise ValueError("malformed total record")
        key = (row["driver_id"], row[day_field])
        if key in values:
            raise ValueError(f"duplicate driver/date key: {key}")
        values[key] = finite_number(row[value_field], key)
    missing, extra = expected_keys - values.keys(), values.keys() - expected_keys
    if missing or extra:
        raise ValueError(
            f"total key mismatch: missing={sorted(missing)}, unexpected={sorted(extra)}"
        )
    return values


def validate_comparison(path, fixed, old, expected_keys):
    """Check the independently specified rectangular reporting grid and presence."""
    drivers = {driver for driver, _ in expected_keys}
    days = [date.fromisoformat(day).toordinal() for _, day in expected_keys]
    grid = (
        {
            (d, str(date.fromordinal(day)))
            for d in drivers
            for day in range(min(days), max(days) + 1)
        }
        | set(old)
        | expected_keys
    )
    seen = set()
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            key = (row["driver_id"], row["reporting_date"])
            if key in seen or key not in grid:
                raise ValueError(f"duplicate or unexpected comparison key: {key}")
            seen.add(key)
            for field, records in (("corrected", fixed), ("legacy", old)):
                if row[field + "_present"] != str(key in records):
                    raise ValueError(f"inconsistent presence flag: {key} {field}")
            if (
                row["legacy_date_basis"] != "UTC endpoint"
                or row["corrected_date_basis"] != "UTC+9 interval"
            ):
                raise ValueError("invalid date convention")
            # Grid padding is explicitly absent, not a missing required total.
            before = old[key] if key in old else 0
            after = fixed[key] if key in fixed else 0
            for field, want in (
                ("legacy_m", before),
                ("corrected_m", after),
                ("difference_m", after - before),
            ):
                actual = finite_number(float(row[field]), field)
                if abs(actual - want) > 0.000501:
                    raise ValueError(f"comparison value mismatch: {key} {field}")
    if seen != grid:
        raise ValueError("missing comparison driver/date rows")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    args = parser.parse_args()
    data = Path("data/synthetic")
    expected = load_json(Path("tests/expectations/analytic.json"))
    instances = load_json(data / "instances.json")
    expected_keys = set()
    legacy_keys = set()
    for instance in instances:
        first = date(2026, 11, 4) + timedelta(days=instance["copy"])
        legacy_keys.add((instance["driver"], str(first)))
        for offset, value in enumerate(expected[instance["scenario"]][1]):
            finite_number(value, instance["scenario"])
            expected_keys.add((instance["driver"], str(first + timedelta(days=offset))))
    fixed = keyed_totals(
        load_json(args.results / "corrected_totals.json"),
        expected_keys,
        "corrected_m",
        "reporting_date",
    )
    old = keyed_totals(
        load_json(Path("results/phase2/legacy_totals.json")), legacy_keys, "legacy_m", "report_date"
    )
    validate_comparison(args.results / "driver_day.csv", fixed, old, expected_keys)
    measurements = []
    for instance in instances:
        legacy, required = expected[instance["scenario"]]
        for value in legacy:
            finite_number(value, instance["scenario"])
        for i, want in enumerate(required):
            day = str(date(2026, 11, 4) + timedelta(days=instance["copy"] + i))
            key = (instance["driver"], day)
            actual = fixed[key]
            before = old[key] if key in legacy_keys else 0
            if abs(actual - want) > 0.01 or abs(before - legacy[i]) > 0.01:
                raise SystemExit(f"numeric gate failed: {key}")
            measurements.append(
                dict(
                    scenario=instance["scenario"],
                    driver_id=key[0],
                    reporting_date=day,
                    expected_m=want,
                    corrected_m=actual,
                    legacy_m=before,
                    classification="characterization"
                    if instance["scenario"] in ("S11", "S13")
                    else "billing",
                )
            )
    frozen = json.loads(Path("results/phase2/r5_only.json").read_text())
    rows = parse_rows(frozen["raw_rows"])
    roads = project_geojson(json.loads((data / "roads.geojson").read_text()), "roads")
    zone = project_geojson(json.loads((data / "zone.geojson").read_text()), "zone")
    corrected = calculate(rows, roads, zone)
    legacy = legacy_calculate(rows, zone)
    dates = ["2026-11-04", "2026-11-05"]
    actual = [corrected.totals[("SYN-R5-ONLY", day)] for day in dates]
    primary_keys = {("SYN-R5-ONLY", day) for day in dates}
    if set(corrected.totals) != primary_keys or set(legacy.totals) != {("SYN-R5-ONLY", dates[0])}:
        raise ValueError("primary total key mismatch")
    # This fixture has exactly one UTC legacy date; the second date is explicitly absent.
    before = [legacy.totals[("SYN-R5-ONLY", dates[0])], 0]
    if before != frozen["actual_legacy_m"] or any(abs(v - 50) > 0.01 for v in actual):
        raise SystemExit("primary numeric gate failed")
    with tempfile.TemporaryDirectory() as temporary:
        primary = Path(temporary) / "primary"
        write_comparison(primary, rows, legacy, corrected, Path("results/phase2/r5_only.json"))
        target = args.results / "r5_only"
        if target.exists():
            wanted = {p.name: p.read_bytes() for p in primary.iterdir()}
            existing = {p.name: p.read_bytes() for p in target.iterdir() if p.is_file()}
            if wanted != existing:
                raise ValueError("primary evidence mismatch")
        else:
            shutil.copytree(primary, target)
    payload = dict(
        primary=dict(
            legacy_m=before,
            corrected_m=actual,
            independent_required_m=[100 * 5 / 10, 100 * 5 / 10],
            records=frozen["raw_rows"],
        ),
        measurements=measurements,
        tolerance_m=0.01,
        instances_verified=len(instances),
    )
    (args.results / "numerical_verification.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    print(f"PASS: {len(instances)} instances; isolated R5 {before} -> {actual}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError) as error:
        raise SystemExit(f"verification failed: {error}") from None
