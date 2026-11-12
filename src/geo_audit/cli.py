"""Phase 2 input generation and blind baseline inspection."""

import argparse
import json
from pathlib import Path

from geo_audit import __version__
from geo_audit.calc_legacy import calculate
from geo_audit.checker import audit_legacy, inspect
from geo_audit.geo import project_geojson
from geo_audit.io import read_csv
from geo_audit.report import write_baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="geo-audit", description="GeoAudit baseline discovery")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", nargs="?", choices=["generate", "check", "compare", "demo"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--roads", type=Path)
    parser.add_argument("--zone", type=Path)
    parser.add_argument("--gate", action="store_true")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    if args.command in ("compare", "demo"):
        parser.error(f"{args.command} is unavailable in Phase 2")
    if not args.output:
        parser.error("--output is required (empty directory)")
    try:
        if args.command == "generate":
            from geo_audit_synthetic.generator import generate

            print(json.dumps(generate(args.output), sort_keys=True))
            return 0
        if not all((args.input, args.roads, args.zone)):
            parser.error("check requires --input, --roads and --zone")
        with args.input.open(newline="") as stream:
            rows = read_csv(stream)
        if not any(r.ping for r in rows):
            parser.error("NO_USABLE_DATA")
        roads = project_geojson(json.loads(args.roads.read_text()), "roads")
        zone = project_geojson(json.loads(args.zone.read_text()), "zone")
        findings = inspect(rows, roads, zone)
        baseline = calculate(rows, zone)
        decisions = audit_legacy(rows, roads, zone, baseline)
        run, summary = write_baseline(args.output, rows, findings, decisions, baseline, args.input)
        print(json.dumps(dict(run=run, findings=summary), sort_keys=True, indent=2))
        return 1 if args.gate and (findings or decisions) else 0
    except (ValueError, OSError) as error:
        parser.error(str(error))
