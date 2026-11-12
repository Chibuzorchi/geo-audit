"""Blind diagnostics, not a corrected calculator or a billing-impact oracle.

Four kinds of output are kept apart:
- ``provisional_anomaly``: raw-pair measurement, never an acceptance decision.
- ``condition``: an observed data fact (duplicate, lateness, gap, zone or day crossing).
- ``rule_violation``: an observation that breaks a declared input rule (R1, quarantine).
- ``decision_conflict``: one legacy segment decision that contradicts a declared rule,
  with the segment's own measurements. These are never aggregated into corrected totals.

Measured billing discrepancies are produced only by post-run comparison against
independent expectations (scripts/discover_baseline.py), never here.
"""

from collections import defaultdict

from shapely.geometry import Point

from geo_audit.geo import planar_length, project, road_distance, zone_intervals
from geo_audit.rules import excessive_speed, off_road, speed_kmh
from geo_audit.timecut import day_intervals, report_day


def _finding(kind, rule, records, **measurements):
    return dict(
        kind=kind,
        rule=rule,
        rows=[r.source_row for r in records],
        ids=[dict(r.raw).get("ping_id") for r in records],
        driver=records[-1].driver_id,
        timestamps=[r.timestamp.isoformat() if r.timestamp else None for r in records],
        measurements=measurements,
    )


def inspect(rows, roads, zone):
    """Observation-level conditions and input rule violations."""
    findings = []
    drivers = defaultdict(list)
    groups = defaultdict(list)

    def emit(kind, rule, records, **measurements):
        findings.append(_finding(kind, rule, records, **measurements))

    for row in rows:
        if row.ping is None:
            emit(
                "rule_violation",
                "INPUT",
                [row],
                reasons=list(row.reasons),
                assignable=row.assignable,
            )
            continue
        p = row.ping
        xy = project(p.lon, p.lat)
        distance = road_distance(xy, roads)
        if off_road(distance):
            emit("rule_violation", "R1", [row], road_distance_m=distance)
        late = (p.received_at - p.timestamp).total_seconds()
        if late > 10:
            emit("condition", "R4_LATE", [row], lateness_s=late)
        if drivers[p.driver_id] and p.timestamp < drivers[p.driver_id][-1][0].timestamp:
            emit("condition", "R4_ORDER", [drivers[p.driver_id][-1][0], row])
        drivers[p.driver_id].append((row, xy))
        groups[(p.driver_id, p.timestamp)].append(row)
    for records in groups.values():
        if len(records) > 1:
            emit(
                "condition",
                "R3",
                [*records],
                conflict=len({(r.ping.lon, r.ping.lat) for r in records}) > 1,
                note="duplicate condition; billing effect not inferred",
            )
    for entries in drivers.values():
        ordered = sorted(
            entries,
            key=lambda item: (item[0].timestamp, item[0].ping.received_at, item[0].ping.ping_id),
        )
        for (a, xy), (b, end) in zip(ordered, ordered[1:]):
            elapsed = (b.timestamp - a.timestamp).total_seconds()
            if elapsed <= 0:
                continue
            length = planar_length(xy, end)
            speed = speed_kmh(length, elapsed)
            if excessive_speed(speed):
                emit(
                    "provisional_anomaly",
                    "RAW_PAIR_SPEED_ANOMALY",
                    [a, b],
                    speed_kmh=speed,
                    note="adjacent chronological raw pair; not last-accepted classification",
                )
            if elapsed > 60:
                emit("condition", "GAP", [a, b], elapsed_s=elapsed, chord_m=length)
            inside_a = zone.covers(Point(xy))
            inside_b = zone.covers(Point(end))
            if inside_a != inside_b:
                emit(
                    "condition",
                    "R6",
                    [a, b],
                    transition="exit" if inside_a else "entry",
                    intervals=zone_intervals(xy, end, zone),
                )
            if len(day_intervals(a.timestamp, b.timestamp)) > 1:
                emit(
                    "condition",
                    "R5_CROSS",
                    [a, b],
                    start_day=str(report_day(a.timestamp)),
                    end_day=str(report_day(b.timestamp)),
                )
    return findings


def audit_legacy(rows, roads, zone, legacy):
    """Compare each legacy segment decision with one declared rule at a time.

    Every conflict cites its own segment only. No totals, no dedupe selection,
    no anchor tracking: this explains decisions, it does not recompute billing.
    """
    by_row = {r.source_row: r for r in rows}
    findings = []
    for index, s in enumerate(legacy.segments):
        a, b = by_row[s["from_row"]], by_row[s["to_row"]]
        start = project(a.ping.lon, a.ping.lat)
        end = project(b.ping.lon, b.ping.lat)
        common = dict(segment=index, length_m=s["length_m"], included_m=s["included_m"])

        def emit(rule, kind="decision_conflict", **measurements):
            findings.append(_finding(kind, rule, [a, b], **common, **measurements))

        elapsed = (b.timestamp - a.timestamp).total_seconds()
        if elapsed <= 0:
            emit(
                "R3_R4_FILE_ORDER",
                elapsed_s=elapsed,
                decision="segment joins rows in file order, not device-time order",
            )
        elif s["included_m"] > 0 and excessive_speed(speed_kmh(s["length_m"], elapsed)):
            emit(
                "LEGACY_RAW_PAIR_SPEED_ANOMALY",
                kind="provisional_anomaly",
                speed_kmh=speed_kmh(s["length_m"], elapsed),
                decision="billed raw pair exceeds threshold; neither endpoint is classified",
                note="road and duplicate selection precede last-accepted speed decisions in Phase 3",
            )
        if s["included_m"] > 0:
            road = {
                "from": road_distance(start, roads),
                "to": road_distance(end, roads),
            }
            if any(off_road(d) for d in road.values()):
                emit(
                    "R1_OFF_ROAD",
                    road_distance_m=road,
                    decision="segment uses an off-road observation",
                )
        in_zone = sum(hi - lo for lo, hi in zone_intervals(start, end, zone)) * s["length_m"]
        if abs(in_zone - s["included_m"]) > 1e-6:
            emit(
                "R6_ENDPOINT",
                in_zone_length_m=in_zone,
                endpoint_inside=s["endpoint_inside"],
                decision="whole segment included or excluded by end point only",
            )
        if elapsed > 0 and s["included_m"] > 0:
            kst = sorted({str(piece.day) for piece in day_intervals(a.timestamp, b.timestamp)})
            if kst != [s["report_date"]]:
                emit(
                    "R5_UTC_DATE",
                    legacy_date=s["report_date"],
                    utc9_days=kst,
                    decision="distance labelled with end point's UTC date",
                )
    return findings
