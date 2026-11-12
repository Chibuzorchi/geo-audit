"""Deliberately wrong baseline: file order, endpoint zone inclusion, UTC dates."""

from collections import defaultdict
from dataclasses import dataclass

from shapely.geometry import Point

from geo_audit.geo import planar_length, project, validate_geometry
from geo_audit.models import ParsedRow


@dataclass(frozen=True)
class LegacyResult:
    totals: dict[tuple[str, str], float]
    segments: tuple[dict, ...]


def calculate(rows: tuple[ParsedRow, ...], zone) -> LegacyResult:
    validate_geometry(zone, "zone")
    previous = {}
    totals = defaultdict(float)
    ledger = []
    for row in rows:
        if row.ping is None:
            continue
        ping = row.ping
        xy = project(ping.lon, ping.lat)
        day = ping.timestamp.date().isoformat()
        totals[(ping.driver_id, day)] += 0
        if ping.driver_id in previous:
            prior, a = previous[ping.driver_id]
            old = prior.ping
            length = planar_length(a, xy)
            inside = bool(zone.covers(Point(xy)))
            included = length if inside else 0.0
            ledger.append(
                dict(
                    driver_id=ping.driver_id,
                    from_id=old.ping_id,
                    to_id=ping.ping_id,
                    from_row=prior.source_row,
                    to_row=row.source_row,
                    from_time=old.timestamp.isoformat(),
                    to_time=ping.timestamp.isoformat(),
                    from_lon=old.lon,
                    from_lat=old.lat,
                    to_lon=ping.lon,
                    to_lat=ping.lat,
                    length_m=length,
                    endpoint_inside=inside,
                    report_date=day,
                    date_basis="UTC endpoint",
                    included_m=included,
                )
            )
            totals[(ping.driver_id, day)] += included
        previous[ping.driver_id] = (row, xy)
    return LegacyResult(dict(sorted(totals.items())), tuple(ledger))
