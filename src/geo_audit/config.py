"""Domain constants; no environment or filesystem access."""

import math

ROAD_LIMIT_M = 100.0  # Required: strictly greater is noise.
SPEED_LIMIT_KMH = 150.0
LONGITUDE_BOUNDS = (126.8, 127.3)  # Supported synthetic area, an explicit assumption.
LATITUDE_BOUNDS = (37.3, 37.7)


def validate_coordinate(lon: float, lat: float) -> None:
    if not (math.isfinite(lon) and math.isfinite(lat)):
        raise ValueError("coordinates must be finite")
    if not (
        LONGITUDE_BOUNDS[0] <= lon <= LONGITUDE_BOUNDS[1]
        and LATITUDE_BOUNDS[0] <= lat <= LATITUDE_BOUNDS[1]
    ):
        raise ValueError("coordinates outside supported geographic envelope")


def nonnegative(value: float) -> float:
    if not math.isfinite(value) or value < 0:
        raise ValueError("value must be finite and nonnegative")
    return value
