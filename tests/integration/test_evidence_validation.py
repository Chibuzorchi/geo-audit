"""Phase 3 audit regressions: invalid evidence must never be accepted or repaired."""

import copy
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_corrected import ROADS, ZONE, T, raw_points

from geo_audit.calc_corrected import calculate
from geo_audit.calc_legacy import calculate as legacy
from geo_audit.io import parse_rows
from geo_audit.report import write_comparison


@pytest.mark.parametrize(
    "mutation,diagnostic",
    [
        ("nan", "nonfinite"),
        ("duplicate", "duplicate driver/date"),
        ("missing_zero", "missing="),
        ("extra", "unexpected="),
        ("presence", "inconsistent presence"),
        ("missing_comparison", "missing comparison"),
        ("comparison_nan", "nonfinite"),
    ],
)
def test_verifier_rejects_corrupt_evidence(tmp_path, mutation, diagnostic):
    out = tmp_path / "results"
    shutil.copytree("results/phase3", out)
    path = out / "corrected_totals.json"
    records = json.loads(path.read_text())
    if mutation == "nan":
        records[0]["corrected_m"] = float("nan")
    elif mutation == "duplicate":
        records.append(dict(records[0]))
    elif mutation == "missing_zero":
        records = [r for r in records if not r["driver_id"].startswith("SYN-S14-")]
    elif mutation == "extra":
        records.append(dict(driver_id="SYN-FAKE", reporting_date="2030-01-01", corrected_m=1000000))
    else:
        comparison = out / "driver_day.csv"
        with comparison.open() as stream:
            reader = csv.DictReader(stream)
            fields = reader.fieldnames
            entries = list(reader)
        if mutation == "presence":
            entries[0]["corrected_present"] = "False"
        elif mutation == "missing_comparison":
            entries.pop()
        else:
            entries[0]["corrected_m"] = "nan"
        with comparison.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(entries)
    path.write_text(json.dumps(records))
    before = path.read_bytes()
    process = subprocess.run(
        [sys.executable, "scripts/verify_phase3.py", "--results", str(out)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 1
    assert diagnostic in process.stderr
    assert "PASS" not in process.stdout
    assert "Traceback" not in process.stderr
    assert path.read_bytes() == before


def test_canonical_verification_passes_without_changing_numeric_evidence(tmp_path):
    out = tmp_path / "results"
    shutil.copytree("results/phase3", out)
    before = {str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    process = subprocess.run(
        [sys.executable, "scripts/verify_phase3.py", "--results", str(out)],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stderr
    assert "PASS: 63 instances" in process.stdout
    assert before == {
        str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "mutation,diagnostic",
    [
        ("nan_included", "nonfinite"),
        ("forged_source", "source identity"),
        ("impossible_date", "allocation dates"),
        ("negative_fraction", "zone-intersection"),
        ("overlap", "zone-intersection"),
        ("nan_fraction", "nonfinite"),
        ("wrong_decision", "decision source identity"),
        ("balanced_transfer", "allocation amount"),
        ("nan_speed", "nonfinite"),
    ],
)
def test_report_rejects_corrupted_corrected_result(tmp_path, mutation, diagnostic):
    frozen = json.loads(Path("results/phase2/r5_only.json").read_text())
    rows = parse_rows(frozen["raw_rows"])
    result = copy.deepcopy(calculate(rows, ROADS, ZONE))
    segment = result.segments[0]
    if mutation == "nan_included":
        segment["included_m"] = float("nan")
    elif mutation == "forged_source":
        segment.update(from_id="NONEXISTENT", from_time="1900-01-01T00:00:00+00:00")
    elif mutation == "impossible_date":
        value = sum(result.totals.values())
        for key in result.totals:
            result.totals[key] = 0
        result.totals[("SYN-R5-ONLY", "2030-01-01")] = value
        segment["allocations"] = [dict(report_date="2030-01-01", included_m=value)]
    elif mutation == "negative_fraction":
        segment["zone_intervals"] = [(-0.1, 1)]
    elif mutation == "overlap":
        segment["zone_intervals"] = [(0, 0.7), (0.6, 1)]
    elif mutation == "nan_fraction":
        segment["zone_intervals"] = [(0, float("nan"))]
    elif mutation == "wrong_decision":
        result.decisions[0]["ping_id"] = "NONEXISTENT"
    elif mutation == "nan_speed":
        result.decisions[1]["speed_kmh"] = float("nan")
    else:
        segment["allocations"][0]["included_m"] += 25
        segment["allocations"][1]["included_m"] -= 25
        result.totals[("SYN-R5-ONLY", "2026-11-04")] += 25
        result.totals[("SYN-R5-ONLY", "2026-11-05")] -= 25
    with pytest.raises(ValueError, match=diagnostic):
        write_comparison(tmp_path / "out", rows, legacy(rows, ZONE), result, Path(__file__))
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize(
    "distance,seconds,expected",
    [
        (100, 10, [50, 50]),
        (0, 10, [0, 0]),
        (100, 86410, [100 * 5 / 86410, 100 * 86400 / 86410, 100 * 5 / 86410]),
    ],
)
def test_report_accepts_valid_midnight_zero_and_multiday(tmp_path, distance, seconds, expected):
    rows = parse_rows(
        raw_points(
            [(3000, 0, 0), (3000 + distance, 0, seconds)], T.replace(hour=14, minute=59, second=55)
        )
    )
    result = calculate(rows, ROADS, ZONE)
    write_comparison(tmp_path / "out", rows, legacy(rows, ZONE), result, Path(__file__))
    assert [v["included_m"] for v in result.segments[0]["allocations"]] == pytest.approx(
        expected, abs=0.01
    )
    assert json.loads((tmp_path / "out/summary.json").read_text())["status"] == "OK"


@pytest.mark.parametrize("command", ["compare", "check"])
def test_malformed_csv_cli_is_input_error(tmp_path, command):
    source = tmp_path / "broken.csv"
    source.write_text(
        'ping_id,driver_id,ts_utc,lat,lon,received_at_utc,is_synthetic\n"unterminated'
    )
    output = tmp_path / "out"
    process = subprocess.run(
        [
            sys.executable,
            "-m",
            "geo_audit",
            command,
            "--input",
            str(source),
            "--roads",
            "data/synthetic/roads.geojson",
            "--zone",
            "data/synthetic/zone.geojson",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 2
    assert "malformed CSV: unexpected end of data" in process.stderr
    assert "Traceback" not in process.stderr
    assert not output.exists()
    assert process.stdout == ""
