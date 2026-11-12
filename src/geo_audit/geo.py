"""Projected metre primitives. Planar functions accept already-projected XY only."""

import math
from collections.abc import Mapping

from pyproj import Transformer
from shapely import get_coordinate_dimension, get_coordinates, transform
from shapely.geometry import LineString, MultiLineString, Point, Polygon, shape
from shapely.geometry.base import BaseGeometry

from geo_audit.config import validate_coordinate

XY = tuple[float, float]
Interval = tuple[float, float]


def project(lon: float, lat: float) -> XY:
    validate_coordinate(lon, lat)
    return Transformer.from_crs(4326, 32652, always_xy=True).transform(lon, lat)


def unproject(easting: float, northing: float) -> XY:
    _point((easting, northing))
    lon, lat = Transformer.from_crs(32652, 4326, always_xy=True).transform(easting, northing)
    validate_coordinate(lon, lat)
    return lon, lat


def _point(xy: XY) -> Point:
    if len(xy) != 2 or not all(math.isfinite(v) for v in xy):
        raise ValueError("expected finite planar XY")
    return Point(xy)


def validate_geometry(geometry: BaseGeometry, kind: str) -> None:
    if kind not in {"roads", "zone"}:
        raise ValueError("unknown geometry role")
    expected = (LineString, MultiLineString) if kind == "roads" else (Polygon,)
    if not isinstance(geometry, expected) or geometry.is_empty:
        raise ValueError("unsupported or empty geometry")
    if get_coordinate_dimension(geometry) != 2 or not all(
        math.isfinite(v) for xy in get_coordinates(geometry) for v in xy
    ):
        raise ValueError("geometry must have finite 2D coordinates")
    if not geometry.is_valid:
        raise ValueError("invalid geometry")
    if kind == "zone" and geometry.area <= 0:
        raise ValueError("zone must have positive area")
    if kind == "roads":
        lines = geometry.geoms if isinstance(geometry, MultiLineString) else [geometry]
        if any(len(set(line.coords)) < 2 for line in lines):
            raise ValueError("road needs two distinct points")


def _validate_rings(coordinates: object) -> None:
    """Check raw GeoJSON before Shapely can close or coerce malformed rings."""
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        raise ValueError("polygon requires an exterior ring")
    for ring in coordinates:
        if not isinstance(ring, (list, tuple)) or len(ring) < 4:
            raise ValueError("polygon ring requires at least four positions")
        for position in ring:
            if not isinstance(position, (list, tuple)) or len(position) != 2:
                raise ValueError("polygon positions must be finite 2D coordinates")
            if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in position):
                raise ValueError("polygon coordinates must be numbers")
            validate_coordinate(*position)
        if tuple(ring[0]) != tuple(ring[-1]):
            raise ValueError("polygon ring must be explicitly closed")


def project_geojson(document: Mapping, kind: str) -> BaseGeometry:
    """Validate a GeoJSON geometry object and project all vertices, including holes."""
    if document.get("type") == "Polygon":
        _validate_rings(document.get("coordinates"))
    try:
        geometry = shape(document)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("malformed GeoJSON geometry") from error
    validate_geometry(geometry, kind)
    for lon, lat in get_coordinates(geometry):
        validate_coordinate(lon, lat)
    transformer = Transformer.from_crs(4326, 32652, always_xy=True)
    projected = transform(geometry, transformer.transform, interleaved=False)
    validate_geometry(projected, kind)
    return projected


def planar_length(start: XY, end: XY) -> float:
    return _point(start).distance(_point(end))


def road_distance(point: XY, roads: BaseGeometry) -> float:
    validate_geometry(roads, "roads")
    return _point(point).distance(roads)


def zone_intervals(start: XY, end: XY, zone: Polygon) -> tuple[Interval, ...]:
    """Return merged τ intervals; boundary lines count, isolated points do not."""
    validate_geometry(zone, "zone")
    length = planar_length(start, end)
    if length == 0:
        return ()
    segment = LineString([start, end])
    pieces = []

    def visit(part: BaseGeometry) -> None:
        if isinstance(part, LineString) and part.length > 0:
            bounds = sorted(
                segment.project(Point(p)) / length for p in (part.coords[0], part.coords[-1])
            )
            pieces.append((max(0.0, bounds[0]), min(1.0, bounds[1])))
        elif hasattr(part, "geoms"):
            for child in part.geoms:
                visit(child)

    visit(segment.intersection(zone))
    merged: list[Interval] = []
    for lo, hi in sorted(pieces):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else:
            merged.append((lo, hi))
    return tuple(merged)
