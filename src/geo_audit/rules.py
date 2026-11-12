"""Threshold predicates and batch duplicate selection; no movement calculation."""

import math

from geo_audit.config import ROAD_LIMIT_M, SPEED_LIMIT_KMH, nonnegative


def off_road(distance_m: float) -> bool:
    return nonnegative(distance_m) > ROAD_LIMIT_M


def excessive_speed(speed_kmh: float) -> bool:
    return nonnegative(speed_kmh) > SPEED_LIMIT_KMH


def speed_kmh(distance_m: float, elapsed_seconds: float) -> float:
    nonnegative(distance_m)
    if not math.isfinite(elapsed_seconds) or elapsed_seconds <= 0:
        raise ValueError("elapsed time must be finite and positive")
    return nonnegative(distance_m / elapsed_seconds * 3.6)


def select_observations(rows):
    """Batch ID quarantine followed by deterministic driver/instant deduplication.

    Return per-row selection facts. Physical identical copies are interchangeable;
    source row only orders evidence, never distinguishes different payloads.
    """
    from collections import defaultdict

    from geo_audit.io import normalized_payload

    ids = defaultdict(list)
    groups = defaultdict(list)
    decisions = {}
    for row in rows:
        ping_id = dict(row.raw).get("ping_id")
        if ping_id:
            ids[ping_id].append(row)
    conflicts = {
        ping_id
        for ping_id, copies in ids.items()
        if len({normalized_payload(r) for r in copies}) > 1
    }
    for row in rows:
        reasons = list(row.reasons)
        if dict(row.raw).get("ping_id") in conflicts:
            reasons.append("ID_CONFLICT")
        decisions[row.source_row] = dict(
            state="quarantined" if reasons else None,
            reasons=reasons,
            duplicate_winner=None,
        )
        if not reasons:
            groups[(row.driver_id, row.timestamp)].append(row)
    for copies in groups.values():
        winner = min(copies, key=lambda r: (r.ping.received_at, r.ping.ping_id))
        conflict = len({(r.ping.lon, r.ping.lat) for r in copies}) > 1
        for row in copies:
            decision = decisions[row.source_row]
            if len(copies) > 1:
                decision["duplicate_winner"] = winner.ping.ping_id
            if row is not winner:
                decision.update(state="rejected_duplicate", reasons=["DUPLICATE"])
            elif conflict:
                decision["reasons"].append("DUPLICATE_CONFLICT")
    return decisions
