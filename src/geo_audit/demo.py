"""End-to-end demonstration from a project checkout. Success means every gate passed.

Each step runs the real command in a subprocess with the active interpreter, writes
into a fresh output directory, and is then checked. Regenerated artifacts must be
identical at their documented serialization precision to the committed reference files, and those must still match their
recorded hashes. Reference data and results are read, never written.
"""

import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from geo_audit.report import _rounded

REFERENCE_DATA = Path("data/synthetic")
REFERENCE_PHASE2 = Path("results/phase2")
REFERENCE_PHASE3 = Path("results/phase3")
PHASE2_FREEZE = Path("results/phase2_freeze.json")
PHASE3_MANIFEST = Path("results/phase3_validation_manifest.json")
REQUIRED = (
    Path("pyproject.toml"),
    Path("requirements.lock"),
    Path("scripts/discover_baseline.py"),
    Path("scripts/verify_r5_fixture.py"),
    Path("scripts/verify_phase3.py"),
    Path("scripts/verify_red_green.py"),
    Path("tests/expectations/analytic.json"),
    Path("tests/expectations/r5_midnight.json"),
    Path("tests/regression/manifest.json"),
    PHASE2_FREEZE,
    PHASE3_MANIFEST,
)
INPUT_ROWS = 3327  # Frozen synthetic dataset size (data/synthetic/manifest.json).


class DemoFailure(RuntimeError):
    """A verification gate failed (exit 1)."""


class PrerequisiteFailure(DemoFailure):
    """The demo cannot start: wrong interpreter, missing files or reused output (exit 2)."""


def require(condition, message):
    if not condition:
        raise DemoFailure(message)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same_files(fresh, reference, names=None, *, raw_json=()):
    """Byte comparison except explicitly named, historically unrounded JSON reports."""
    names = sorted(names or (p.name for p in Path(fresh).iterdir() if p.is_file()))
    require(names, f"no artifacts produced in {fresh}")
    for name in names:
        new, old = Path(fresh) / name, Path(reference) / name
        require(new.is_file() and new.stat().st_size > 0, f"missing or empty artifact: {new}")
        require(old.is_file() and old.stat().st_size > 0, f"missing reference artifact: {old}")
        if name in raw_json:
            equal = _rounded(json.loads(new.read_text())) == _rounded(json.loads(old.read_text()))
        else:
            equal = new.read_bytes() == old.read_bytes()
        require(equal, f"regenerated artifact differs: {new}")
    return names


def _pre(condition, message):
    if not condition:
        raise PrerequisiteFailure(message)


def check_prerequisites(root, output):
    _pre(sys.version_info[:2] == (3, 12), f"Python 3.12 required, found {sys.version.split()[0]}")
    for path in REQUIRED:
        _pre((root / path).is_file(), f"missing project file: {path} (run from a checkout)")
    pins = dict(
        line.split("==")
        for line in (root / "requirements.lock").read_text().split()
        if "==" in line and not line.startswith("#")
    )
    from importlib.metadata import version

    for package in ("pyproj", "shapely"):
        _pre(version(package) == pins.get(package), f"{package} differs from requirements.lock")
    _pre(not output.exists(), f"output must not exist yet: {output}")


def check_frozen_references(root):
    """Reference files read by the demo must still match their recorded hashes."""
    frozen = json.loads((root / PHASE2_FREEZE).read_text())["files"]
    # Immutable calculation evidence only: data, Phase 2 results (current and the archived
    # pre-remediation run) and Phase 3 numeric outputs. Source and append-only logs evolve
    # and are verified against their commits by scripts/verify_frozen_history.py instead.
    guarded = {p: h for p, h in frozen.items() if p.startswith(("data/", "results/"))}
    manifest = json.loads((root / PHASE3_MANIFEST).read_text())
    guarded.update(manifest["unchanged_numeric_evidence"])
    for path, digest in sorted(guarded.items()):
        require(sha256(root / path) == digest, f"frozen reference changed: {path}")
    return len(guarded)


def check_reconciliation(compare_dir):
    summary = json.loads((compare_dir / "summary.json").read_text())
    states = summary["states"]
    require(summary["input_rows"] == INPUT_ROWS, "input row count changed")
    require(sum(states.values()) == INPUT_ROWS, f"row states do not reconcile: {states}")
    totals = json.loads((compare_dir / "corrected_totals.json").read_text())
    ledger = json.loads((compare_dir / "segments_corrected.json").read_text())
    by_key = {}
    for segment in ledger:
        for piece in segment["allocations"]:
            key = (segment["driver_id"], piece["report_date"])
            by_key[key] = by_key.get(key, 0.0) + piece["included_m"]
    keys = {(row["driver_id"], row["reporting_date"]) for row in totals}
    require(by_key and set(by_key) <= keys, "ledger dates outside corrected totals")
    for row in totals:
        key = (row["driver_id"], row["reporting_date"])
        require(
            abs(by_key.get(key, 0.0) - row["corrected_m"]) <= 1e-3,
            f"corrected ledger does not reconcile: {key}",
        )
    with (compare_dir / "driver_day.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    require(len(rows) == summary["driver_day_rows"] > 0, "driver/day table row count mismatch")
    return dict(states=states, driver_day_rows=len(rows))


def run_demo(output, root=None):
    root = Path(root or Path.cwd()).resolve()
    output = Path(output)
    output = output if output.is_absolute() else root / output
    check_prerequisites(root, output)
    output.mkdir(parents=True)
    log = []

    def step(name, *arguments):
        command = [sys.executable, *arguments]
        process = subprocess.run(command, cwd=root, capture_output=True, text=True)
        (output / f"{len(log):02d}_{name}.log").write_text(process.stdout + process.stderr)
        log.append(dict(step=name, exit=process.returncode))
        require(process.returncode == 0, f"step {name} exited {process.returncode}")
        print(f"  [ok] {name}", flush=True)
        return process.stdout

    data, check, compare, red_green = (
        output / n for n in ("data", "check", "compare", "red_green")
    )
    references = check_frozen_references(root)
    print(f"  [ok] {references} frozen reference hashes", flush=True)
    step("generate", "-m", "geo_audit", "generate", "--output", str(data))
    same_files(data, root / REFERENCE_DATA)
    inputs = ["--roads", str(data / "roads.geojson"), "--zone", str(data / "zone.geojson")]
    csv_path = str(data / "SYNTHETIC_gps_pings.csv")
    step("check", "-m", "geo_audit", "check", "--input", csv_path, *inputs, "--output", str(check))
    step(
        "discover_baseline",
        "scripts/discover_baseline.py",
        "--data",
        str(data),
        "--results",
        str(check),
        "--expectations",
        "tests/expectations/analytic.json",
    )
    step("r5_fixture", "scripts/verify_r5_fixture.py", "--output", str(check / "r5_only.json"))
    same_files(check, root / REFERENCE_PHASE2, raw_json=("r5_only.json",))
    step(
        "compare",
        "-m",
        "geo_audit",
        "compare",
        "--input",
        csv_path,
        *inputs,
        "--output",
        str(compare),
    )
    step("verify_numbers", "scripts/verify_phase3.py", "--results", str(compare))
    same_files(
        compare,
        root / REFERENCE_PHASE3,
        names=[p.name for p in compare.iterdir() if p.is_file()],
        raw_json=("numerical_verification.json",),
    )
    same_files(compare / "r5_only", root / REFERENCE_PHASE3 / "r5_only")
    reconciliation = check_reconciliation(compare)
    print(f"  [ok] {INPUT_ROWS} rows reconcile: {reconciliation['states']}", flush=True)
    verdict = step("verify_red_green", "scripts/verify_red_green.py", "--output", str(red_green))
    red_green_summary = json.loads((red_green / "summary.json").read_text())
    require(red_green_summary["status"] == "PASS", "red/green summary is not PASS")
    summary = dict(
        status="PASS",
        steps=log,
        frozen_reference_hashes=references,
        reproduction_policy="byte-identical except two supplemental raw-float JSON reports",
        serialization_precision_reports=[
            "results/phase2/r5_only.json",
            "results/phase3/numerical_verification.json",
        ],
        reconciliation=reconciliation,
        red_green=dict(
            cases=red_green_summary["cases"],
            legacy_red=red_green_summary["legacy_red"],
            legacy_controls=red_green_summary["legacy_controls"],
        ),
    )
    (output / "demo_summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
    print("  " + verdict.strip())
    return summary


def main(output):
    print(f"GeoAudit demo (SYNTHETIC DATA) -> {output}")
    try:
        summary = run_demo(output)
    except DemoFailure as error:
        print(f"DEMO FAILED: {error}", file=sys.stderr)
        return 2 if isinstance(error, PrerequisiteFailure) else 1
    print(
        "DEMO PASS: data, baseline and corrected results verified at documented serialization precision; "
        f"{summary['red_green']['legacy_red']} legacy reds and "
        f"{summary['red_green']['cases']} corrected greens verified."
    )
    print(f"Artifacts: {output}/{{data,check,compare,red_green}}, {output}/demo_summary.json")
    return 0
