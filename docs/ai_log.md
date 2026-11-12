# AI contribution log

## Phase 1 — 2026-11-12

The assistant drafted the package, parser, spatial/time primitives, threshold
predicates, tests, installation configuration and documentation from reviewed
requirements. It inspected reference conventions without copying code.

Validation used literal geometric/time expectations, exact threshold tests,
invalid-input reconciliation, two host-timezone subprocesses, and both editable
and non-editable installations. Human audit of this implementation is pending.

Actual correction: the first test run found a deprecated Shapely transform
call under warnings-as-errors. The assistant replaced it with the supported
API and reran the suite. Ruff corrected import ordering. No billing fix or
red/green regression is claimed at this stage.

## Phase 1 audit remediation — 2026-11-12

The assistant addressed the independently reproduced F1–F3 findings: Polygon
ring repair before validation, reporting-date overflow after parsing, and
measured dimensions escaping the XY-only contract. Existing parser error
handling now receives the shared time-range validation error; no parser or
model rewrite was required. Installed Shapely API documentation was inspected
before selecting `get_coordinate_dimension`.

The assistant added focused ring/dimension/time/quarantine regressions and
strengthened serialization and mixed-intersection coverage. It independently
cross-checked the existing projection literals with a scalar WGS84 series and
recorded the equations, without inventing historical provenance. Full-suite
and isolated installation results are appended to phase1_evidence.md. Human
review of these remediation changes remains pending.
