"""Phase 3 numerical/state tests; expectations are literals or elementary arithmetic."""

import builtins
import csv
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, Polygon, box

from geo_audit.calc_corrected import allocate_segment, calculate
from geo_audit.calc_legacy import calculate as legacy_calculate
from geo_audit.geo import project_geojson
from geo_audit.io import parse_rows, read_csv
from geo_audit.report import reconcile_corrected, write_comparison
from geo_audit_synthetic.generator import SCENARIOS, scenario_rows

ZONE = box(322050, 4149500, 327950, 4150500)
ROADS = LineString([(320000, 4150000), (330000, 4150000)])
T = datetime(2026, 11, 4, 3, tzinfo=UTC)
EXPECTED = json.loads(Path("tests/expectations/analytic.json").read_text())


def raw_points(points, start=T, driver="SYN-TEST"):
    transform = Transformer.from_crs(32652, 4326, always_xy=True)
    rows = []
    for i, (east, north, seconds) in enumerate(points):
        lon, lat = transform.transform(320000 + east, 4150000 + north)
        stamp = start + timedelta(seconds=seconds)
        rows.append(
            dict(
                ping_id=f"{driver}-P{i}",
                driver_id=driver,
                ts_utc=stamp.isoformat(),
                received_at_utc=(stamp + timedelta(seconds=1)).isoformat(),
                lon=f"{lon:.10f}",
                lat=f"{lat:.10f}",
                is_synthetic="true",
            )
        )
    return rows


def run(raw):
    return calculate(parse_rows(raw), ROADS, ZONE)


def test_primary_frozen_r5():
    frozen = json.loads(Path("results/phase2/r5_only.json").read_text())
    rows = parse_rows(frozen["raw_rows"])
    legacy = legacy_calculate(rows, ZONE)
    fixed = calculate(rows, ROADS, ZONE)
    dates = ["2026-11-04", "2026-11-05"]
    old = [legacy.totals.get(("SYN-R5-ONLY", d), 0) for d in dates]
    new = [fixed.totals[("SYN-R5-ONLY", d)] for d in dates]
    assert old == pytest.approx(frozen["actual_legacy_m"], abs=1e-6, rel=0)
    assert old == pytest.approx([100, 0], abs=0.01)
    assert new == pytest.approx([100 * 5 / 10, 100 * 5 / 10], abs=0.01)
    assert fixed.segments[0]["zone_intervals"] == ((0, 1),)
    assert fixed.decisions[1]["speed_kmh"] == pytest.approx(36, abs=0.001)


@pytest.mark.parametrize("name", SCENARIOS)
def test_all_analytic_corrected(name):
    rows = parse_rows(scenario_rows(name)[0])
    fixed = calculate(rows, ROADS, ZONE)
    old = legacy_calculate(rows, ZONE)
    legacy_expected, required = EXPECTED[name]
    for i, value in enumerate(required):
        key = (f"SYN-{name}-00", str(date(2026, 11, 4) + timedelta(days=i)))
        assert fixed.totals.get(key, 0) == pytest.approx(value, abs=0.01)
        assert old.totals.get(key, 0) == pytest.approx(legacy_expected[i], abs=0.01)
    reconcile_corrected(rows, fixed)


def test_invalid_duplicate_winner_no_fallback():
    result = run(scenario_rows("S3b")[0])
    by_id = {d["ping_id"].split("-")[-1]: d for d in result.decisions}
    assert by_id["D001"]["state"] == "rejected_noise"
    assert by_id["D001"]["reasons"] == ["DUPLICATE_CONFLICT", "OFF_ROAD"]
    assert by_id["P001"]["state"] == "rejected_duplicate"
    assert by_id["P001"]["road_distance_m"] is None
    assert by_id["P002"]["anchor_id"].endswith("P000")
    assert sum(result.totals.values()) == pytest.approx(200, abs=0.01)


def test_equivalent_instants_identical_receipt_lexical_winner():
    raw = raw_points([(3000, 0, 0), (3100, 0, 10), (3200, 0, 20)])
    copy = dict(
        raw[1],
        ping_id="AAA",
        ts_utc="2026-11-04T12:00:10+09:00",
        received_at_utc="2026-11-04T12:00:11+09:00",
    )
    result = run([*raw, copy])
    assert result.decisions[1]["state"] == "rejected_duplicate"
    assert result.decisions[1]["duplicate_winner"] == "AAA"
    assert result.decisions[-1]["state"] == "accepted"
    assert sum(result.totals.values()) == pytest.approx(200, abs=0.01)


@pytest.mark.parametrize("malformed", [False, True])
def test_duplicate_id_conflict_includes_malformed_copy(malformed):
    raw = raw_points([(3000, 0, 0), (3100, 0, 10)])
    copy = dict(raw[1], lat="" if malformed else raw[0]["lat"])
    result = run([*raw, copy])
    assert [d["state"] for d in result.decisions] == ["accepted", "quarantined", "quarantined"]
    assert all("ID_CONFLICT" in d["reasons"] for d in result.decisions[1:])
    assert sum(result.totals.values()) == 0
    reversed_result = run([copy, *reversed(raw)])
    assert Counter(d["state"] for d in result.decisions) == Counter(
        d["state"] for d in reversed_result.decisions
    )


def test_identical_id_normalized_payload_copies():
    raw = raw_points([(3000, 0, 0), (3100, 0, 10)])
    copy = dict(raw[1], ts_utc="2026-11-04T12:00:10+09:00", lon=str(float(raw[1]["lon"])))
    result = run([*raw, copy])
    assert Counter(d["state"] for d in result.decisions) == {"accepted": 2, "rejected_duplicate": 1}
    assert sum(result.totals.values()) == pytest.approx(100, abs=0.01)


@pytest.mark.parametrize(
    "field,value,reason,assignable",
    [
        ("driver_id", "", "BAD_DRIVER_ID", False),
        ("ping_id", "!", "BAD_PING_ID", True),
        ("ts_utc", "", "MISSING_TIMESTAMP", False),
        ("ts_utc", "bad", "BAD_TIMESTAMP", False),
        ("received_at_utc", "", "MISSING_TIMESTAMP", True),
        ("lat", "", "BAD_COORDINATE", True),
    ],
)
def test_quarantine_preserved(field, value, reason, assignable):
    raw = raw_points([(3000, 0, 0)])
    raw[0][field] = value
    result = run(raw)
    d = result.decisions[0]
    assert d["state"] == "quarantined" and d["assignable"] is assignable
    assert any(reason in s for s in d["reasons"])
    assert d["raw"] == raw[0]
    assert result.status == "NO_USABLE_DATA"


def test_s12_counts():
    result = run(scenario_rows("S12")[0])
    assert Counter(d["state"] for d in result.decisions) == {"accepted": 81, "quarantined": 4}
    quarantine = [d for d in result.decisions if d["state"] == "quarantined"]
    assert sum(d["assignable"] for d in quarantine) == 1
    assert len(result.decisions) == 85
    assert sum(result.totals.values()) == pytest.approx(5900, abs=0.01)


def test_empty_and_all_noise():
    assert run([]).status == "NO_USABLE_DATA"
    result = run(raw_points([(3000, 150, 0), (3100, 150, 10)]))
    assert result.status == "OK"
    assert [d["state"] for d in result.decisions] == ["rejected_noise"] * 2
    assert result.totals == {("SYN-TEST", "2026-11-04"): 0}
    assert result.segments == ()


def test_consecutive_spikes_retained_anchor_and_interleaved_drivers():
    a = raw_points([(3000, 0, 0), (4100, 0, 10), (4200, 0, 20), (3300, 0, 30)])
    b = raw_points([(5000, 0, 0), (5100, 0, 10), (5200, 0, 20), (5300, 0, 30)], driver="SYN-B")
    result = run([r for pair in zip(a, b, strict=True) for r in pair])
    decisions = [d for d in result.decisions if d["driver_id"] == "SYN-TEST"]
    assert [d["state"] for d in decisions] == [
        "accepted",
        "rejected_noise",
        "rejected_noise",
        "accepted",
    ]
    assert [d["anchor_id"] for d in decisions[1:]] == ["SYN-TEST-P0"] * 3
    assert [d["speed_kmh"] for d in decisions[1:]] == pytest.approx([396, 216, 36], abs=0.001)
    assert list(result.totals.values()) == pytest.approx([300, 300], abs=0.01)


def test_offroad_precedes_speed_and_does_not_anchor():
    result = run(raw_points([(3000, 0, 0), (4100, 150, 10), (3200, 0, 20)]))
    assert result.decisions[1]["reasons"] == ["OFF_ROAD"]
    assert result.decisions[1]["speed_kmh"] is None
    assert result.decisions[2]["anchor_id"] == "SYN-TEST-P0"
    assert sum(result.totals.values()) == pytest.approx(200, abs=0.01)


def test_zero_movement_and_gap_warning():
    result = run(raw_points([(3000, 0, 0), (3000, 0, 61)]))
    assert [d["state"] for d in result.decisions] == ["accepted", "accepted_warning"]
    assert result.decisions[1]["reasons"] == ["GAP"]
    assert result.decisions[1]["gap_s"] == 61
    assert result.segments[0]["included_m"] == 0


@pytest.mark.parametrize(
    "start,end,zone,want",
    [
        ((2000, 0), (2100, 0), box(2050, -500, 7950, 500), 50),
        ((2000, 0), (8000, 0), box(2050, -500, 7950, 500), 5900),
        ((-1, 1), (1, -1), box(0, 0, 1, 1), 0),
        ((-1, 0), (2, 0), box(0, 0, 1, 1), 1),
        (
            (0, 0),
            (100, 0),
            Polygon([(10, -1), (30, -1), (30, 1), (60, 1), (60, -1), (90, -1), (90, 2), (10, 2)]),
            50,
        ),
    ],
)
def test_segment_geometry_numeric(start, end, zone, want):
    _, _, allocations = allocate_segment(start, end, T, T + timedelta(seconds=600), zone)
    assert sum(a["included_m"] for a in allocations) == pytest.approx(want, abs=1e-6)


@pytest.mark.parametrize(
    "start,seconds,want",
    [
        ("2026-11-04T14:59:50+00:00", 10, [100]),
        ("2026-11-04T15:00:00+00:00", 10, [100]),
        (
            "2026-11-04T14:59:55+00:00",
            86410,
            [100 * 5 / 86410, 100 * 86400 / 86410, 100 * 5 / 86410],
        ),
    ],
)
def test_exact_midnight_and_multiple_days(start, seconds, want):
    stamp = datetime.fromisoformat(start)
    _, _, allocations = allocate_segment(
        (3000, 0), (3100, 0), stamp, stamp + timedelta(seconds=seconds), box(2050, -1, 7950, 1)
    )
    assert [a["included_m"] for a in allocations] == pytest.approx(want, abs=1e-6)
    first_day = "2026-11-05" if start.endswith("15:00:00+00:00") else "2026-11-04"
    assert allocations[0]["report_date"] == first_day


def test_permutation_and_blind_calculation(monkeypatch):
    raw = scenario_rows("S3b")[0] + scenario_rows("S6c")[0]
    forward = run(raw)
    reversed_rows = parse_rows(list(reversed(raw)))
    with monkeypatch.context() as m:

        def forbidden(*a, **k):
            raise AssertionError("calculation must not read external files")

        m.setattr(builtins, "open", forbidden)
        m.setattr(Path, "open", forbidden)
        backward = calculate(reversed_rows, ROADS, ZONE)
    assert forward.totals == backward.totals
    assert {(d["ping_id"], d["state"], tuple(d["reasons"])) for d in forward.decisions} == {
        (d["ping_id"], d["state"], tuple(d["reasons"])) for d in backward.decisions
    }


def test_reconciliation_rejects_date_transfer(tmp_path):
    rows = parse_rows(
        raw_points([(3000, 0, 0), (3100, 0, 10)], T.replace(hour=14, minute=59, second=55))
    )
    result = calculate(rows, ROADS, ZONE)
    totals = dict(result.totals)
    totals[("SYN-TEST", "2026-11-04")] += 25
    totals[("SYN-TEST", "2026-11-05")] -= 25
    with pytest.raises(ValueError, match="driver/day"):
        write_comparison(
            tmp_path / "bad",
            rows,
            legacy_calculate(rows, ZONE),
            replace(result, totals=totals),
            Path(__file__),
        )
    assert not (tmp_path / "bad").exists()


def test_full_dataset_compare_cli_timezone_and_reconciliation(tmp_path):
    outputs = []
    for tz in ["UTC", "Pacific/Honolulu"]:
        out = tmp_path / tz.replace("/", "_")
        command = [
            sys.executable,
            "-m",
            "geo_audit",
            "compare",
            "--input",
            "data/synthetic/SYNTHETIC_gps_pings.csv",
            "--roads",
            "data/synthetic/roads.geojson",
            "--zone",
            "data/synthetic/zone.geojson",
            "--output",
            str(out),
        ]
        p = subprocess.run(command, env={**os.environ, "TZ": tz}, capture_output=True, text=True)
        assert p.returncode == 0, p.stderr
        outputs.append(out)
    assert {p.name: p.read_bytes() for p in outputs[0].iterdir()} == {
        p.name: p.read_bytes() for p in outputs[1].iterdir()
    }
    with Path("data/synthetic/SYNTHETIC_gps_pings.csv").open() as f:
        rows = read_csv(f)
    roads = project_geojson(json.loads(Path("data/synthetic/roads.geojson").read_text()), "roads")
    zone = project_geojson(json.loads(Path("data/synthetic/zone.geojson").read_text()), "zone")
    result = calculate(rows, roads, zone)
    for instance in json.loads(Path("data/synthetic/instances.json").read_text()):
        for i, want in enumerate(EXPECTED[instance["scenario"]][1]):
            key = (
                instance["driver"],
                str(date(2026, 11, 4) + timedelta(days=instance["copy"] + i)),
            )
            assert result.totals.get(key, 0) == pytest.approx(want, abs=0.01)
    summary = json.loads((outputs[0] / "summary.json").read_text())
    assert summary["input_rows"] == 3327
    assert sum(summary["states"].values()) == 3327
    assert (
        sum(x["count"] for x in summary["assigned_states"])
        + sum(summary["unassignable_states"].values())
        == 3327
    )
    with (outputs[0] / "driver_day.csv").open() as f:
        report = list(csv.DictReader(f))
    assert len(report) == 63 * 4
    assert sum(float(r["corrected_m"]) for r in report) == pytest.approx(
        sum(result.totals.values()), abs=len(report) * 0.0005
    )
    ledger = json.loads((outputs[0] / "segments_corrected.json").read_text())
    sums = defaultdict(float)
    counts = Counter()
    for segment in ledger:
        for allocation in segment["allocations"]:
            key = (segment["driver_id"], allocation["report_date"])
            sums[key] += allocation["included_m"]
            counts[key] += 1
    for row in report:
        key = (row["driver_id"], row["reporting_date"])
        assert abs(float(row["corrected_m"]) - sums[key]) <= 0.0005 + counts[key] * 0.0000005 + 1e-6
    assert (outputs[0] / "segments_legacy.json").read_bytes() == Path(
        "results/phase2/segments_legacy.json"
    ).read_bytes()


@pytest.mark.parametrize(
    "mutation", ["missing_total", "extra_total", "duplicate_segment", "missing_decision"]
)
def test_corrected_report_rejects_incomplete_evidence(mutation):
    rows = parse_rows(raw_points([(3000, 0, 0), (3100, 0, 10)]))
    result = calculate(rows, ROADS, ZONE)
    if mutation == "missing_total":
        result = replace(result, totals={})
    elif mutation == "extra_total":
        result = replace(result, totals={**result.totals, ("SYN-TEST", "2026-11-09"): 0})
    elif mutation == "duplicate_segment":
        result = replace(result, segments=result.segments * 2)
    else:
        result = replace(result, decisions=result.decisions[:-1])
    with pytest.raises(ValueError):
        reconcile_corrected(rows, result)


def test_compare_outer_union_and_no_usable_evidence(tmp_path):
    raw = raw_points([(3000, 0, 0), (3100, 0, 10)], T.replace(hour=16))
    rows = parse_rows(raw)
    summary = write_comparison(
        tmp_path / "union",
        rows,
        legacy_calculate(rows, ZONE),
        calculate(rows, ROADS, ZONE),
        Path(__file__),
    )
    assert summary["driver_day_rows"] == 2
    with (tmp_path / "union/driver_day.csv").open() as f:
        entries = list(csv.DictReader(f))
    assert [
        (r["reporting_date"], r["legacy_present"], r["corrected_present"]) for r in entries
    ] == [("2026-11-04", "True", "False"), ("2026-11-05", "False", "True")]
    assert [(float(r["legacy_m"]), float(r["corrected_m"])) for r in entries] == [
        (100, 0),
        (0, 100),
    ]
    raw[0]["lat"] = ""
    rows = parse_rows(raw[:1])
    result = calculate(rows, ROADS, ZONE)
    summary = write_comparison(
        tmp_path / "empty", rows, legacy_calculate(rows, ZONE), result, Path(__file__)
    )
    assert summary["status"] == "NO_USABLE_DATA"
    assert summary["states"] == {"quarantined": 1}


def test_compare_no_usable_exit_preserves_quarantine(tmp_path):
    raw = raw_points([(3000, 0, 0)])
    raw[0]["lat"] = ""
    source = tmp_path / "bad.csv"
    with source.open("w") as f:
        writer = csv.DictWriter(f, fieldnames=list(raw[0]))
        writer.writeheader()
        writer.writerows(raw)
    output = tmp_path / "report"
    p = subprocess.run(
        [
            sys.executable,
            "-m",
            "geo_audit",
            "compare",
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
    assert p.returncode == 2
    decisions = json.loads((output / "ping_decisions.json").read_text())
    assert decisions[0]["raw"]["lat"] == ""
    assert decisions[0]["state"] == "quarantined"
