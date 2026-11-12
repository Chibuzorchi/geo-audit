"""Pure threshold predicates only; no selection, anchors or billing pipeline."""

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
