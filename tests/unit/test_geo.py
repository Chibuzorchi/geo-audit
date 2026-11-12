import math

import pytest
from shapely.geometry import LineString, MultiLineString, Polygon, box

from geo_audit.geo import (
    planar_length,
    project,
    project_geojson,
    road_distance,
    unproject,
    validate_geometry,
    zone_intervals,
)


def test_triangle():
    assert planar_length((0, 0), (3, 4)) == 5


@pytest.mark.parametrize("lon,lat", [(127, 37.5), (126.8, 37.3), (127.3, 37.7)])
def test_projection_roundtrip(lon, lat):
    xy = project(lon, lat)
    recovered = unproject(*xy)
    assert recovered == pytest.approx((lon, lat), abs=1e-10)
    assert planar_length(xy, project(*recovered)) < 0.001
    rounded = tuple(float(f"{v:.10f}") for v in recovered)
    assert planar_length(xy, project(*rounded)) <= 0.00002


def test_known_projection_origin():
    # WGS84 transverse Mercator series derivation: docs/phase1_evidence.md,
    # remediation projection-reference section. These are rounded metre values.
    easting, northing = project(127, 37.5)
    assert easting == pytest.approx(323210.469, abs=0.001)
    assert northing == pytest.approx(4152220.145, abs=0.001)


@pytest.mark.parametrize(
    "roads",
    [
        LineString([(0, 0), (1000, 0)]),
        MultiLineString([[(0, 0), (1000, 0)], [(0, -200), (1000, -200)]]),
    ],
)
def test_road_distance(roads):
    assert road_distance((500, 100), roads) == 100
    assert road_distance((500, 100.5), roads) == 100.5
    assert road_distance((-3, 4), roads) == 5


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((2000, 0), (2100, 0), ((0.5, 1),)),
        ((7900, 0), (8000, 0), ((0, 0.5),)),
        ((2000, 0), (8000, 0), ((1 / 120, 119 / 120),)),
        ((3000, 0), (3000, 0), ()),
    ],
)
def test_zone_intervals(zone, a, b, expected):
    actual = zone_intervals(a, b, zone)
    assert len(actual) == len(expected)
    for pair, want in zip(actual, expected, strict=True):
        assert pair == pytest.approx(want, abs=1e-12)
    if a == (2000, 0) and b == (8000, 0):
        assert sum(hi - lo for lo, hi in actual) * 6000 == pytest.approx(5900, abs=1e-6)


def test_boundary():
    square = box(0, 0, 1, 1)
    assert zone_intervals((-1, 1), (1, -1), square) == ()
    intervals = zone_intervals((-1, 0), (2, 0), square)
    assert len(intervals) == 1
    assert intervals[0] == pytest.approx((1 / 3, 2 / 3), abs=1e-12)


def test_concave_and_hole():
    concave = Polygon([(10, -1), (30, -1), (30, 1), (60, 1), (60, -1), (90, -1), (90, 2), (10, 2)])
    assert zone_intervals((0, 0), (100, 0), concave) == ((0.1, 0.3), (0.6, 0.9))
    hole = Polygon([(0, 0), (10, 0), (10, 10), (0, 10)], holes=[[(4, 4), (6, 4), (6, 6), (4, 6)]])
    assert zone_intervals((0, 5), (10, 5), hole) == ((0, 0.4), (0.6, 1))
    assert zone_intervals((10, 5), (0, 5), hole) == ((0, 0.4), (0.6, 1))


@pytest.mark.parametrize(
    "geometry,kind",
    [
        (Polygon(), "zone"),
        (LineString(), "roads"),
        (box(0, 0, 1, 1), "roads"),
        (Polygon([(0, 0), (1, 1), (0, 1), (1, 0)]), "zone"),
        (LineString([(0, 0), (0, 0)]), "roads"),
        (LineString([(0, 0, 0), (1, 1, 1)]), "roads"),
    ],
)
def test_invalid_geometry(geometry, kind):
    with pytest.raises(ValueError):
        validate_geometry(geometry, kind)


@pytest.mark.parametrize(
    "document",
    [
        {"type": "Point", "coordinates": [127, 37.5]},
        {"type": "LineString", "coordinates": [[0, 0], [1, 1]]},
        {"type": "LineString", "coordinates": [[127, 37.5], [math.inf, 37.5]]},
        {"type": "LineString", "coordinates": []},
    ],
)
def test_bad_geojson(document):
    with pytest.raises(ValueError):
        project_geojson(document, "roads")


def test_geojson_projection():
    roads = project_geojson(
        {"type": "LineString", "coordinates": [[127, 37.5], [127.001, 37.5]]}, "roads"
    )
    assert roads.length == pytest.approx(88.416, abs=0.01)
    assert road_distance(project(127, 37.5), roads) < 1e-6


@pytest.mark.parametrize(
    "lon,lat", [(126.8, 37.3), (127.3, 37.3), (126.8, 37.7), (127.3, 37.7), (127, 37.5)]
)
def test_projection_against_ellipsoid(lon, lat):
    from pyproj import Geod

    geod = Geod(ellps="WGS84")
    for dx, dy in [(0.0001, 0), (0, 0.0001), (0.0001, 0.0001)]:
        # Step inward at upper envelope edges.
        other = (lon + (-dx if lon == 127.3 else dx), lat + (-dy if lat == 37.7 else dy))
        ground = geod.inv(lon, lat, *other)[2]
        projected = planar_length(project(lon, lat), project(*other))
        assert abs(projected / ground - 1) < 0.001  # 0.1%, intentionally conservative.


def test_geojson_polygon_hole():
    document = {
        "type": "Polygon",
        "coordinates": [
            [[127, 37.5], [127.01, 37.5], [127.01, 37.51], [127, 37.51], [127, 37.5]],
            [
                [127.004, 37.504],
                [127.006, 37.504],
                [127.006, 37.506],
                [127.004, 37.506],
                [127.004, 37.504],
            ],
        ],
    }
    zone = project_geojson(document, "zone")
    assert len(zone.interiors) == 1
    assert not zone.covers(__import__("shapely").Point(project(127.005, 37.505)))


@pytest.mark.parametrize("lon,lat", [(37.5, 127), (float("nan"), 37.5), (127, 90)])
def test_invalid_geographic_point(lon, lat):
    with pytest.raises(ValueError):
        project(lon, lat)


@pytest.mark.parametrize(
    "ring",
    [
        [[127, 37.5], [127.01, 37.5], [127, 37.51]],  # Exact audit example.
        [[127, 37.5], [127.01, 37.5], [127.01, 37.51], [127, 37.51]],
        [],
        None,
        "ring",
        [[127, 37.5]] * 3,
        [[127, 37.5], [127.01, 37.5, 0], [127, 37.51], [127, 37.5]],
        [[127, 37.5], [float("nan"), 37.5], [127, 37.51], [127, 37.5]],
        [[127, 37.5], [127.01, float("inf")], [127, 37.51], [127, 37.5]],
        [[127, 37.5], ["127.01", 37.5], [127, 37.51], [127, 37.5]],
    ],
)
@pytest.mark.parametrize("interior", [False, True])
def test_malformed_rings(ring, interior):
    exterior = [[127, 37.5], [127.02, 37.5], [127.02, 37.52], [127, 37.52], [127, 37.5]]
    rings = [exterior, ring] if interior else [ring]
    with pytest.raises(ValueError):
        project_geojson({"type": "Polygon", "coordinates": rings}, "zone")


@pytest.mark.parametrize(
    "wkt",
    [
        "LINESTRING M (0 0 NaN, 1 1 NaN)",
        "LINESTRING M (0 0 1, 1 1 2)",
        "LINESTRING Z (0 0 1, 1 1 2)",
        "LINESTRING ZM (0 0 1 2, 1 1 2 3)",
    ],
)
def test_unsupported_dimensions(wkt):
    from shapely import from_wkt

    with pytest.raises(ValueError, match="finite 2D"):
        validate_geometry(from_wkt(wkt), "roads")
    validate_geometry(LineString([(0, 0), (1, 1)]), "roads")


def test_serialized_inverse_projection():
    from geo_audit.io import format_number

    xy = (323456.789123, 4152345.678912)
    lonlat = unproject(*xy)
    rounded = tuple(float(format_number(v, 10)) for v in lonlat)
    assert rounded != lonlat  # Exercise actual serialization loss.
    assert 0 < planar_length(xy, project(*rounded)) <= 0.00002


def test_mixed_line_point_intersection():
    # Connected polygon: the left lobe crosses y=0; the right tip touches it.
    zone = Polygon([(0, -1), (2, -1), (2, 1), (3, 1), (4, 0), (5, 1), (5, 2), (0, 2)])
    segment = LineString([(-1, 0), (6, 0)])
    intersection = segment.intersection(zone)
    assert intersection.geom_type == "GeometryCollection"
    assert {part.geom_type for part in intersection.geoms} == {"LineString", "Point"}
    result = zone_intervals((-1, 0), (6, 0), zone)
    assert len(result) == 1
    assert result[0] == pytest.approx((1 / 7, 3 / 7), abs=1e-12)
    assert 7 * (result[0][1] - result[0][0]) == pytest.approx(2, abs=1e-6)
