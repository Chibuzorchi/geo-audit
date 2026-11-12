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
            json.dumps(_rounded(payload), sort_keys=True, indent=2) + "\n"
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
