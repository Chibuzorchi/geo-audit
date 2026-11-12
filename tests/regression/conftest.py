"""Small pytest evidence adapter; calculator expectations come only from the manifest."""

import csv
import hashlib
import json
import os
from pathlib import Path

import pytest
from shapely.geometry import LineString, box

from geo_audit.calc_corrected import calculate as corrected
from geo_audit.calc_legacy import calculate as legacy
from geo_audit.io import parse_rows

MANIFEST = Path("tests/regression/manifest.json")
CASES = json.loads(MANIFEST.read_text())


class BillingMismatch(AssertionError):
    def __init__(self, assertion_id):
        self.assertion_id = assertion_id
        super().__init__(assertion_id)


def pytest_configure(config):
    config._billing = dict(collected=[], deselected=[], events=[], assertions=[])


def pytest_collection_finish(session):
    session.config._billing["collected"] = [i.nodeid for i in session.items]


def pytest_deselected(items):
    if items:
        items[0].config._billing["deselected"].extend(i.nodeid for i in items)


@pytest.fixture(scope="session", autouse=True)
def run_identity(record_testsuite_property):
    record_testsuite_property("run_id", os.environ.get("GEO_AUDIT_RUN_ID", "direct"))


@pytest.fixture(params=CASES, ids=lambda c: c["scenario"])
def billing_assertion(request):
    case = request.param
    target = os.environ.get("GEO_AUDIT_TARGET", "corrected")
    if target not in ("legacy", "corrected"):
        raise ValueError("invalid GEO_AUDIT_TARGET")
    if case["scenario"] == "R5_ONLY":
        rows = json.loads(Path("results/phase2/r5_only.json").read_text())["raw_rows"]
    else:
        with Path("data/synthetic/SYNTHETIC_gps_pings.csv").open() as stream:
            all_rows = list(csv.DictReader(stream))
        first = case["first_row"] - 1
        rows = all_rows[first : first + case["row_count"]]
    digest = hashlib.sha256(
        json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if digest != case["fixture_sha256"]:
        raise ValueError("fixture hash mismatch")
    parsed = parse_rows(rows)
    zone = box(322050, 4149500, 327950, 4150500)
    roads = LineString([(320000, 4150000), (330000, 4150000)])
    result = legacy(parsed, zone) if target == "legacy" else corrected(parsed, roads, zone)
    keys = {(case["driver"], d) for d in case["raw_dates"][target]}
    if set(result.totals) != keys:
        raise ValueError("missing or unexpected raw driver/day keys")
    # Only independently declared absent legacy comparison dates receive padding.
    actual = {
        day: result.totals[(case["driver"], day)] if day in case["raw_dates"][target] else 0
        for day in case["required"]
    }

    def check():
        status = (
            "passed"
            if all(abs(actual[d] - v) <= case["tolerance_m"] for d, v in case["required"].items())
            else "failed"
        )
        request.node._billing_record = dict(
            nodeid=request.node.nodeid,
            scenario=case["scenario"],
            assertion_id=case["assertion_id"],
            fixture_sha256=digest,
            target=target,
            expected=case["required"],
            actual=actual,
            legacy_expected=case["legacy"],
            tolerance_m=case["tolerance_m"],
            raw_dates=sorted(d for _, d in result.totals),
            status=status,
            reason=None if status == "passed" else "NUMERIC_MISMATCH",
        )
        if status == "failed":
            raise BillingMismatch(case["assertion_id"])

    return check


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    failure = None
    assertion_id = None
    if call.excinfo:
        error = call.excinfo.value
        failure = "numeric_mismatch" if isinstance(error, BillingMismatch) else type(error).__name__
        assertion_id = error.assertion_id if isinstance(error, BillingMismatch) else None
    item.config._billing["events"].append(
        dict(
            nodeid=item.nodeid,
            phase=report.when,
            outcome=report.outcome,
            failure=failure,
            assertion_id=assertion_id,
            wasxfail=hasattr(report, "wasxfail"),
        )
    )
    if report.when == "call" and hasattr(item, "_billing_record"):
        item.config._billing["assertions"].append(item._billing_record)


def pytest_sessionfinish(session, exitstatus):
    destination = os.environ.get("GEO_AUDIT_EVIDENCE")
    if destination:
        payload = dict(
            **session.config._billing,
            run_id=os.environ["GEO_AUDIT_RUN_ID"],
            target=os.environ["GEO_AUDIT_TARGET"],
            exitstatus=int(exitstatus),
            manifest_sha256=hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        )
        Path(destination).write_text(
            json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n"
        )
