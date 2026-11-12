# GeoAudit

GeoAudit audits distance billing on **synthetic** GPS pings. It includes a
deterministic dataset generator, deliberately wrong legacy calculation, blind QA
checker and corrected calculation with per-driver/day comparison.

Requires Python 3.12 and make on POSIX. Install and verify:

```sh
make install
make lint
make test
.venv/bin/python -m geo_audit --version
.venv/bin/geo-audit --help
```

Without make, create `.venv` with `python3.12 -m venv .venv`, install
`requirements.lock` using `.venv/bin/python -m pip install --only-binary=:all: -r requirements.lock`,
then install the project with `.venv/bin/python -m pip install --no-deps --no-build-isolation -e .`.
The lock pins runtime, transitive, testing and build dependencies. Updating it
is a deliberate dependency resolution step, not part of routine installation.

Reproduce the baseline and discovery in one step:

```sh
make baseline            # writes .scratch/baseline/{data,results}
```

That runs:

```sh
geo-audit generate --output DIR/data           # synthetic CSV, geometry, labels, manifest
geo-audit check --input DIR/data/SYNTHETIC_gps_pings.csv \
  --roads DIR/data/roads.geojson --zone DIR/data/zone.geojson --output DIR/results
python scripts/discover_baseline.py --data DIR/data --results DIR/results \
  --expectations tests/expectations/analytic.json
```

`check` exits 0 with findings, 1 with `--gate` and findings, and 2 on bad input.
It writes `findings.json` (observation conditions), `decision_conflicts.json`
(legacy rule conflicts and explicitly provisional raw-pair anomalies), `segments_legacy.json`,
`legacy_totals.json` and `quarantine.json`. `compare` produces before/after evidence; `demo` remains unavailable.
Reference outputs are in `data/synthetic/` and `results/phase2/`; see
`docs/phase2_evidence.md`.

## Contracts

- Geometry uses UTM 52N metres after explicit longitude/latitude projection.
  Geographic inputs are limited to longitude 126.8–127.3, latitude 37.3–37.7.
  Planar primitives accept metre XY coordinates; never pass raw degrees to them.
- Zone boundaries count; point-only contact has zero length. Polygon holes and
  multiple intersection intervals are supported.
- Timestamps require ISO date/time with seconds and an explicit `Z` or `±HH:MM`
  offset, at most six fractional digits. Days use fixed UTC+9.
- Thresholds reject only road distance >100 m or speed >150 km/h.
- Parsing preserves each CSV record with raw evidence and quarantine reasons.
  Required fields: `ping_id,driver_id,ts_utc,lat,lon,received_at_utc,is_synthetic`.
  Synthetic flags are literal `true` or `false`. Identifiers are ASCII letters,
  digits, underscores or hyphens. Invalid headers/syntactically broken CSV fail
  explicitly. Blank or mis-sized data records are quarantined, not dropped.
- Parser validity is not billing acceptance. Batch ID-conflict detection,
  duplicate selection, noise filtering and billing aggregation run in the corrected path.

`config` holds constants, `models` immutable records, `io` parsing/serialization,
`geo` metre geometry, `timecut` time partitions and `rules` selection and pure thresholds.
No tests require credentials, live services, current time or a database.
Run one test with `.venv/bin/python -m pytest tests/unit/test_geo.py::test_triangle`.

See `docs/phase1_evidence.md` for measured verification and limitations.

Timestamp representability: normalized UTC must fall between
`0001-01-01T00:00:00Z` and `9999-12-31T14:59:59.999999Z`, inclusive, so both
UTC and UTC+9 are representable. Unsupported conversions raise
`ValueError("TIMESTAMP_OUT_OF_RANGE")`; the parser preserves the row and
quarantines it. An unsupported device instant is unassignable. Polygon rings
must be explicitly closed before conversion; M, Z and ZM geometries are rejected.


## Corrected comparison (Phase 3)

Run `.venv/bin/geo-audit compare --input data/synthetic/SYNTHETIC_gps_pings.csv --roads data/synthetic/roads.geojson --zone data/synthetic/zone.geojson --output .scratch/comparison`
with a fresh output directory. This writes driver/day CSV, per-row decisions,
legacy and corrected ledgers and a reconciled summary. The legacy column retains
UTC date labels; corrected dates use fixed UTC+9. This is reporting discrepancy
analysis, not a financial settlement. Missing calculation keys carry presence flags.

The corrected path quarantines conflicting IDs, deterministically selects duplicate
survivors, sorts device instants, filters road noise then speed against the last
accepted anchor, clips movement and splits it at reporting midnight. No label or
answer-key access occurs in either calculation. Empty or fully quarantined input
writes its decision evidence and returns exit 2. All-noise input can return valid
zero totals. `demo` and the final red/green verifier remain deferred.

See `docs/phase3_evidence.md` and `results/phase3/` for executed evidence.
