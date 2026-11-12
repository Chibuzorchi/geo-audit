"""Negative tests: the shipped red/green verifier must reject each corruption for its reason.

One real verifier run produces genuine evidence. Each test copies it, injects exactly
one corruption, and asserts the rejection message. End-to-end cases rerun real pytest
subprocesses against a temporary project copy with a sabotaged implementation.
"""

import hashlib
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
_spec = importlib.util.spec_from_file_location(
    "verify_red_green", ROOT / "scripts/verify_red_green.py"
)
vrg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vrg)


@pytest.fixture(scope="module")
def genuine(tmp_path_factory):
    output = tmp_path_factory.mktemp("genuine") / "run"
    summary = vrg.verify(output, root=ROOT)
    assert summary["status"] == "PASS" and summary["legacy_red"] == 13
    return output


@pytest.fixture
def cases():
    return vrg.check_manifest(ROOT)


def manifest_hash():
    return hashlib.sha256((ROOT / vrg.MANIFEST).read_bytes()).hexdigest()


def corrupt(genuine, tmp_path, target, evidence=None, junit=None, returncode=None, raw=None):
    """Copy one target's real evidence, apply one corruption, run validation."""
    directory = tmp_path / target
    shutil.copytree(genuine / target, directory)
    path = directory / "evidence.json"
    payload = json.loads(path.read_text())
    run_id = payload["run_id"]
    if evidence:
        evidence(payload)
        path.write_text(json.dumps(payload))
    if raw:
        path.write_text(raw(path.read_text()))
    if junit:
        xml = directory / "junit.xml"
        junit(xml)
    code = returncode if returncode is not None else (0 if target == "corrected" else 1)
    return lambda cases: vrg.validate_run(directory, target, run_id, code, cases, manifest_hash())


def record(payload, scenario):
    return next(r for r in payload["assertions"] if r["scenario"] == scenario)


def event(payload, scenario, phase):
    return next(
        e
        for e in payload["events"]
        if e["nodeid"].endswith(f"[{scenario}]") and e["phase"] == phase
    )


def test_genuine_evidence_is_accepted(genuine, cases, tmp_path):
    for target in ("corrected", "legacy"):
        assert len(corrupt(genuine, tmp_path, target)(cases)) == 20


# Each entry: (target, corruption kwargs, intended rejection reason)
def _legacy_pass(p):
    r = record(p, "S2b")
    r.update(actual={"2026-11-04": 200.0}, status="passed", reason=None)
    event(p, "S2b", "call").update(outcome="passed", failure=None, assertion_id=None)


def _corrected_fail(p):
    r = record(p, "S9a")
    r.update(actual={"2026-11-04": 2900.0}, status="failed", reason="NUMERIC_MISMATCH")
    event(p, "S9a", "call").update(
        outcome="failed", failure="numeric_mismatch", assertion_id="S9a_REQUIRED_DISTANCE"
    )


CORRUPTIONS = {
    "corrected_failure_exit": ("corrected", dict(returncode=1), "unexpected pytest exit status"),
    "corrected_failure_record": (
        "corrected",
        dict(evidence=_corrected_fail),
        "unexpected call outcome",
    ),
    "legacy_unexpected_pass": ("legacy", dict(evidence=_legacy_pass), "unexpected call outcome"),
    "legacy_wrong_assertion": (
        "legacy",
        dict(
            evidence=lambda p: event(p, "S2b", "call").update(assertion_id="S3_REQUIRED_DISTANCE")
        ),
        "wrong failure assertion",
    ),
    "legacy_wrong_exception_type": (
        "legacy",
        dict(evidence=lambda p: event(p, "S4", "call").update(failure="ZeroDivisionError")),
        "wrong call failure type",
    ),
    "setup_exception": (
        "legacy",
        dict(
            evidence=lambda p: event(p, "S7", "setup").update(
                outcome="failed", failure="ValueError"
            )
        ),
        "unexpected setup outcome",
    ),
    "teardown_exception": (
        "corrected",
        dict(evidence=lambda p: event(p, "S1", "teardown").update(outcome="failed")),
        "unexpected teardown outcome",
    ),
    "collection_error_exit": ("legacy", dict(returncode=2), "unexpected pytest exit status"),
    "missing_result": (
        "legacy",
        dict(evidence=lambda p: p["assertions"].remove(record(p, "S8"))),
        "missing or duplicate assertion results",
    ),
    "missing_collected": (
        "corrected",
        dict(evidence=lambda p: p["collected"].pop()),
        "missing or duplicate collected tests",
    ),
    "duplicate_test_id": (
        "corrected",
        dict(evidence=lambda p: p["collected"].append(p["collected"][0])),
        "missing or duplicate collected tests",
    ),
    "duplicate_phase": (
        "corrected",
        dict(evidence=lambda p: p["events"].append(p["events"][0])),
        "missing or duplicate execution phases",
    ),
    "deselected": (
        "corrected",
        dict(evidence=lambda p: p["deselected"].append(p["collected"][0])),
        "deselected required tests",
    ),
    "missing_junit": (
        "legacy",
        dict(junit=lambda x: x.unlink()),
        "missing or malformed JUnit",
    ),
    "truncated_junit": (
        "legacy",
        dict(junit=lambda x: x.write_bytes(x.read_bytes()[: x.stat().st_size // 2])),
        "missing or malformed JUnit",
    ),
    "junit_skip": (
        "corrected",
        dict(junit=lambda x: x.write_text(x.read_text().replace('skipped="0"', 'skipped="1"'))),
        "unexpected JUnit totals",
    ),
    "missing_evidence": (
        "corrected",
        dict(raw=lambda text: ""),
        "missing or malformed JSON evidence",
    ),
    "stale_evidence": (
        "legacy",
        dict(evidence=lambda p: p.update(run_id="0" * 32)),
        "stale run identity",
    ),
    "stale_junit": (
        "legacy",
        dict(
            junit=lambda x: x.write_text(
                x.read_text().replace('name="run_id" value="', 'name="run_id" value="old')
            )
        ),
        "stale JUnit run identity",
    ),
    "invalid_fixture_hash": (
        "legacy",
        dict(evidence=lambda p: record(p, "S3").update(fixture_sha256="0" * 64)),
        "invalid fixture hash",
    ),
    "incorrect_legacy_value": (
        "legacy",
        dict(evidence=lambda p: record(p, "S9a")["actual"].update({"2026-11-04": 2901.0})),
        "incorrect numerical value",
    ),
    "nan_token": (
        "legacy",
        dict(raw=lambda text: text.replace("5900.000006", "NaN", 1)),
        "nonfinite evidence",
    ),
    "infinity_token": (
        "corrected",
        dict(raw=lambda text: text.replace('"tolerance_m": 0.01', '"tolerance_m": Infinity', 1)),
        "nonfinite evidence",
    ),
    "nan_string": (
        "corrected",
        dict(evidence=lambda p: record(p, "S1")["actual"].update({"2026-11-04": "NaN"})),
        "nonfinite numerical outcome",
    ),
    "missing_explicit_zero": (
        "legacy",
        dict(evidence=lambda p: record(p, "S7")["actual"].pop("2026-11-05")),
        "missing or unexpected numerical outcome keys",
    ),
    "unexpected_raw_day": (
        "corrected",
        dict(evidence=lambda p: record(p, "S8")["raw_dates"].append("2026-11-06")),
        "missing or unexpected raw driver/day keys",
    ),
    "unexpected_outcome_day": (
        "corrected",
        dict(evidence=lambda p: record(p, "S1")["actual"].update({"2026-11-05": 0.0})),
        "missing or unexpected numerical outcome keys",
    ),
    "skipped_test": (
        "corrected",
        dict(evidence=lambda p: event(p, "S10", "setup").update(outcome="skipped")),
        "unexpected setup outcome",
    ),
    "xfailed_test": (
        "legacy",
        dict(evidence=lambda p: event(p, "S6c", "call").update(wasxfail=True)),
        "xfail required test",
    ),
    "wrong_target": (
        "legacy",
        dict(evidence=lambda p: p.update(target="corrected")),
        "wrong evidence target",
    ),
    "changed_tolerance": (
        "corrected",
        dict(evidence=lambda p: record(p, "S5b").update(tolerance_m=1.0)),
        "changed tolerance",
    ),
    "malformed_record": (
        "corrected",
        dict(evidence=lambda p: record(p, "S1").pop("status")),
        "malformed evidence",
    ),
}


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_corrupted_evidence_rejected(name, genuine, cases, tmp_path):
    target, kwargs, reason = CORRUPTIONS[name]
    validate = corrupt(genuine, tmp_path, target, **kwargs)
    with pytest.raises(vrg.VerificationError, match=reason):
        validate(cases)


# ------------------------------------------------------------ manifest / oracle drift


def project_copy(tmp_path):
    """Minimal public project tree needed by the regression suite; no private files."""
    root = tmp_path / "project"
    shutil.copytree(ROOT / "tests", root / "tests", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(ROOT / "data/synthetic", root / "data/synthetic")
    (root / "results/phase2").mkdir(parents=True)
    shutil.copy(ROOT / "results/phase2/r5_only.json", root / "results/phase2/r5_only.json")
    shutil.copy(ROOT / "pyproject.toml", root / "pyproject.toml")
    return root


def edit_manifest(root, which, **changes):
    path = root / vrg.MANIFEST
    data = json.loads(path.read_text())
    next(c for c in data if c["scenario"] == which).update(changes)
    path.write_text(json.dumps(data, indent=1))


@pytest.mark.parametrize(
    ("scenario", "changes", "reason"),
    [
        ("S2b", dict(required={"2026-11-04": 300}), "oracle drift"),
        ("S9a", dict(legacy={"2026-11-04": 2950}), "legacy drift"),
        ("S2b", dict(legacy_status="passed"), "classification contradicts"),
        ("S1", dict(fixture_sha256="f" * 64), "invalid fixture hash"),
        ("S1", dict(tolerance_m=5), "tolerance outside plan budget"),
        (
            "S1",
            dict(scenario="S11", nodeid="tests/regression/test_billing.py::test_billing[S11]"),
            "characterization",
        ),
    ],
)
def test_manifest_drift_rejected(scenario, changes, reason, tmp_path):
    root = project_copy(tmp_path)
    edit_manifest(root, scenario, **changes)
    with pytest.raises(vrg.VerificationError, match=reason):
        vrg.check_manifest(root)


def test_duplicate_manifest_id_rejected(tmp_path):
    root = project_copy(tmp_path)
    path = root / vrg.MANIFEST
    data = json.loads(path.read_text())
    path.write_text(json.dumps(data + [data[0]]))
    with pytest.raises(vrg.VerificationError, match="duplicate manifest node IDs"):
        vrg.check_manifest(root)


def test_changed_dataset_row_rejected(tmp_path):
    root = project_copy(tmp_path)
    csv_path = root / vrg.DATASET
    lines = csv_path.read_text().split("\n")
    assert lines[2].startswith("SYN-S1-00-P001,")
    lines[2] = lines[2].replace(",true", ",false")
    csv_path.write_text("\n".join(lines))
    with pytest.raises(vrg.VerificationError, match="invalid fixture hash: S1"):
        vrg.check_manifest(root)


def test_existing_output_rejected(tmp_path):
    with pytest.raises(vrg.VerificationError, match="fresh directory"):
        vrg.verify(tmp_path, root=ROOT)


# ------------------------------------------------------------ real subprocess sabotage


def sabotage(root, code):
    conftest = root / "tests/regression/conftest.py"
    conftest.write_text(conftest.read_text() + "\n\n# --- injected by negative test ---\n" + code)


def test_e2e_broken_corrected_implementation_rejected(tmp_path):
    root = project_copy(tmp_path)
    sabotage(
        root,
        "_real = corrected\n"
        "def corrected(rows, roads, zone):\n"
        "    result = _real(rows, roads, zone)\n"
        "    return type(result)(**{**result.__dict__, 'totals': {k: v + 1 for k, v in result.totals.items()}})\n",
    )
    with pytest.raises(vrg.VerificationError, match="unexpected pytest exit status: 1"):
        vrg.verify(tmp_path / "out", root=root)
    assert "S1_REQUIRED_DISTANCE" in (tmp_path / "out/corrected/pytest.log").read_text()


def test_e2e_harness_silently_runs_corrected_for_legacy_rejected(tmp_path):
    """A harness that ignores GEO_AUDIT_TARGET makes legacy look green; must be rejected."""
    root = project_copy(tmp_path)
    sabotage(root, "os.environ['GEO_AUDIT_TARGET'] = 'corrected'\n")
    with pytest.raises(vrg.VerificationError, match="wrong evidence target"):
        vrg.verify(tmp_path / "out", root=root)


def test_e2e_legacy_raw_keys_changed_rejected(tmp_path):
    """Swapping legacy for the corrected calculator changes raw keys: setup must not pass."""
    root = project_copy(tmp_path)
    sabotage(
        root,
        "legacy = lambda rows, zone: corrected(\n"
        "    rows, LineString([(320000, 4150000), (330000, 4150000)]), zone)\n",
    )
    with pytest.raises(vrg.VerificationError, match="unexpected setup outcome"):
        vrg.verify(tmp_path / "out", root=root)


def test_e2e_setup_error_disguised_as_red_rejected(tmp_path):
    """Legacy still exits 1, but one intended red fails in setup, not at its assertion."""
    root = project_copy(tmp_path)
    sabotage(
        root,
        "_parse = parse_rows\n"
        "def parse_rows(rows):\n"
        "    if os.environ.get('GEO_AUDIT_TARGET') == 'legacy' and any('-S2b-' in r['ping_id'] for r in rows):\n"
        "        raise RuntimeError('synthetic setup failure')\n"
        "    return _parse(rows)\n",
    )
    with pytest.raises(vrg.VerificationError, match="unexpected setup outcome.*S2b"):
        vrg.verify(tmp_path / "out", root=root)


def test_e2e_import_error_rejected(tmp_path):
    root = project_copy(tmp_path)
    conftest = root / "tests/regression/conftest.py"
    conftest.write_text("raise ImportError('synthetic import failure')\n" + conftest.read_text())
    with pytest.raises(vrg.VerificationError, match="missing or malformed JSON evidence"):
        vrg.verify(tmp_path / "out", root=root)
