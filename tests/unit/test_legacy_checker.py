"""Phase 2 focused tests. Each test builds its own rows; expectations are literals."""

import ast
import json
import math
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import LineString, box

from geo_audit.calc_legacy import calculate
from geo_audit.checker import audit_legacy, inspect
from geo_audit.io import parse_rows
from geo_audit_synthetic.generator import SCENARIOS, scenario_rows

ORIGIN = (320000, 4150000)
ZONE = box(322050, 4149500, 327950, 4150500)
ROADS = LineString([(320000, 4150000), (330000, 4150000)])
T = datetime(2026, 11, 4, 3, tzinfo=UTC)
TO_GEO = Transformer.from_crs(32652, 4326, always_xy=True)
EXPECTATIONS = Path(__file__).parents[1] / "expectations/analytic.json"


def build(points, start=T, driver="SYN-T01"):
    """points: (ping_id, seconds after start, local E, local N, receipt delay s)."""
    rows = []
    for ping_id, seconds, east, north, delay in points:
        lon, lat = TO_GEO.transform(ORIGIN[0] + east, ORIGIN[1] + north)
        stamp = start + timedelta(seconds=seconds)
        rows.append(
            dict(
                ping_id=ping_id,
                driver_id=driver,
                ts_utc=stamp.isoformat(),
                lat=f"{lat:.10f}",
                lon=f"{lon:.10f}",
                received_at_utc=(stamp + timedelta(seconds=delay)).isoformat(),
                is_synthetic="true",
            )
        )
    return parse_rows(rows)


def total(result):
    return sum(result.totals.values())


# ---------------------------------------------------------------- legacy behaviour


def test_legacy_is_file_order_sensitive():
    chronological = build([("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1), ("C", 20, 3200, 0, 1)])
    shuffled = build([("A", 0, 3000, 0, 1), ("C", 20, 3200, 0, 1), ("B", 10, 3100, 0, 31)])
    assert total(calculate(chronological, ZONE)) == pytest.approx(200, abs=0.01)
    assert total(calculate(shuffled, ZONE)) == pytest.approx(300, abs=0.01)  # 200 + 100 back


def test_legacy_counts_duplicates_by_position():
    adjacent = build(
        [("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1), ("B2", 10, 3100, 0, 2), ("C", 20, 3200, 0, 1)]
    )
    appended = build(
        [
            ("A", 0, 3000, 0, 1),
            ("B", 10, 3100, 0, 1),
            ("C", 20, 3200, 0, 1),
            ("B2", 10, 3100, 0, 21),
        ]
    )
    # Exact duplicate next to its original adds a zero-length segment.
    adjacent_result = calculate(adjacent, ZONE)
    assert total(adjacent_result) == pytest.approx(200, abs=0.01)
    assert [s["length_m"] for s in adjacent_result.segments][1] == pytest.approx(0, abs=1e-5)
    # The same copy arriving late adds a 100 m backward segment.
    assert total(calculate(appended, ZONE)) == pytest.approx(300, abs=0.01)


def test_legacy_dates_by_endpoint_utc_date():
    # 14:59:55Z -> 15:00:05Z crosses UTC+9 midnight; UTC date stays Nov 4.
    rows = build(
        [("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1)],
        start=T.replace(hour=14, minute=59, second=55),
    )
    result = calculate(rows, ZONE)
    assert result.totals == {("SYN-T01", "2026-11-04"): pytest.approx(100, abs=0.01)}
    assert result.segments[0]["report_date"] == "2026-11-04"
    # 23:59:55Z -> 00:00:05Z: UTC date changes, so legacy uses Nov 5 (KST Nov 5 throughout).
    rows = build(
        [("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1)],
        start=T.replace(hour=23, minute=59, second=55),
    )
    assert calculate(rows, ZONE).segments[0]["report_date"] == "2026-11-05"


def test_legacy_endpoint_only_zone_inclusion():
    entry = calculate(build([("A", 0, 2000, 0, 1), ("B", 10, 2100, 0, 1)]), ZONE)
    exit_ = calculate(build([("A", 0, 7900, 0, 1), ("B", 10, 8000, 0, 1)]), ZONE)
    assert entry.segments[0]["endpoint_inside"] is True
    assert total(entry) == pytest.approx(100, abs=0.01)  # 50 m actually inside
    assert exit_.segments[0]["endpoint_inside"] is False
    assert total(exit_) == 0  # 50 m actually inside


def test_legacy_skips_quarantine_and_keeps_zero_keys():
    rows = list(build([("A", 0, 0, 0, 1), ("B", 10, 100, 0, 1)]))
    bad = parse_rows([{**dict(rows[0].raw), "ping_id": "Q", "lat": ""}])[0]
    result = calculate(tuple(rows + [bad]), ZONE)
    assert len(result.segments) == 1
    assert result.totals == {("SYN-T01", "2026-11-04"): 0.0}


def test_legacy_ledger_traceability_and_stability():
    rows = build([("A", 0, 2000, 0, 1), ("B", 10, 2100, 0, 1), ("C", 20, 2200, 0, 1)])
    result = calculate(rows, ZONE)
    assert result == calculate(rows, ZONE)
    for s in result.segments:
        assert rows[s["from_row"] - 1].ping.ping_id == s["from_id"]
        assert rows[s["to_row"] - 1].ping.ping_id == s["to_id"]
        assert s["date_basis"] == "UTC endpoint"
    assert sum(s["included_m"] for s in result.segments) == pytest.approx(total(result), abs=1e-9)


def test_legacy_drivers_are_independent():
    a = build([("A0", 0, 3000, 0, 1), ("A1", 10, 3100, 0, 1)], driver="SYN-A")
    b = build([("B0", 5, 9000, 0, 1), ("B1", 15, 9100, 0, 1)], driver="SYN-B")
    interleaved = parse_rows([dict(r.raw) for pair in zip(a, b) for r in pair])
    result = calculate(interleaved, ZONE)
    assert {s["driver_id"] for s in result.segments} == {"SYN-A", "SYN-B"}
    assert result.totals[("SYN-A", "2026-11-04")] == pytest.approx(100, abs=0.01)
    assert result.totals[("SYN-B", "2026-11-04")] == 0


# ---------------------------------------------------------------- checker


def rules(findings, kind=None):
    return {f["rule"] for f in findings if kind is None or f["kind"] == kind}


def test_checker_clean_trip_has_no_rule_findings():
    rows = build([("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1), ("C", 20, 3200, 0, 1)])
    assert inspect(rows, ROADS, ZONE) == []
    assert audit_legacy(rows, ROADS, ZONE, calculate(rows, ZONE)) == []


@pytest.mark.parametrize(
    ("points", "observed", "decision"),
    [
        # Off-road ping, 150 m north.
        (
            [("A", 0, 3000, 0, 1), ("B", 10, 3100, 150, 1), ("C", 20, 3200, 0, 1)],
            "R1",
            "R1_OFF_ROAD",
        ),
        # Speed spike: 1100 m in 10 s = 396 km/h.
        (
            [("A", 0, 3000, 0, 1), ("B", 10, 4100, 0, 1), ("C", 20, 3200, 0, 1)],
            "RAW_PAIR_SPEED_ANOMALY",
            "LEGACY_RAW_PAIR_SPEED_ANOMALY",
        ),
        # Late out-of-order ping.
        (
            [("A", 0, 3000, 0, 1), ("C", 20, 3200, 0, 1), ("B", 10, 3100, 0, 31)],
            "R4_ORDER",
            "R3_R4_FILE_ORDER",
        ),
        # Exit segment, endpoint outside.
        ([("A", 0, 7900, 0, 1), ("B", 10, 8000, 0, 1)], "R6", "R6_ENDPOINT"),
    ],
)
def test_checker_flags_rule_and_decision(points, observed, decision):
    rows = build(points)
    assert observed in rules(inspect(rows, ROADS, ZONE))
    assert decision in rules(audit_legacy(rows, ROADS, ZONE, calculate(rows, ZONE)))


def test_checker_duplicate_conflict_and_lateness_measurements():
    rows = build(
        [
            ("A", 0, 3000, 0, 1),
            ("B", 10, 3100, 0, 1),
            ("B2", 10, 3100, 60, 2),
            ("C", 20, 3200, 0, 21),
        ]
    )
    findings = inspect(rows, ROADS, ZONE)
    dup = [f for f in findings if f["rule"] == "R3"]
    assert len(dup) == 1 and dup[0]["ids"] == ["B", "B2"] and dup[0]["measurements"]["conflict"]
    late = [f for f in findings if f["rule"] == "R4_LATE"]
    assert late[0]["ids"] == ["C"] and late[0]["measurements"]["lateness_s"] == 21


def test_checker_exact_duplicate_is_condition_not_billing_claim():
    rows = build(
        [("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1), ("B2", 10, 3100, 0, 2), ("C", 20, 3200, 0, 1)]
    )
    dup = [f for f in inspect(rows, ROADS, ZONE) if f["rule"] == "R3"]
    assert dup[0]["kind"] == "condition" and dup[0]["measurements"]["conflict"] is False
    decisions = audit_legacy(rows, ROADS, ZONE, calculate(rows, ZONE))
    # The zero-length duplicate segment is flagged as a decision, with 0 m included.
    assert [d["measurements"]["included_m"] for d in decisions] == [pytest.approx(0, abs=1e-5)]


def test_checker_reports_utc9_day_conflict_with_days():
    rows = build(
        [("A", 0, 3000, 0, 1), ("B", 10, 3100, 0, 1)],
        start=T.replace(hour=14, minute=59, second=55),
    )
    findings = inspect(rows, ROADS, ZONE)
    cross = [f for f in findings if f["rule"] == "R5_CROSS"][0]["measurements"]
    assert (cross["start_day"], cross["end_day"]) == ("2026-11-04", "2026-11-05")
    conflict = audit_legacy(rows, ROADS, ZONE, calculate(rows, ZONE))[0]
    assert conflict["rule"] == "R5_UTC_DATE"
    assert conflict["measurements"]["utc9_days"] == ["2026-11-04", "2026-11-05"]
    assert conflict["measurements"]["legacy_date"] == "2026-11-04"


def test_checker_quarantine_reasons_visible():
    rows = parse_rows(
        [
            {
                **dict(build([("A", 0, 0, 0, 1)])[0].raw),
                "ping_id": "Q1",
                "ts_utc": "2026-11-04T03:00:00",
            }
        ]
    )
    finding = inspect(rows, ROADS, ZONE)[0]
    assert finding["rule"] == "INPUT" and finding["kind"] == "rule_violation"
    assert finding["measurements"]["assignable"] is False
    assert any("NAIVE_TIMESTAMP" in r for r in finding["measurements"]["reasons"])


def test_checker_source_has_no_answer_key_access():
    import geo_audit.checker as checker

    tree = ast.parse(Path(checker.__file__).read_text())
    imported = {
        n.module if isinstance(n, ast.ImportFrom) else a.name
        for n in ast.walk(tree)
        if isinstance(n, (ast.Import, ast.ImportFrom))
        for a in (n.names if isinstance(n, ast.Import) else [n])
    }
    assert imported <= {
        "collections",
        "shapely.geometry",
        "geo_audit.geo",
        "geo_audit.rules",
        "geo_audit.timecut",
    }
    calls = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and hasattr(n.func, "id")}
    assert not calls & {"open", "eval", "exec", "__import__"}
    for token in ("fault_labels", "analytic.json", "calc_corrected", "read_text", "Path"):
        assert token not in Path(checker.__file__).read_text()


# ---------------------------------------------------------------- generator


def test_generator_serialization_and_labels_are_separate():
    for name in SCENARIOS:
        raw, labels = scenario_rows(name)
        assert all(
            set(r)
            == {"ping_id", "driver_id", "ts_utc", "lat", "lon", "received_at_utc", "is_synthetic"}
            for r in raw
        )
        assert all("condition" not in r and "label" not in r for r in raw)
        ids = {r["ping_id"] for r in raw}
        assert {label["ping_id"] for label in labels} <= ids
        for r in raw:
            if "-Q" in r["ping_id"]:
                continue  # S12 quarantine rows are malformed on purpose.
            if r["ts_utc"] not in ("invalid", "2026-11-04T03:00:00"):
                assert r["ts_utc"].endswith("+00:00")
            assert len(r["lat"].split(".")[1]) == 10 and len(r["lon"].split(".")[1]) == 10


def test_post_run_labels_match_blind_checker():
    """Integration cross-check after the blind run; labels never reach the checker."""
    expected_rule = {
        "EXACT_DUPLICATE": "R3",
        "CONFLICT_DUPLICATE": "R3",
        "LATE": "R4_LATE",
        "OUT_OF_ORDER": "R4_ORDER",
        "OFF_ROAD": "R1",
        "SPEED": "RAW_PAIR_SPEED_ANOMALY",
        "GAP": "GAP",
        "QUARANTINE": "INPUT",
    }
    for name in SCENARIOS:
        raw, labels = scenario_rows(name)
        findings = inspect(parse_rows(raw), ROADS, ZONE)
        for label in labels:
            rule = expected_rule.get(label["condition"])
            hits = [f for f in findings if label["ping_id"] in f["ids"]]
            if rule:
                assert rule in {f["rule"] for f in hits}, (name, label)
            elif label["condition"] in ("NEAR_ROAD_LIMIT", "NEAR_SPEED_LIMIT"):
                assert not {"R1", "RAW_PAIR_SPEED_ANOMALY"} & {f["rule"] for f in hits}, (
                    name,
                    label,
                )


# ---------------------------------------------------------------- expectations


def test_expectation_literals_match_independent_arithmetic():
    """Recompute plan section 4 formulas with math only; no production helpers."""
    e = json.loads(EXPECTATIONS.read_text())
    s = math.sqrt
    checks = {
        "S2b": ([300], [200]),
        "S3": ([100 + 60 + s(100**2 + 60**2)], [200]),
        "S3b": ([100 + 150 + s(100**2 + 150**2)], [200]),
        "S4": ([200 + 100], [200]),
        "S5a": ([5700 + 2 * s(100**2 + 150**2)], [5900]),
        "S5b": ([5700 + 2 * s(100**2 + 99.5**2)], [5700 + 2 * s(100**2 + 99.5**2)]),
        "S5c": ([5700 + 2 * s(100**2 + 100.5**2)], [5900]),
        "S6a": ([5700 + 415.28 + 215.28] * 2, None),
        "S6b": ([5700 + 418.06 + 218.06], [5900]),
        "S6c": ([5700 + 1100 + 900], [5900]),
        "S7": ([5900, 0], [2950, 2950]),
        "S8": ([5900, 0], [20, 5880]),
        "S9a": ([2900], [2950]),
        "S9b": ([3000], [2950]),
        "S10": ([5900], [5900]),
    }
    for name, (legacy, required) in checks.items():
        if name == "S6a":
            legacy, required = legacy[:1], legacy[1:]
        assert e[name][0] == pytest.approx(legacy, abs=1e-6), name
        assert e[name][1] == pytest.approx(required, abs=1e-6), name
    # S6 speed boundaries: 418.06 m / 10 s > 150 km/h, 415.28 m / 10 s < 150 km/h.
    assert 415.28 * 0.36 < 150 < 418.06 * 0.36
    # S8: midnight 7 s into a 10 s, 100 m segment from E=2000 -> 2070; zone starts 2050.
    assert 2000 + 100 * 0.7 - 2050 == pytest.approx(20)
    # S10: 2900 -> 7000 chord crosses no boundary, so totals are unchanged.
    assert (2900 - 2050) + (7000 - 2900) + (7950 - 7000) == 5900
