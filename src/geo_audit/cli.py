"""Phase 1 entry point: later commands fail explicitly rather than simulate results."""

import argparse

from geo_audit import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="geo-audit", description="GeoAudit Phase 1 primitives")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("command", nargs="?", choices=["generate", "check", "compare", "demo"])
    args = parser.parse_args(argv)
    if args.command:
        parser.error(f"{args.command} is unavailable in Phase 1")
    parser.print_help()
    return 0
