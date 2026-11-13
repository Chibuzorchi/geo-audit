"""The demo must fail closed: prerequisites, frozen references and output freshness."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from geo_audit.demo import DemoFailure, PrerequisiteFailure, run_demo

ROOT = Path(__file__).parents[2]
PUBLIC = ["data", "results", "scripts", "tests", "pyproject.toml", "requirements.lock"]


def project_copy(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    for name in PUBLIC:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, root / name, ignore=shutil.ignore_patterns("__pycache__"))
        else:
            shutil.copy(source, root / name)
    return root


def test_existing_output_is_a_prerequisite_failure(tmp_path):
    with pytest.raises(PrerequisiteFailure, match="must not exist"):
        run_demo(tmp_path, root=ROOT)


def test_missing_project_file_exit_2(tmp_path):
    root = project_copy(tmp_path)
    (root / "tests/regression/manifest.json").unlink()
    result = subprocess.run(
        [sys.executable, "-m", "geo_audit", "demo", "--output", "out"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "missing project file: tests/regression/manifest.json" in result.stderr
    assert not (root / "out").exists()


def test_tampered_frozen_reference_fails(tmp_path):
    root = project_copy(tmp_path)
    path = root / "results/phase3/driver_day.csv"
    path.write_text(path.read_text().replace("5900.000", "5901.000", 1))
    with pytest.raises(
        DemoFailure, match="frozen reference changed: results/phase3/driver_day.csv"
    ):
        run_demo(tmp_path / "out", root=root)


def test_demo_passes_in_public_project_copy(tmp_path):
    """The copy holds only the public allowlist; the demo must still pass."""
    root = project_copy(tmp_path)
    assert sorted(p.name for p in root.iterdir()) == sorted(PUBLIC)
    summary = run_demo(tmp_path / "out", root=root)
    assert summary["status"] == "PASS"
    assert summary["red_green"] == dict(cases=20, legacy_red=13, legacy_controls=7)
    assert summary["reconciliation"]["states"] == {
        "accepted": 3246,
        "accepted_warning": 9,
        "quarantined": 12,
        "rejected_duplicate": 39,
        "rejected_noise": 21,
    }


@pytest.mark.parametrize("delta,passes", [(6e-11, True), (0.000002, False)])
def test_raw_evidence_precision_is_narrow(tmp_path, delta, passes):
    import json

    from geo_audit.demo import same_files

    fresh, reference = tmp_path / "fresh", tmp_path / "reference"
    fresh.mkdir()
    reference.mkdir()
    (reference / "raw.json").write_text(json.dumps({"distance_m": 100.00000273383924}))
    (fresh / "raw.json").write_text(json.dumps({"distance_m": 100.00000273383924 + delta}))
    if passes:
        assert same_files(fresh, reference, raw_json=("raw.json",)) == ["raw.json"]
    else:
        with pytest.raises(DemoFailure, match="differs"):
            same_files(fresh, reference, raw_json=("raw.json",))
    with pytest.raises(DemoFailure, match="differs"):
        same_files(fresh, reference)  # Ordinary evidence retains byte comparison.


@pytest.mark.parametrize(
    "corrupt", ['{"distance_m": NaN}', '{"other": 100}', '{"distance_m": Infinity}']
)
def test_raw_evidence_corruption_rejected(tmp_path, corrupt):
    from geo_audit.demo import same_files

    fresh, reference = tmp_path / "fresh", tmp_path / "reference"
    fresh.mkdir()
    reference.mkdir()
    (reference / "raw.json").write_text('{"distance_m": 100}')
    (fresh / "raw.json").write_text(corrupt)
    with pytest.raises((DemoFailure, ValueError)):
        same_files(fresh, reference, raw_json=("raw.json",))
