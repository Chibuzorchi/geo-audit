"""Enumerated synthetic scenarios; historical pre-measurement freeze is unverified."""

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pyproj import Transformer

SCENARIOS = (
    "S1",
    "S2a",
    "S2b",
    "S3",
    "S3b",
    "S4",
    "S5a",
    "S5b",
    "S5c",
    "S6a",
    "S6b",
    "S6c",
    "S7",
    "S8",
    "S9a",
    "S9b",
    "S10",
    "S11",
    "S12",
    "S13",
    "S14",
)
REPEATS = 3
VERSION = "analytic-v1"
FIELDS = ("ping_id", "driver_id", "ts_utc", "lat", "lon", "received_at_utc", "is_synthetic")


def scenario_points(name):
    """Return (index, E, N, suffix, receipt delay, labels); explicit local metre fixtures."""
    if name not in SCENARIOS:
        raise ValueError("unknown scenario")
    points = [(k, 1000 + 100 * k, 0, f"P{k:03}", 1, []) for k in range(81)]
    if name in ("S2b", "S3", "S3b", "S4"):
        points = [(k, 3000 + 100 * k, 0, f"P{k:03}", 1, []) for k in range(3)]
    if name == "S2a":
        points = [
            p
            for original in points
            for p in (
                [
                    original,
                    (original[0], original[1], 0, f"D{original[0]:03}", 2, ["EXACT_DUPLICATE"]),
                ]
                if 20 <= original[0] <= 29
                else [original]
            )
        ]
    if name == "S2b":
        points.append((1, 3100, 0, "D001", 21, ["EXACT_DUPLICATE", "LATE"]))
    if name in ("S3", "S3b"):
        points.insert(
            2,
            (
                1,
                3100,
                60 if name == "S3" else 150,
                "D001",
                2 if name == "S3" else 0,
                ["CONFLICT_DUPLICATE"] + (["OFF_ROAD"] if name == "S3b" else []),
            ),
        )
    if name == "S4":
        points = [points[0], points[2], (1, 3100, 0, "P001", 21, ["LATE", "OUT_OF_ORDER"])]
    if name.startswith("S5"):
        north = {"S5a": 150, "S5b": 99.5, "S5c": 100.5}[name]
        points[40] = (
            40,
            5000,
            north,
            "P040",
            1,
            ["OFF_ROAD" if north > 100 else "NEAR_ROAD_LIMIT"],
        )
    if name.startswith("S6"):
        east = {"S6a": 5315.28, "S6b": 5318.06, "S6c": 6000}[name]
        points[40] = (40, east, 0, "P040", 1, ["SPEED" if name != "S6a" else "NEAR_SPEED_LIMIT"])
    if name == "S9a":
        points = points[40:]
    if name == "S9b":
        points = points[:41]
    if name == "S10":
        points = [p for p in points if not 20 <= p[0] <= 59]
        points = [(*p[:5], ["GAP"] if p[0] == 60 else p[5]) for p in points]
    if name == "S11":
        points = [
            (k, 5000, 5 if k % 2 == 0 else -5, f"P{k:03}", 1, ["DRIFT_CONDITION"])
            for k in range(61)
        ]
    if name == "S13":
        points = [
            (k, e, 0, f"P{k:03}", 1, ["ANCHOR_LIMITATION"])
            for k, e in enumerate([9000, 3000, 3100])
        ]
    if name == "S14":
        points = [(k, 100 * k, 0, f"P{k:03}", 1, []) for k in range(2)]
    return points


def scenario_rows(name, copy=0):
    transformer = Transformer.from_crs(32652, 4326, always_xy=True)
    start = datetime(2026, 11, 4, 3, tzinfo=UTC) + timedelta(days=copy)
    if name == "S7":
        start = start.replace(hour=14, minute=53, second=20)
    if name == "S8":
        start = start.replace(hour=14, minute=58, second=13)
    driver = f"SYN-{name}-{copy:02}"
    rows = []
    labels = []
    for k, e, n, suffix, delay, tags in scenario_points(name):
        lon, lat = transformer.transform(320000 + e, 4150000 + n)
        stamp = start + timedelta(seconds=10 * k)
        row = dict(
            zip(
                FIELDS,
                [
                    f"{driver}-{suffix}",
                    driver,
                    stamp.isoformat(),
                    f"{lat:.10f}",
                    f"{lon:.10f}",
                    (stamp + timedelta(seconds=delay)).isoformat(),
                    "true",
                ],
                strict=True,
            )
        )
        rows.append(row)
        for tag in tags:
            labels.append({"ping_id": row["ping_id"], "condition": tag})
    if name == "S12":
        for i, (field, value) in enumerate(
            [
                ("lat", ""),
                ("ts_utc", "invalid"),
                ("ts_utc", "2026-11-04T03:00:00"),
                ("driver_id", ""),
            ]
        ):
            row = {**rows[0], "ping_id": f"{driver}-Q{i}", field: value}
            rows.append(row)
            labels.append({"ping_id": row["ping_id"], "condition": "QUARANTINE"})
    return rows, labels


def generate(output: Path):
    """Write inputs and labels only. Refuse nonempty destinations; no answer computation."""
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    labels = []
    instances = []
    for copy in range(REPEATS):
        for name in SCENARIOS:
            batch, tags = scenario_rows(name, copy)
            instances.append(
                dict(
                    scenario=name,
                    copy=copy,
                    driver=f"SYN-{name}-{copy:02}",
                    first_row=len(rows) + 1,
                    row_count=len(batch),
                )
            )
            rows.extend(batch)
            labels.extend(tags)
    if len(rows) - 4 * REPEATS < 2000:
        raise ValueError("insufficient structured observations")
    with (output / "SYNTHETIC_gps_pings.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    transform = Transformer.from_crs(32652, 4326, always_xy=True)

    def position(e, n):
        return list(transform.transform(320000 + e, 4150000 + n))

    roads = {"type": "LineString", "coordinates": [position(0, 0), position(10000, 0)]}
    zone = {
        "type": "Polygon",
        "coordinates": [
            [
                position(e, n)
                for e, n in [(2050, -500), (7950, -500), (7950, 500), (2050, 500), (2050, -500)]
            ]
        ],
    }
    for filename, value in [
        ("roads.geojson", roads),
        ("zone.geojson", zone),
        ("fault_labels.json", labels),
        ("instances.json", instances),
    ]:
        (output / filename).write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    manifest = {
        "synthetic": True,
        "version": VERSION,
        "seed": 0,
        "repeats": REPEATS,
        "rows": len(rows),
        "structured_rows": len(rows) - 4 * REPEATS,
        "scenarios": list(SCENARIOS),
        "hashes": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())
        },
    }
    (output / "manifest.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    return manifest
