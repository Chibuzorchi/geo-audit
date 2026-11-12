import ast
import builtins
import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely.geometry import box

from geo_audit.calc_legacy import calculate
from geo_audit.checker import audit_legacy, inspect
from geo_audit.geo import project_geojson
from geo_audit.io import parse_rows, read_csv
from geo_audit.report import write_baseline
from geo_audit_synthetic.generator import REPEATS, SCENARIOS, generate, scenario_rows

EXPECTATIONS = json.loads((Path(__file__).parents[1] / "expectations/analytic.json").read_text())


@pytest.mark.parametrize("name", SCENARIOS)
def test_analytic_legacy(name):
    raw, _ = scenario_rows(name)
    rows = parse_rows(raw)
    zone = box(322050, 4149500, 327950, 4150500)
    result = calculate(rows, zone)
    old, _ = EXPECTATIONS[name]
    for offset, want in enumerate(old):
        day = str(date(2026, 11, 4) + timedelta(days=offset))
        assert result.totals.get((f"SYN-{name}-00", day), 0) == pytest.approx(want, abs=0.01)
    assert sum(result.totals.values()) == pytest.approx(
        sum(s["included_m"] for s in result.segments), abs=1e-6
    )
    assert result == calculate(rows, zone)


def test_fixture_contracts():
    # Independent checks of serialized input, not generator's local-point helper.
    transformer = Transformer.from_crs(4326, 32652, always_xy=True)
    for name in SCENARIOS:
        raw, _ = scenario_rows(name)
        for row in raw:
            if "-Q" in row["ping_id"]:
                continue
            k = int(row["ping_id"][-3:])
            e, n = transformer.transform(float(row["lon"]), float(row["lat"]))
            east = 1000 + 100 * k
            north = 0
            if name in ("S2b", "S3", "S3b", "S4"):
                east = 3000 + 100 * k
            if name == "S11":
                east = 5000
                north = 5 if k % 2 == 0 else -5
            if name == "S13":
                east = [9000, 3000, 3100][k]
            if name == "S14":
                east = 100 * k
            if name in ("S5a", "S5b", "S5c") and k == 40:
                north = {"S5a": 150, "S5b": 99.5, "S5c": 100.5}[name]
            if name in ("S6a", "S6b", "S6c") and k == 40:
                east = {"S6a": 5315.28, "S6b": 5318.06, "S6c": 6000}[name]
            if name in ("S3", "S3b") and row["ping_id"].endswith("D001"):
                north = 60 if name == "S3" else 150
            assert (e - 320000, n - 4150000) == pytest.approx((east, north), abs=0.00002)
        if name == "S10":
            assert [int(r["ping_id"][-3:]) for r in raw] == list(range(20)) + list(range(60, 81))
    for name, ids in [
        ("S2b", ["P000", "P001", "P002", "D001"]),
        ("S3", ["P000", "P001", "D001", "P002"]),
        ("S4", ["P000", "P002", "P001"]),
    ]:
        assert [r["ping_id"][-4:] for r in scenario_rows(name)[0]] == ids
    assert scenario_rows("S7")[0][40]["ts_utc"] == "2026-11-04T15:00:00+00:00"
    assert scenario_rows("S8")[0][10]["ts_utc"] == "2026-11-04T14:59:53+00:00"


def test_bulk_determinism_and_reconciliation(tmp_path):
    first, second = tmp_path / "one", tmp_path / "two"
    manifest = generate(first)
    assert manifest == generate(second)
    assert all(p.read_bytes() == (second / p.name).read_bytes() for p in first.iterdir())
    with (first / "SYNTHETIC_gps_pings.csv").open() as f:
        rows = read_csv(f)
    assert len(rows) == manifest["rows"]
    assert sum(r.ping is not None for r in rows) == manifest["structured_rows"] >= 2000
    assert len({dict(r.raw)["ping_id"] for r in rows}) == len(rows)
    assert len({r.driver_id for r in rows if r.driver_id}) == len(SCENARIOS) * REPEATS
    assert all(dict(r.raw)["is_synthetic"] == "true" for r in rows)
    bad = [r for r in rows if r.ping is None]
    assert len(bad) == 12 and sum(r.assignable for r in bad) == 3
    zone = project_geojson(json.loads((first / "zone.geojson").read_text()), "zone")
    roads = project_geojson(json.loads((first / "roads.geojson").read_text()), "roads")
    result = calculate(rows, zone)
    assert all(
        s["from_id"].rsplit("-", 1)[0] == s["to_id"].rsplit("-", 1)[0] for s in result.segments
    )
    counts = Counter(r.driver_id for r in rows if r.ping)
    assert len(result.segments) == sum(n - 1 for n in counts.values())
    sums = defaultdict(float)
    for s in result.segments:
        assert rows[s["from_row"] - 1].ping.ping_id == s["from_id"]
        assert rows[s["to_row"] - 1].ping.ping_id == s["to_id"]
        sums[(s["driver_id"], s["report_date"])] += s["included_m"]
    for key, total in result.totals.items():
        assert total == pytest.approx(sums[key], abs=1e-6)
    findings = inspect(rows, roads, zone)
    assert {
        "R1",
        "RAW_PAIR_SPEED_ANOMALY",
        "R3",
        "R4_LATE",
        "R4_ORDER",
        "R6",
        "R5_CROSS",
        "GAP",
        "INPUT",
    } <= {f["rule"] for f in findings}
    decisions = audit_legacy(rows, roads, zone, result)
    for dest in [tmp_path / "a", tmp_path / "b"]:
        write_baseline(dest, rows, findings, decisions, result, first / "SYNTHETIC_gps_pings.csv")
    assert all(
        p.read_bytes() == (tmp_path / "b" / p.name).read_bytes() for p in (tmp_path / "a").iterdir()
    )
    assert all(p.stat().st_size > 0 for p in (tmp_path / "a").iterdir())


def test_checker_blind_and_specific(tmp_path, monkeypatch):
    data = tmp_path / "data"
    generate(data)
    with (data / "SYNTHETIC_gps_pings.csv").open() as f:
        rows = read_csv(f)
    roads = project_geojson(json.loads((data / "roads.geojson").read_text()), "roads")
    zone = project_geojson(json.loads((data / "zone.geojson").read_text()), "zone")

    def forbidden(*args, **kwargs):
        raise AssertionError("checker must not read any file")

    with monkeypatch.context() as m:
        m.setattr(builtins, "open", forbidden)
        m.setattr(Path, "open", forbidden)
        findings = inspect(rows, roads, zone)
        decisions = audit_legacy(rows, roads, zone, calculate(rows, zone))
    assert decisions
    assert any(
        f["rule"] == "R1"
        and f["ids"] == ["SYN-S5a-00-P040"]
        and abs(f["measurements"]["road_distance_m"] - 150) < 0.001
        for f in findings
    )
    assert any(
        f["rule"] == "RAW_PAIR_SPEED_ANOMALY"
        and f["ids"] == ["SYN-S6c-00-P039", "SYN-S6c-00-P040"]
        and abs(f["measurements"]["speed_kmh"] - 396) < 0.001
        for f in findings
    )
    assert any(
        f["rule"] == "R3" and f["measurements"]["conflict"] and f["driver"] == "SYN-S3-00"
        for f in findings
    )
    allowed = {"condition", "rule_violation", "decision_conflict", "provisional_anomaly"}
    assert {f["kind"] for f in findings + decisions} <= allowed
    # No expected value, corrected total or driver/day aggregate leaves the checker.
    text = json.dumps(findings + decisions)
    assert "expected" not in text and "corrected" not in text and "total" not in text


def test_generator_has_no_billing_import():
    import geo_audit_synthetic.generator as generator

    tree = ast.parse(Path(generator.__file__).read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert not (node.module or "").startswith("geo_audit.")
        if isinstance(node, ast.Import):
            assert all(not n.name.startswith("geo_audit.") for n in node.names)


def test_cli_and_discovery(tmp_path):
    data = tmp_path / "data"
    out = tmp_path / "out"
    command = [sys.executable, "-m", "geo_audit"]
    subprocess.run(command + ["generate", "--output", str(data)], check=True, capture_output=True)
    subprocess.run(
        command
        + [
            "check",
            "--input",
            str(data / "SYNTHETIC_gps_pings.csv"),
            "--roads",
            str(data / "roads.geojson"),
            "--zone",
            str(data / "zone.geojson"),
            "--output",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [
            sys.executable,
            "scripts/discover_baseline.py",
            "--data",
            str(data),
            "--results",
            str(out),
            "--expectations",
            "tests/expectations/analytic.json",
        ],
        check=True,
        capture_output=True,
    )
    report = json.loads((out / "discovery.json").read_text())
    ranking = report["ranking"]
    assert len(ranking) >= 3
    keys = [(-round(d["absolute_m"] / 0.01), -d["driver_days"], d["defect"]) for d in ranking]
    assert keys == sorted(keys)
    assert [d["rank"] for d in ranking] == list(range(1, len(ranking) + 1))
    assert all(not d["unexplained"] for d in ranking)
    discrepancies = [m for m in report["measurements"] if m["classification"] == "discrepancy"]
    assert sum(d["driver_days"] for d in ranking) == len(discrepancies)
    assert sum(d["absolute_m"] for d in ranking) == pytest.approx(
        sum(abs(m["difference_m"]) for m in discrepancies), abs=1e-5
    )
    controls = {m["scenario"] for m in report["measurements"] if m["classification"] == "control"}
    assert {"S1", "S2a", "S5b", "S6a", "S10", "S12", "S14"} <= controls
    assert (out / "findings.md").read_text().startswith("# Phase 2 executed baseline")
    assert (
        subprocess.run(
            command + ["generate", "--output", str(data)], capture_output=True
        ).returncode
        == 2
    )
