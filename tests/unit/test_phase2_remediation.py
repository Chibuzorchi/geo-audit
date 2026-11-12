"""Focused audit regressions; literal expectations independent of billing code."""

import importlib.util
import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_legacy_checker import ROADS, ZONE, T, build

from geo_audit.calc_legacy import calculate
from geo_audit.checker import audit_legacy, inspect
from geo_audit.report import write_baseline
from geo_audit_synthetic.generator import scenario_rows

spec = importlib.util.spec_from_file_location("discovery", "scripts/discover_baseline.py")
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)


def test_r5_only_midnight_literal_vectors():
    fixture = json.loads(Path("tests/expectations/r5_midnight.json").read_text())
    rows = build(
        [("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1)],
        start=T.replace(hour=14, minute=59, second=55),
    )
    result = calculate(rows, ZONE)
    actual = [result.totals.get(("SYN-T01", day), 0) for day in fixture["dates"]]
    assert actual == pytest.approx(fixture["legacy_m"], abs=0.01)
    assert fixture["required_m"] == [100 * 5 / 10, 100 * 5 / 10]
    assert 100 / 10 * 3.6 == 36
    conflicts = audit_legacy(rows, ROADS, ZONE, result)
    assert [f["rule"] for f in conflicts] == ["R5_UTC_DATE"]


def test_combined_conflicts_visible_and_r5_reconciles():
    from geo_audit.io import parse_rows

    rows = parse_rows(scenario_rows("S8")[0])
    result = calculate(rows, ZONE)
    ledger = [dict(segment=i, **s) for i, s in enumerate(result.segments)]
    conflicts = audit_legacy(rows, ROADS, ZONE, result)
    evidence = discovery.evidence_for("SYN-S8-00", ["R5_UTC_DATE"], ledger, conflicts)
    entry = [e for e in evidence if e["ledger"]["to_id"].endswith("P011")]
    assert {e["rule"] for e in entry} == {"R5_UTC_DATE", "R6_ENDPOINT"}
    assert next(e for e in entry if e["rule"] == "R6_ENDPOINT")["selected_category"] is False
    assert next(e for e in entry if e["rule"] == "R6_ENDPOINT")["measurements"][
        "in_zone_length_m"
    ] == pytest.approx(50, abs=0.01)
    measurements = []
    for copy in range(3):
        for name, required in [("S7", [2950, 2950]), ("S8", [20, 5880])]:
            for offset in range(2):
                old = [5900, 0][offset]
                measurements.append(
                    dict(
                        scenario=name,
                        copy=copy,
                        report_day_utc9=f"2026-11-{4 + copy + offset:02}",
                        expected_m=required[offset],
                        expected_legacy_m=old,
                        difference_m=old - required[offset],
                    )
                )
    a = discovery.r5_attribution(measurements)
    assert [
        a[k]
        for k in (
            "observed_absolute_m",
            "isolated_r5_absolute_m",
            "r6_interaction_absolute_m",
            "r5_moved_m",
            "net_m",
            "positive_m",
            "negative_m",
        )
    ] == [52980, 52380, 600, 26190, 0, 26490, -26490]


@pytest.mark.parametrize(
    "points,pairs",
    [
        ([(3000, 0), (4100, 0), (4200, 0)], [("A", "B")]),  # second spike missed by raw pairs
        ([(3000, 0), (4100, 0), (3200, 0)], [("A", "B"), ("B", "C")]),  # valid C implicated
        ([(3000, 0), (4100, 150), (3200, 0)], [("A", "B"), ("B", "C")]),  # road rejects B first
    ],
)
def test_speed_anomalies_never_assert_acceptance(points, pairs):
    rows = build([(chr(65 + i), i * 10, e, n, 1) for i, (e, n) in enumerate(points)])
    findings = inspect(rows, ROADS, ZONE)
    raw = [f for f in findings if f["rule"] == "RAW_PAIR_SPEED_ANOMALY"]
    assert [tuple(f["ids"]) for f in raw] == pairs
    legacy = audit_legacy(rows, ROADS, ZONE, calculate(rows, ZONE))
    for f in raw + [f for f in legacy if "SPEED" in f["rule"]]:
        assert f["kind"] == "provisional_anomaly"
    assert not any(f["rule"].startswith("R2") for f in findings + legacy)
    if points[1][1]:
        assert any(f["rule"] == "R1" and f["ids"] == ["B"] for f in findings)


def test_s6b_return_is_not_speed_rejection():
    rows = build([("A", 0, 4900, 0, 1), ("B", 10, 5318.06, 0, 1), ("C", 20, 5100, 0, 1)])
    raw = [f for f in inspect(rows, ROADS, ZONE) if "SPEED" in f["rule"]]
    assert [f["ids"] for f in raw] == [["A", "B"]]
    assert raw[0]["measurements"]["speed_kmh"] == pytest.approx(150.5016, abs=0.001)
    assert 218.06 / 10 * 3.6 < 150
    assert 200 / 20 * 3.6 == 36  # accepted-anchor expectation, not executed correction


@pytest.mark.parametrize(
    "mutation", ["transfer", "missing", "extra", "duplicate", "malformed", "nan"]
)
def test_writer_rejects_bad_driver_day_ledgers(tmp_path, mutation):
    rows = build([("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1), ("C", 20, 3200, 0, 1)])
    result = calculate(rows, ZONE)
    totals = dict(result.totals)
    segments = list(result.segments)
    key = ("SYN-T01", "2026-11-04")
    if mutation == "transfer":
        totals = {key: 100, ("SYN-T01", "2026-11-09"): 100}
    elif mutation == "missing":
        totals = {}
    elif mutation == "extra":
        totals[("SYN-T01", "2026-11-09")] = 0
    elif mutation == "duplicate":
        segments.append(segments[0])
    elif mutation == "malformed":
        segments[0] = {**segments[0], "report_date": "2026-11-09"}
    else:
        totals[key] = float("nan")
    with pytest.raises(ValueError):
        write_baseline(
            tmp_path / "out",
            rows,
            [],
            [],
            replace(result, totals=totals, segments=tuple(segments)),
            Path(__file__),
        )
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("east,expected", [(3000, 100), (0, 0)])
def test_writer_valid_and_explicit_zero(tmp_path, east, expected):
    rows = build([("A", 0, east, 0, 1), ("B", 10, east + 100, 0, 1)])
    run, _ = write_baseline(tmp_path / "out", rows, [], [], calculate(rows, ZONE), Path(__file__))
    assert run["total_m"] == pytest.approx(expected, abs=0.01)


def test_ranking_ignores_sub_tolerance_noise():
    for noise in [-0.00002, 0.00002]:
        zone = dict(defect="zone", absolute_m=300, driver_days=6)
        order = dict(defect="order", absolute_m=300 + noise, driver_days=3)
        assert sorted([order, zone], key=discovery.ranking_key) == [zone, order]


def test_writer_rejects_transfer_between_existing_dates(tmp_path):
    rows = build([("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1), ("C", 5 * 86400, 3200, 0, 1)])
    result = calculate(rows, ZONE)
    assert list(result.totals.values()) == pytest.approx([100, 100], abs=0.01)
    totals = dict(result.totals)
    totals[("SYN-T01", "2026-11-04")] = sum(totals.values())
    totals[("SYN-T01", "2026-11-09")] = 0
    with pytest.raises(ValueError, match="does not reconcile"):
        write_baseline(
            tmp_path / "out", rows, [], [], replace(result, totals=totals), Path(__file__)
        )
