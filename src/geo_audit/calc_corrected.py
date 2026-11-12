"""Corrected calculation over parsed records, independent of legacy and answer keys."""

from geo_audit.geo import planar_length, zone_intervals
from geo_audit.timecut import day_intervals


def allocate_segment(start, end, start_time, end_time, zone):
    """Intersect spatial fractions with fixed UTC+9 time fractions."""
    length = planar_length(start, end)
    spatial = zone_intervals(start, end, zone)
    allocations = []
    for piece in day_intervals(start_time, end_time):
        fraction = sum(max(0.0, min(hi, piece.end) - max(lo, piece.start)) for lo, hi in spatial)
        allocations.append(dict(report_date=str(piece.day), included_m=length * fraction))
    return length, spatial, allocations


def calculate(rows, roads, zone):
    """Apply selection, road filtering, accepted-anchor speed and clipped allocation."""
    from collections import defaultdict

    from geo_audit.geo import project, road_distance, validate_geometry
    from geo_audit.models import CorrectedResult
    from geo_audit.rules import excessive_speed, off_road, select_observations, speed_kmh
    from geo_audit.timecut import report_day

    validate_geometry(roads, "roads")
    validate_geometry(zone, "zone")
    if len({r.source_row for r in rows}) != len(rows):
        raise ValueError("source row references must be unique")
    selected = select_observations(rows)
    totals = defaultdict(float)
    decisions = {}
    segments = []
    for row in rows:
        decisions[row.source_row] = dict(
            row=row.source_row,
            raw=dict(row.raw),
            driver_id=row.driver_id,
            ping_id=dict(row.raw).get("ping_id"),
            timestamp=row.timestamp.isoformat() if row.timestamp else None,
            reporting_date=str(report_day(row.timestamp)) if row.assignable else None,
            assignable=row.assignable,
            **selected[row.source_row],
            road_distance_m=None,
            speed_kmh=None,
            anchor_id=None,
            anchor_row=None,
        )
        if row.assignable:
            totals[(row.driver_id, str(report_day(row.timestamp)))] += 0
    survivors = sorted(
        (r for r in rows if selected[r.source_row]["state"] is None),
        key=lambda r: (r.driver_id, r.timestamp),
    )
    anchors = {}
    for row in survivors:
        p = row.ping
        d = decisions[row.source_row]
        xy = project(p.lon, p.lat)
        d["road_distance_m"] = road_distance(xy, roads)
        if off_road(d["road_distance_m"]):
            d["state"] = "rejected_noise"
            d["reasons"].append("OFF_ROAD")
            continue
        prior = anchors.get(p.driver_id)
        if prior:
            a, start = prior
            elapsed = (p.timestamp - a.ping.timestamp).total_seconds()
            d.update(
                anchor_id=a.ping.ping_id,
                anchor_row=a.source_row,
                speed_kmh=speed_kmh(planar_length(start, xy), elapsed),
            )
            if excessive_speed(d["speed_kmh"]):
                d["state"] = "rejected_noise"
                d["reasons"].append("SPEED")
                continue
            length, spatial, allocations = allocate_segment(
                start, xy, a.timestamp, p.timestamp, zone
            )
            segments.append(
                dict(
                    driver_id=p.driver_id,
                    from_id=a.ping.ping_id,
                    to_id=p.ping_id,
                    from_row=a.source_row,
                    to_row=row.source_row,
                    from_time=a.timestamp.isoformat(),
                    to_time=p.timestamp.isoformat(),
                    from_lon=a.ping.lon,
                    from_lat=a.ping.lat,
                    to_lon=p.lon,
                    to_lat=p.lat,
                    length_m=length,
                    zone_intervals=spatial,
                    allocations=allocations,
                    included_m=sum(v["included_m"] for v in allocations),
                    date_basis="UTC+9 interval",
                )
            )
            for allocation in allocations:
                totals[(p.driver_id, allocation["report_date"])] += allocation["included_m"]
            if elapsed > 60:
                d["reasons"].append("GAP")
                d["gap_s"] = elapsed
        late = (p.received_at - p.timestamp).total_seconds()
        if late > 10:
            d["reasons"].append("LATE")
            d["lateness_s"] = late
        d["state"] = "accepted_warning" if d["reasons"] else "accepted"
        anchors[p.driver_id] = (row, xy)
    return CorrectedResult(
        dict(sorted(totals.items())),
        tuple(decisions[n] for n in sorted(decisions)),
        tuple(segments),
        "OK" if survivors else "NO_USABLE_DATA",
    )
