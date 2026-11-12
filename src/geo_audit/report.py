"""Canonical baseline evidence serialization, without expected-result access."""

import hashlib
import json
from collections import Counter, defaultdict
from math import isfinite
from pathlib import Path

COORDINATE_KEYS = {"from_lon", "from_lat", "to_lon", "to_lat"}


def _rounded(value, key=None):
    """Output rounding only: coordinates 10 dp, every other float 6 dp."""
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError("nonfinite evidence value")
        return round(value, 10 if key in COORDINATE_KEYS else 6)
    if isinstance(value, dict):
        return {k: _rounded(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_rounded(v, key) for v in value]
    return value


def summarize(findings, decisions):
    counts = Counter((f["kind"], f["rule"]) for f in [*findings, *decisions])
    return [dict(kind=k, rule=r, count=n) for (k, r), n in sorted(counts.items())]


def write_baseline(output: Path, rows, findings, decisions, legacy, input_path: Path):
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    reconcile(rows, legacy)
    output.mkdir(parents=True, exist_ok=True)
    totals_sum = sum(legacy.totals.values())
    payloads = {
        "findings.json": findings,
        "decision_conflicts.json": decisions,
        "summary.json": summarize(findings, decisions),
        "segments_legacy.json": [dict(segment=i, **s) for i, s in enumerate(legacy.segments)],
        "legacy_totals.json": [
            dict(driver_id=d, report_date=day, date_basis="UTC", legacy_m=m)
            for (d, day), m in legacy.totals.items()
        ],
        "quarantine.json": [
            dict(row=r.source_row, raw=dict(r.raw), reasons=r.reasons, assignable=r.assignable)
            for r in rows
            if r.ping is None
        ],
        "run.json": dict(
            input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
            input_rows=len(rows),
            parsed_rows=sum(r.ping is not None for r in rows),
            quarantined_rows=sum(r.ping is None for r in rows),
            segments=len(legacy.segments),
            total_m=totals_sum,
            calculator="legacy",
            synthetic=all(r.ping.is_synthetic for r in rows if r.ping),
        ),
    }
    for filename, payload in payloads.items():
        (output / filename).write_text(
            json.dumps(_rounded(payload), sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    return payloads["run.json"], payloads["summary.json"]


def reconcile(rows, legacy):
    """Validate source edges and every UTC baseline key, including explicit zeros.

    This is the legacy report contract; the full cross-calculator date grid belongs
    to the comparison phase. No rounding is applied before reconciliation.
    """
    usable = {r.source_row: r for r in rows if r.ping}
    keys = {(r.driver_id, r.timestamp.date().isoformat()) for r in usable.values()}
    sums = defaultdict(float)
    expected_edges = set()
    previous = {}
    for r in rows:
        if r.ping:
            if r.driver_id in previous:
                expected_edges.add((previous[r.driver_id], r.source_row))
            previous[r.driver_id] = r.source_row
    seen = set()
    try:
        for s in legacy.segments:
            edge = (s["from_row"], s["to_row"])
            if edge in seen or edge not in expected_edges:
                raise ValueError("duplicate or unexpected ledger edge")
            seen.add(edge)
            a, b = (usable[i] for i in edge)
            if any(
                (
                    s["driver_id"] != b.driver_id,
                    s["from_id"] != a.ping.ping_id,
                    s["to_id"] != b.ping.ping_id,
                    s["from_time"] != a.timestamp.isoformat(),
                    s["to_time"] != b.timestamp.isoformat(),
                    s["report_date"] != b.timestamp.date().isoformat(),
                )
            ):
                raise ValueError("malformed ledger source or date")
            length, included = s["length_m"], s["included_m"]
            if not all(isfinite(v) and v >= 0 for v in (length, included)):
                raise ValueError("nonfinite or negative ledger distance")
            if included != (length if s["endpoint_inside"] else 0):
                raise ValueError("malformed legacy inclusion")
            sums[(s["driver_id"], s["report_date"])] += included
        if seen != expected_edges or set(legacy.totals) != keys:
            raise ValueError("missing or extra ledger edges or driver/day keys")
        for key, value in legacy.totals.items():
            if not isfinite(value) or value < 0 or abs(value - sums[key]) > 1e-6:
                raise ValueError(f"legacy ledger does not reconcile for {key}")
    except (KeyError, TypeError) as error:
        raise ValueError("malformed ledger record") from error


def reconcile_corrected(rows, result):
    """Reject malformed evidence without suppressing execution errors."""
    try:
        _reconcile_corrected(rows, result)
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError(f"malformed corrected evidence: {error}") from error


def _reconcile_corrected(rows, result):
    """Require one final state per row, accepted edges and all driver/day sums."""
    from geo_audit.geo import planar_length, project
    from geo_audit.timecut import day_intervals, report_day

    _rounded([result.decisions, result.segments, list(result.totals.values())])
    allowed = {
        "quarantined",
        "rejected_duplicate",
        "rejected_noise",
        "accepted",
        "accepted_warning",
    }
    by_row = {r.source_row: r for r in rows}
    decisions = {d["row"]: d for d in result.decisions}
    if len(decisions) != len(result.decisions) or set(decisions) != set(by_row):
        raise ValueError("corrected decisions do not reconcile with input rows")
    keys = set()
    accepted = defaultdict(list)
    for d in result.decisions:
        r = by_row[d["row"]]
        if d["state"] not in allowed or d["assignable"] != r.assignable:
            raise ValueError("invalid final state or assignability")
        if (
            d["driver_id"] != r.driver_id
            or d["ping_id"] != dict(r.raw).get("ping_id")
            or d["timestamp"] != (r.timestamp.isoformat() if r.timestamp else None)
            or d["reporting_date"] != (str(report_day(r.timestamp)) if r.assignable else None)
            or d["raw"] != dict(r.raw)
        ):
            raise ValueError("corrected decision source identity mismatch")
        if d["state"] in ("accepted", "accepted_warning") and r.ping is None:
            raise ValueError("accepted observation is invalid")
        if d["assignable"]:
            keys.add((d["driver_id"], d["reporting_date"]))
        if d["state"] in ("accepted", "accepted_warning"):
            accepted[d["driver_id"]].append(d)
    edges = {}
    for driver, points in accepted.items():
        ordered = sorted(points, key=lambda d: d["timestamp"])
        for a, b in zip(ordered, ordered[1:]):
            edges[(a["row"], b["row"])] = driver
    seen = set()
    sums = defaultdict(float)
    for s in result.segments:
        edge = (s["from_row"], s["to_row"])
        if edge in seen or edges.get(edge) != s["driver_id"]:
            raise ValueError("duplicate or unexpected corrected edge")
        seen.add(edge)
        a, b = by_row[edge[0]], by_row[edge[1]]
        for prefix, row in (("from", a), ("to", b)):
            if (
                s[prefix + "_id"] != row.ping.ping_id
                or s[prefix + "_time"] != row.timestamp.isoformat()
                or s[prefix + "_lon"] != row.ping.lon
                or s[prefix + "_lat"] != row.ping.lat
                or s["driver_id"] != row.driver_id
            ):
                raise ValueError("corrected segment source identity mismatch")
        if a.timestamp >= b.timestamp or s["date_basis"] != "UTC+9 interval":
            raise ValueError("invalid segment time order or date basis")
        if not isfinite(s["included_m"]) or s["included_m"] < 0:
            raise ValueError("invalid included distance")
        previous = -1.0
        for lo, hi in s["zone_intervals"]:
            if not (isfinite(lo) and isfinite(hi) and 0 <= lo < hi <= 1 and lo >= previous):
                raise ValueError("invalid zone-intersection fractions")
            previous = hi
        distance = planar_length(project(a.ping.lon, a.ping.lat), project(b.ping.lon, b.ping.lat))
        if abs(distance - s["length_m"]) > 1e-6:
            raise ValueError("segment length disagrees with source coordinates")
        partitions = {str(piece.day): piece for piece in day_intervals(a.timestamp, b.timestamp)}
        if [v["report_date"] for v in s["allocations"]] != list(partitions):
            raise ValueError("allocation dates disagree with segment interval")
        if not isfinite(s["length_m"]) or s["length_m"] < 0:
            raise ValueError("invalid corrected length")
        allocated = 0
        dates = set()
        for allocation in s["allocations"]:
            key = (s["driver_id"], allocation["report_date"])
            value = allocation["included_m"]
            if key in dates or not isfinite(value) or value < 0:
                raise ValueError("invalid corrected allocation")
            piece = partitions[allocation["report_date"]]
            fraction = sum(
                max(0.0, min(hi, piece.end) - max(lo, piece.start))
                for lo, hi in s["zone_intervals"]
            )
            if abs(value - s["length_m"] * fraction) > 1e-6:
                raise ValueError("allocation amount disagrees with recorded spatial/time fractions")
            dates.add(key)
            keys.add(key)
            sums[key] += value
            allocated += value
        spatial_m = s["length_m"] * sum(hi - lo for lo, hi in s["zone_intervals"])
        if abs(allocated - s["included_m"]) > 1e-6 or abs(allocated - spatial_m) > 1e-6:
            raise ValueError("corrected segment allocation does not reconcile")
    if seen != set(edges) or set(result.totals) != keys:
        raise ValueError("missing corrected segments or driver/day keys")
    for key, value in result.totals.items():
        if not isfinite(value) or value < 0 or abs(value - sums[key]) > 1e-6:
            raise ValueError("corrected driver/day totals do not reconcile")


def write_comparison(output, rows, legacy, corrected, input_path):
    """Write literal date-label comparison, not a financial settlement calculation."""
    import csv
    from datetime import date

    from geo_audit.timecut import report_day

    _rounded([legacy.segments, list(legacy.totals.values())])
    reconcile(rows, legacy)
    reconcile_corrected(rows, corrected)
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    keys = set(legacy.totals) | set(corrected.totals)
    days = [report_day(r.timestamp).toordinal() for r in rows if r.timestamp]
    drivers = {r.driver_id for r in rows if r.driver_id}
    if days:
        keys.update(
            (driver, str(date.fromordinal(day)))
            for driver in drivers
            for day in range(min(days), max(days) + 1)
        )
    comparisons = []
    for key in sorted(keys):
        old, new = legacy.totals.get(key, 0.0), corrected.totals.get(key, 0.0)
        comparisons.append(
            dict(
                driver_id=key[0],
                reporting_date=key[1],
                legacy_m=f"{old:.3f}",
                corrected_m=f"{new:.3f}",
                difference_m=f"{new - old:.3f}",
                legacy_present=key in legacy.totals,
                corrected_present=key in corrected.totals,
                legacy_date_basis="UTC endpoint",
                corrected_date_basis="UTC+9 interval",
            )
        )
    output.mkdir(parents=True, exist_ok=True)

    def csv_file(name, fields, records):
        with (output / name).open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(records)

    csv_file(
        "driver_day.csv",
        [
            "driver_id",
            "reporting_date",
            "legacy_m",
            "corrected_m",
            "difference_m",
            "legacy_present",
            "corrected_present",
            "legacy_date_basis",
            "corrected_date_basis",
        ],
        comparisons,
    )
    csv_file(
        "ping_decisions.csv",
        [
            "row",
            "driver_id",
            "ping_id",
            "timestamp",
            "reporting_date",
            "state",
            "reasons",
            "assignable",
            "duplicate_winner",
            "road_distance_m",
            "speed_kmh",
            "anchor_id",
            "anchor_row",
            "raw",
        ],
        [
            {
                k: json.dumps(v, sort_keys=True, allow_nan=False)
                if isinstance(v, (list, dict))
                else v
                for k, v in _rounded(d).items()
                if k not in ("gap_s", "lateness_s")
            }
            for d in corrected.decisions
        ],
    )
    states = Counter(d["state"] for d in corrected.decisions)
    assigned = Counter(
        (d["driver_id"], d["reporting_date"], d["state"])
        for d in corrected.decisions
        if d["assignable"]
    )
    unassigned = Counter(d["state"] for d in corrected.decisions if not d["assignable"])
    differences = [corrected.totals.get(k, 0) - legacy.totals.get(k, 0) for k in keys]
    summary = dict(
        status=corrected.status,
        input_rows=len(rows),
        states=dict(states),
        assigned_states=[
            dict(driver_id=d, reporting_date=day, state=s, count=n)
            for (d, day, s), n in sorted(assigned.items())
        ],
        unassignable_states=dict(unassigned),
        driver_day_rows=len(comparisons),
        legacy_m=sum(legacy.totals.values()),
        corrected_m=sum(corrected.totals.values()),
        net_change_m=sum(differences),
        absolute_date_label_difference_m=sum(map(abs, differences)),
        positive_difference_m=sum(max(v, 0) for v in differences),
        negative_difference_m=sum(min(v, 0) for v in differences),
        input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
        interpretation="Date-label discrepancy analysis, not normalized financial settlement. "
        "Differences combine time, zone, ordering, duplicate and noise policies.",
    )
    payloads = {
        "summary.json": summary,
        "ping_decisions.json": corrected.decisions,
        "segments_legacy.json": [dict(segment=i, **s) for i, s in enumerate(legacy.segments)],
        "segments_corrected.json": [dict(segment=i, **s) for i, s in enumerate(corrected.segments)],
        "corrected_totals.json": [
            dict(driver_id=d, reporting_date=day, corrected_m=m)
            for (d, day), m in corrected.totals.items()
        ],
    }
    for name, payload in payloads.items():
        (output / name).write_text(
            json.dumps(_rounded(payload), sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
    return summary
