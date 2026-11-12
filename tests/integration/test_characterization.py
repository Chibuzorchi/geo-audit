"""S11/S13 characterization only: documents behaviour, never proof that a rule was fixed."""

import json
from pathlib import Path

import pytest
from shapely.geometry import LineString, box

from geo_audit.calc_corrected import calculate as corrected
from geo_audit.calc_legacy import calculate as legacy
from geo_audit.io import parse_rows
from geo_audit_synthetic.generator import scenario_rows

EXPECTED = json.loads((Path(__file__).parents[1] / "expectations/analytic.json").read_text())
ZONE = box(322050, 4149500, 327950, 4150500)
ROADS = LineString([(320000, 4150000), (330000, 4150000)])


@pytest.mark.parametrize("name", ["S11", "S13"])
def test_characterization_values(name):
    rows = parse_rows(scenario_rows(name)[0])
    (old,), (new,) = EXPECTED[name]
    key = (f"SYN-{name}-00", "2026-11-04")
    assert legacy(rows, ZONE).totals.get(key, 0) == pytest.approx(old, abs=0.01)
    assert corrected(rows, ROADS, ZONE).totals.get(key, 0) == pytest.approx(new, abs=0.01)
