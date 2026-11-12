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

## Phase 2 — 2026-11-12

An earlier assistant session drafted the generator, legacy calculator, first
checker, report writer, expectation file, discovery script and integration
tests. It left them unverified and uncommitted. This session's assistant then:

- Re-verified Phase 1 from `git archive HEAD` (122 passed) before building on it.
- Found and fixed: report output rounded coordinates to 6 dp (about 0.1 m loss).
  Coordinates now serialize at 10 dp.
- Found a gap: the checker listed observation conditions only and could not show
  why a total was wrong. It added `audit_legacy`, which compares each legacy segment
  decision with one rule and emits `decision_conflict` without totals.
- Rejected the draft's per-scenario ranking and its test asserting `primary == "S8"`.
  S7 and S8 share one cause, and a hardcoded winner is not evidence. Ranking now groups
  scenarios into six defects and is tested by invariants only.
- Added a refusal: discovery fails if any discrepancy lacks checker evidence.
- Its own first test draft had two bugs. It read decimals from S12's blank latitude,
  and it banned the word "expectations", which the checker docstring legitimately uses.
  Both were fixed in the test, not the product.
- Its own count prediction was wrong: it expected 15 `R2_SPEED` conflicts, but 12 is
  correct. The S6b return leg is 78.5 km/h, under the limit.
- Rechecked every analytic expectation literal with plain `math`.

The generator, legacy calculator and expectation literals were not altered after measurement.
Human review of Phase 2 is pending.

## Phase 2 audit remediation

The user supplied independent audit findings F1–F6. The assistant inspected code,
reproduced 168 baseline passes, and implemented provisional speed labels, per-key
ledger validation, tolerance-based ranking and complete conflict visibility.
It independently derived the S7/S8 date-only vectors and 52980/52380/600/26190 m
reconciliation using segment counts and time fractions, without a corrected calculator.
It added 16 focused regressions; all 184 tests and each new test independently passed.
An initial Ruff check fixed one import-order issue. No test failures were observed
during this remediation. Prior reports were archived, not silently rewritten.
The current evidence explicitly retracts unsupported pre-measurement freeze claims
and the claim that S7/S8 have only one cause. Human review remains pending.
