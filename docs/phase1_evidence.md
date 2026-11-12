# Phase 1 verification

Verified locally on 2026-11-12, macOS arm64, Python 3.12.12.
No remote CI or Linux run is claimed. No dataset or billing calculation exists.

## Environment and installation

The initial workspace contained only private planning/source documents and OS
metadata. Python 3.12 and pip were available. A new venv was created without
system packages; global testing packages were not used. Dependencies were
resolved once, then frozen in `requirements.lock`, including pip and build tools.

Versions: pyproj 3.8.0 (PROJ 9.8.1), Shapely 2.2.0 (GEOS 3.14.1),
pytest 9.2.0, Ruff 0.17.4, setuptools 84.2.1, wheel 0.48.0.
The lock also records numpy, certifi, iniconfig, packaging, pluggy and Pygments.

Executed commands:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install pyproj shapely pytest ruff setuptools wheel
.venv/bin/python -m pip freeze --all > requirements.lock
make install
make lint
.venv/bin/python -m pytest tests/unit --junitxml=.scratch/phase1.xml
.venv/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir .scratch/wheels .
python3.12 -m venv .scratch/verify-env
.scratch/verify-env/bin/python -m pip install --only-binary=:all: -r requirements.lock
.scratch/verify-env/bin/python -m pip install --no-deps .scratch/wheels/geo_audit-0.1.0-py3-none-any.whl
.scratch/verify-env/bin/python -m pytest tests/unit --junitxml=.scratch/wheel-tests.xml
.scratch/verify-env/bin/python -m pip check
.venv/bin/python -m pip check
.venv/bin/python -m geo_audit --version
.venv/bin/geo-audit --version
```

## Results

- Editable installation: 82 passed, 0 failed, 0 skipped, 0 xfailed.
- Non-editable wheel installation in a second isolated venv: 82 passed,
  0 failed, 0 skipped, 0 xfailed. Imported package path was in site-packages.
- Both dependency consistency checks: no broken requirements.
- Module and console entry points: version 0.1.0; unavailable commands exit 2.
- Ruff checks and formatting pass. Warnings are errors in pytest.
- Wheel inspection: only the nine package modules and distribution metadata;
  no private documents, tests or employer material.
- Geometry evidence includes 5 m triangle, exact 100 m road distance, 5900 m
  outside-to-outside intersection, boundary contact/overlap and polygon holes.
- Time evidence includes 50/50 m midnight division and 20/30 m combined
  zone/day division, with two subprocess host timezones.
- S12 parser evidence: four quarantines, one assignable and three unassignable.
  Billing totals are deliberately not tested or implemented in Phase 1.
- Sampled planar/ellipsoid maximum relative distortion: 0.000123351862
  (about 0.01234%), at five locations and three directions. This is a sampled
  observation, not a proof for every point. Test bound is a conservative 0.1%.

Initial run: 66 passed, one failed because Shapely 2.2 deprecated
`shapely.ops.transform`. Replaced it with `shapely.transform` using
`interleaved=False`, following the installed library documentation. The next
67-test run passed. Additional geometry, input and time tests increased coverage
to 82 passing cases. Ruff initially corrected one import-order issue.

## Boundaries and remaining work

No generator package, legacy/corrected calculator, duplicate selection,
batch ID-conflict processing, complete state machine, billing aggregation or
regression verifier is implemented. Parser results preserve raw/normalized
fields for those later stages. Valid parsing is not acceptance for billing.

Dependencies are version-pinned, not artifact-hash locked. Wheel installation
was verified locally; cross-platform availability remains unverified. This is
not a full clean-checkout demo or end-to-end reproducibility claim.

Reference review informed test isolation, explicit configuration and evidence
reporting. No reference implementation code or private material was copied.
Local Git has no remote and no commits. Public source is staged explicitly;
private context, environments and scratch evidence are ignored.

## Audit remediation — 2026-11-12

Historical 82-test results above remain unchanged. The audit found three gaps;
this remediation adds validation and regressions without implementing billing.

- F1: raw Polygon exterior/interior rings must contain at least four finite XY
  positions and explicitly repeat the first position. Validation runs before
  Shapely can close or coerce a ring. Existing topology/extent checks remain.
- F2: `as_utc` now requires representability in UTC and UTC+9, shared by parsing,
  reporting and day partitioning. Supported UTC instants run inclusively from
  0001-01-01 00:00:00 through 9999-12-31 14:59:59.999999. The corresponding
  local range starts at 0001-01-01 09:00:00 and ends at datetime's maximum.
  Earlier local year-1 instants that need UTC year 0 are unsupported.
  Conversion overflow becomes `ValueError("TIMESTAMP_OUT_OF_RANGE")`.
  The existing parser preserves the raw row and prefixes the reason with the
  field name. Invalid device timestamps become None and are unassignable;
  an invalid receipt alone does not erase a valid device-day assignment.
- F3: Shapely 2.2.0's `get_coordinate_dimension` rejects dimensions other than
  XY, including XYM, XYZ and XYZM. Installed GEOS is 3.14.1.

Regression groups: `test_malformed_rings` (20 cases, exterior and interior),
`test_unsupported_dimensions` (4), `test_supported_time_boundaries` (4),
`test_unsupported_time_boundaries` (5), `test_boundary_day_partitions` (1),
`test_out_of_range_row_preserved` (4), `test_serialized_inverse_projection` (1),
and `test_mixed_line_point_intersection` (1). Boundary overlap now checks the
whole interval collection. Valid-hole tests and all original numeric
expectations remain intact. No new dependencies or public API signatures.

### Projection-reference derivation

The original literal reference had no recorded source. It was independently
cross-checked during remediation using a scalar WGS84 transverse Mercator
series, without calling pyproj or GeoAudit:

- a=6378137 m; f=1/298.257223563; e²=f(2−f); e′²=e²/(1−e²).
- φ=37.5°, λ=127°, λ₀=129°, k₀=.9996; false easting=500000 m.
- A=cosφ(λ−λ₀), T=tan²φ, C=e′²cos²φ, N=a/sqrt(1−e²sin²φ).
- M/a=(1−e²/4−3e⁴/64−5e⁶/256)φ
  −(3e²/8+3e⁴/32+45e⁶/1024)sin2φ
  +(15e⁴/256+45e⁶/1024)sin4φ−35e⁶sin6φ/3072.
- E=500000+k₀N[A+(1−T+C)A³/6+(5−18T+T²+72C−58e′²)A⁵/120].
- Y=k₀[M+Ntanφ(A²/2+(5−T+9C+4C²)A⁴/24
  +(61−58T+T²+600C−330e′²)A⁶/720)].

Angles in these expressions are radians. Executed series values:
E=323210.4691846639 m, Y=4152220.1459323866 m. Both agree with the unchanged
literal expectations (323210.469, 4152220.145) within their 0.001 m tolerance.
These are truncated-series cross-checks, not a claim about the original
literal values' provenance. The executable derivation is retained in local
scratch evidence; the complete equations above make it reproducible.

### Remediation execution results

On macOS arm64 / Python 3.12.12, unchanged locked dependencies:

| Command | Exit | Result |
| --- | ---: | --- |
| `make lint` | 0 | Ruff check and format check passed |
| `.venv/bin/python -m pytest tests/unit --junitxml=.scratch/remediation/unit.xml` | 0 | 122 passed, 0 failed/errors/skipped |
| `make install VENV=.scratch/remediation/editable` | 0 | Fresh isolated editable installation |
| `.scratch/remediation/editable/bin/python -m pytest tests/unit --junitxml=.scratch/remediation/editable.xml` | 0 | 122 passed, 0 failed/errors/skipped |
| `.scratch/remediation/editable/bin/python -m pip wheel --no-deps --no-build-isolation --wheel-dir .scratch/remediation/wheels .` | 0 | Wheel built |
| `python3.12 -m venv .scratch/remediation/wheel-env` | 0 | Fresh isolated wheel environment |
| `.scratch/remediation/wheel-env/bin/python -m pip install --only-binary=:all: -r requirements.lock` | 0 | Lock installed |
| `.scratch/remediation/wheel-env/bin/python -m pip install --no-deps .scratch/remediation/wheels/geo_audit-0.1.0-py3-none-any.whl` | 0 | Wheel installed |

Wheel suite execution used:

```sh
.scratch/remediation/wheel-env/bin/python -c "import geo_audit,pytest; print('PACKAGE',geo_audit.__file__); assert 'wheel-env/lib/python3.12/site-packages/' in geo_audit.__file__; raise SystemExit(pytest.main(['tests/unit','--junitxml=.scratch/remediation/wheel.xml']))"
```

Exit 0: 122 passed, 0 failed/errors/skipped. The import assertion ran in the
same process as pytest and confirmed the installed package, not local src.
Each new test group listed above also ran separately via
`.scratch/remediation/editable/bin/python -m pytest tests/unit/<file>::<test>`;
all exited 0, with the listed case counts and no skips. Each environment's
`python -m pip check` exited 0. Module/console help and `--version` exited 0;
version remained 0.1.0. All four future commands exited 2 through both entry
points in both environments. The local scratch command manifest records all
41 isolated-verification invocations, exact arguments and exit codes, with
logs and JUnit files. No Linux or remote CI execution is claimed.

The first remediation full-suite run passed; no failed remediation test result
was hidden or converted into an expected failure. Source changes are confined
to geometry/time validation; parser/model interfaces and dependency versions
are unchanged. Historical 82-case execution is not represented as 122 cases.
