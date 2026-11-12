"""Strict red/green verifier for GeoAudit's named billing regressions (plan section 7).

Runs the same named assertions twice, in fresh pytest subprocesses:
  GEO_AUDIT_TARGET=corrected  -> must exit 0, every case passes.
  GEO_AUDIT_TARGET=legacy     -> must exit exactly 1; each intended red fails at its own
                                 numeric assertion; every control passes.
Acceptance uses structured evidence written by tests/regression/conftest.py plus the
JUnit report, cross-checked against a manifest that is itself checked against the
independent literal expectation files. Exit codes alone are never accepted.
"""

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

MANIFEST = Path("tests/regression/manifest.json")
ANALYTIC = Path("tests/expectations/analytic.json")
R5_FIXTURE = Path("tests/expectations/r5_midnight.json")
R5_ROWS = Path("results/phase2/r5_only.json")
DATASET = Path("data/synthetic/SYNTHETIC_gps_pings.csv")
TEST_FILE = "tests/regression/test_billing.py"
PHASES = ("setup", "call", "teardown")
CASE_FIELDS = {
    "assertion_id",
    "driver",
    "fixture_sha256",
    "legacy",
    "legacy_status",
    "nodeid",
    "raw_dates",
    "required",
    "scenario",
    "tolerance_m",
}
CHARACTERIZATION = {"S11", "S13"}  # Never accepted as proof of a fixed business rule.


class VerificationError(ValueError):
    """A specific, named reason the evidence is not acceptable."""


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def load_json(path):
    def constant(value):
        raise VerificationError(f"nonfinite evidence: {value}")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        return json.loads(Path(path).read_text(), parse_constant=constant, object_pairs_hook=unique)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError(f"missing or malformed JSON evidence: {Path(path).name}") from error


def finite(value, context):
    require(
        type(value) in (int, float) and math.isfinite(value),
        f"nonfinite numerical outcome: {context}",
    )
    return value


def vector(actual, expected, tolerance, context):
    require(
        isinstance(actual, dict) and set(actual) == set(expected),
        f"missing or unexpected numerical outcome keys: {context}",
    )
    for day, value in actual.items():
        finite(value, context)
        require(abs(value - expected[day]) <= tolerance, f"incorrect numerical value: {context}")


def fixture_digest(rows):
    return hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def check_manifest(root):
    """Manifest must restate the independent literals; it cannot invent its own oracle."""
    cases = load_json(root / MANIFEST)
    require(isinstance(cases, list) and cases, "empty or malformed manifest")
    analytic = load_json(root / ANALYTIC)
    r5 = load_json(root / R5_FIXTURE)
    require(
        Counter(c.get("nodeid") for c in cases).most_common(1)[0][1] == 1,
        "duplicate manifest node IDs",
    )
    require(len({c.get("assertion_id") for c in cases}) == len(cases), "duplicate assertion IDs")
    with (root / DATASET).open(newline="") as stream:
        dataset = list(csv.DictReader(stream))
    for case in cases:
        require(set(case) >= CASE_FIELDS, f"malformed manifest case: {case.get('scenario')}")
        name = case["scenario"]
        require(name not in CHARACTERIZATION, f"characterization case in billing manifest: {name}")
        require(
            case["nodeid"] == f"{TEST_FILE}::test_billing[{name}]", f"unexpected node ID: {name}"
        )
        if name == "R5_ONLY":
            days = r5["dates"]
            legacy, required = r5["legacy_m"], r5["required_m"]
            rows = load_json(root / R5_ROWS)["raw_rows"]
        else:
            require(name in analytic, f"scenario without independent expectation: {name}")
            require(case["driver"] == f"SYN-{name}-00", f"unexpected driver: {name}")
            legacy, required = analytic[name]
            days = [str(date(2026, 11, 4) + timedelta(days=i)) for i in range(len(required))]
            first = case["first_row"] - 1
            rows = dataset[first : first + case["row_count"]]
            require(
                rows and all(r["ping_id"].startswith(case["driver"] + "-") for r in rows),
                f"fixture rows outside scenario namespace: {name}",
            )
        require(case["required"] == dict(zip(days, required, strict=True)), f"oracle drift: {name}")
        require(case["legacy"] == dict(zip(days, legacy, strict=True)), f"legacy drift: {name}")
        tolerance = finite(case["tolerance_m"], name)
        require(0 < tolerance <= 0.01, f"tolerance outside plan budget: {name}")
        differs = any(abs(legacy[i] - required[i]) > tolerance for i in range(len(days)))
        require(
            case["legacy_status"] == ("failed" if differs else "passed"),
            f"legacy red/control classification contradicts expectations: {name}",
        )
        require(fixture_digest(rows) == case["fixture_sha256"], f"invalid fixture hash: {name}")
    return cases


def check_junit(path, run_id, cases, target):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as error:
        raise VerificationError("missing or malformed JUnit") from error
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]
    require(len(suites) == 1, "unexpected JUnit suite count")
    suite = suites[0]
    tokens = [
        p.attrib.get("value") for p in suite.iter("property") if p.attrib.get("name") == "run_id"
    ]
    require(tokens == [run_id], "stale JUnit run identity")
    reds = sum(c["legacy_status"] == "failed" for c in cases) if target == "legacy" else 0
    totals = {k: int(suite.attrib.get(k, "-1")) for k in ("tests", "failures", "errors", "skipped")}
    require(
        totals == dict(tests=len(cases), failures=reds, errors=0, skipped=0),
        f"unexpected JUnit totals: {totals}",
    )
    entries = suite.findall("testcase")
    names = Counter((c.attrib.get("classname"), c.attrib.get("name")) for c in entries)
    wanted = Counter(("tests.regression.test_billing", c["nodeid"].split("::")[1]) for c in cases)
    require(names == wanted, "missing or duplicate JUnit tests")
    return {c.attrib["name"]: c for c in entries}


def validate_run(directory, target, run_id, returncode, cases, manifest_hash):
    """Validate one subprocess run; return per-case evidence or raise a named reason."""
    try:
        return _validate_run(directory, target, run_id, returncode, cases, manifest_hash)
    except (KeyError, TypeError, AttributeError) as error:
        raise VerificationError(f"malformed evidence: {type(error).__name__} {error}") from error


def _validate_run(directory, target, run_id, returncode, cases, manifest_hash):
    payload = load_json(directory / "evidence.json")
    ids = [c["nodeid"] for c in cases]
    require(payload.get("run_id") == run_id, "stale run identity")
    require(payload.get("target") == target, "wrong evidence target")
    require(payload.get("manifest_sha256") == manifest_hash, "manifest hash mismatch")
    expected_exit = 0 if target == "corrected" else 1
    require(
        returncode == payload.get("exitstatus") == expected_exit,
        f"unexpected pytest exit status: {returncode}",
    )
    require(Counter(payload["collected"]) == Counter(ids), "missing or duplicate collected tests")
    require(payload["deselected"] == [], "deselected required tests")
    events = payload["events"]
    for e in events:  # Name setup/teardown/skip/xfail problems before counting phases.
        require(not e["wasxfail"], f"xfail required test: {e['nodeid']}")
        if e["phase"] != "call":
            require(e["outcome"] == "passed", f"unexpected {e['phase']} outcome: {e['nodeid']}")
    require(
        Counter((e["nodeid"], e["phase"]) for e in events)
        == Counter((node, phase) for node in ids for phase in PHASES),
        "missing or duplicate execution phases",
    )
    records = payload["assertions"]
    require(
        Counter(r["nodeid"] for r in records) == Counter(ids),
        "missing or duplicate assertion results",
    )
    records = {r["nodeid"]: r for r in records}
    events = {(e["nodeid"], e["phase"]): e for e in events}
    junit = check_junit(directory / "junit.xml", run_id, cases, target)
    summaries = []
    for case in cases:
        node = case["nodeid"]
        status = "passed" if target == "corrected" else case["legacy_status"]
        for phase in PHASES:
            event = events[node, phase]
            require(not event["wasxfail"], f"xfail required test: {node}")
            want = status if phase == "call" else "passed"
            require(event["outcome"] == want, f"unexpected {phase} outcome: {node}")
            failure = "numeric_mismatch" if phase == "call" and status == "failed" else None
            require(event["failure"] == failure, f"wrong {phase} failure type: {node}")
            require(
                event["assertion_id"] == (case["assertion_id"] if failure else None),
                f"wrong failure assertion: {node}",
            )
        record = records[node]
        require(record["target"] == target, f"wrong record target: {node}")
        require(record["scenario"] == case["scenario"], f"wrong scenario: {node}")
        require(record["fixture_sha256"] == case["fixture_sha256"], f"invalid fixture hash: {node}")
        require(record["assertion_id"] == case["assertion_id"], f"wrong assertion ID: {node}")
        require(record["tolerance_m"] == case["tolerance_m"], f"changed tolerance: {node}")
        vector(record["expected"], case["required"], 0, f"{node} expected")
        vector(record["legacy_expected"], case["legacy"], 0, f"{node} legacy expectation")
        require(
            record["raw_dates"] == sorted(case["raw_dates"][target]),
            f"missing or unexpected raw driver/day keys: {node}",
        )
        measured = case["required"] if target == "corrected" else case["legacy"]
        vector(record["actual"], measured, case["tolerance_m"], f"{node} actual")
        matches = all(
            abs(record["actual"][d] - v) <= case["tolerance_m"] for d, v in case["required"].items()
        )
        require(matches == (status == "passed"), f"unexpected numerical pass/failure: {node}")
        require(record["status"] == status, f"unexpected assertion outcome: {node}")
        require(
            record["reason"] == (None if status == "passed" else "NUMERIC_MISMATCH"),
            f"wrong numeric failure reason: {node}",
        )
        entry = junit[node.split("::")[1]]
        require(not entry.findall("error") and not entry.findall("skipped"), "JUnit error/skip")
        failures = entry.findall("failure")
        require(len(failures) == (status == "failed"), f"unexpected JUnit outcome: {node}")
        if failures:
            require(
                failures[0].attrib.get("message")
                == f"conftest.BillingMismatch: {case['assertion_id']}",
                f"wrong JUnit failure assertion: {node}",
            )
        summaries.append(
            dict(
                nodeid=node,
                scenario=case["scenario"],
                fixture_sha256=case["fixture_sha256"],
                assertion_id=case["assertion_id"],
                target=target,
                expected_m=case["required"],
                legacy_expected_m=case["legacy"],
                actual_m={d: round(v, 6) for d, v in record["actual"].items()},
                tolerance_m=case["tolerance_m"],
                status=status,
                reason=record["reason"],
            )
        )
    return summaries


def run_target(root, directory, target, run_id):
    directory.mkdir(parents=True, exist_ok=False)
    environment = {
        **os.environ,
        "GEO_AUDIT_TARGET": target,
        "GEO_AUDIT_RUN_ID": run_id,
        "GEO_AUDIT_EVIDENCE": str((directory / "evidence.json").resolve()),
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    }
    environment.pop("PYTEST_ADDOPTS", None)
    command = [
        sys.executable,
        "-m",
        "pytest",
        TEST_FILE,
        "-q",
        "-p",
        "no:cacheprovider",
        "--junitxml",
        str((directory / "junit.xml").resolve()),
    ]
    process = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True)
    (directory / "pytest.log").write_text(process.stdout + process.stderr)
    return process.returncode


def verify(output, root=Path(".")):
    root = Path(root)
    require(not Path(output).exists(), "output must be a fresh directory")
    cases = check_manifest(root)
    Path(output).mkdir(parents=True)
    manifest_hash = hashlib.sha256((root / MANIFEST).read_bytes()).hexdigest()
    run_id = uuid.uuid4().hex  # Freshness token; kept out of the canonical summary.
    results = {}
    for target in ("corrected", "legacy"):
        directory = Path(output) / target
        code = run_target(root, directory, target, run_id)
        results[target] = validate_run(directory, target, run_id, code, cases, manifest_hash)
    summary = dict(
        status="PASS",
        cases=len(cases),
        legacy_red=sum(c["legacy_status"] == "failed" for c in cases),
        legacy_controls=sum(c["legacy_status"] == "passed" for c in cases),
        manifest_sha256=manifest_hash,
        results=results,
    )
    (Path(output) / "summary.json").write_text(
        json.dumps(summary, sort_keys=True, indent=2, allow_nan=False) + "\n"
    )
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", type=Path, required=True, help="fresh evidence directory")
    args = parser.parse_args()
    try:
        summary = verify(args.output)
    except (VerificationError, KeyError, TypeError) as error:
        raise SystemExit(
            f"red/green verification FAILED: {type(error).__name__}: {error}"
        ) from None
    print(
        f"PASS: {summary['cases']} corrected greens; {summary['legacy_red']} legacy reds at "
        f"their numeric assertions; {summary['legacy_controls']} legacy controls green"
    )


if __name__ == "__main__":
    main()
