"""Execute the supplemental legacy fixture; never calculate corrected billing."""

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, box

from geo_audit.calc_legacy import calculate
from geo_audit.checker import audit_legacy
from geo_audit.io import parse_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(Path("tests/expectations/r5_midnight.json").read_text())
    transform = Transformer.from_crs(32652, 4326, always_xy=True)
    raw = []
    for i, ((e, n), stamp) in enumerate(
        zip(fixture["local_positions_m"], fixture["timestamps"], strict=True)
    ):
        lon, lat = transform.transform(320000 + e, 4150000 + n)
        raw.append(
            dict(
                ping_id=f"SYN-R5-ONLY-P{i}",
                driver_id="SYN-R5-ONLY",
                ts_utc=stamp,
                received_at_utc=(datetime.fromisoformat(stamp) + timedelta(seconds=1)).isoformat(),
                lon=f"{lon:.10f}",
                lat=f"{lat:.10f}",
                is_synthetic="true",
            )
        )
    rows = parse_rows(raw)
    zone = box(322050, 4149500, 327950, 4150500)
    legacy = calculate(rows, zone)
    actual = [legacy.totals.get(("SYN-R5-ONLY", d), 0) for d in fixture["dates"]]
    if any(abs(a - b) > 0.01 for a, b in zip(actual, fixture["legacy_m"], strict=True)):
        raise SystemExit("R5-only legacy numeric gate failed")
    conflicts = audit_legacy(rows, LineString([(320000, 4150000), (330000, 4150000)]), zone, legacy)
    if [c["rule"] for c in conflicts] != ["R5_UTC_DATE"]:
        raise SystemExit("R5-only isolation gate failed")
    payload = dict(
        fixture=fixture,
        raw_rows=raw,
        actual_legacy_m=actual,
        segments=legacy.segments,
        conflicts=conflicts,
        required_basis="Independent 100 * 5/10 per day; no corrected calculator executed",
    )
    with args.output.open("x") as stream:
        stream.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
