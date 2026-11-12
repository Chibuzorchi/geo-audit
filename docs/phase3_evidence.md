# Phase 3 executed evidence — synthetic GPS correction

## Baseline preservation and primary proof

At entry, all 62 files in the Phase 2 manifest matched their hashes; 184 tests and
Ruff passed. HEAD remained d193a999f0663feeade4801ddc7a2e2ed6dbf4ce.
The existing staged snapshot was captured before editing and compared byte-for-byte
afterwards. Phase 3 changes remain unstaged/untracked. No commit or remote was created.

The preserved R5 records are SYN-R5-ONLY-P0 and SYN-R5-ONLY-P1, source rows 1 and 2:
November 4 14:59:55Z and 15:00:05Z, local E=3000 and 3100, N=0.
Actual source coordinates are preserved in numerical_verification.json and the
primary decision ledger. Legacy calc_legacy.py line 28 derives the UTC endpoint date;
lines 51–56 record it and add included metres to that date.

Independent arithmetic: 100 m × 5 seconds / 10 seconds = 50 m per reporting day.
The first new allocation primitive was executed before the full filtering pipeline:
legacy remained (100.00000273383924,0), allocation became
(50.00000136691962,50.00000136691962). These agree with (100,0) and (50,50)
within the approved 0.01 m geographic-serialization tolerance.
The complete corrected path reproduced those same values. This primary proof is
wholly inside the zone and has no noise or duplicate interaction.

## Implementation

- calc_corrected.py: spatial/time fraction intersection, ordered accepted-anchor
  pipeline, final decisions, segment/day allocations and totals.
- rules.py: batch ID conflicts and deterministic duplicate selection, reusing exact
  road/speed threshold predicates.
- io.py: canonical payload identity normalizes valid fields even in malformed rows;
  malformed values remain literal. Existing parsing and immutable input records remain.
- models.py: CorrectedResult record; no mutable input fields introduced.
- report.py: corrected per-key/row/edge reconciliation, full date grid plus outer
  union, explicit presence flags, CSV decisions/totals and JSON ledgers/summary.
- cli.py: compare is active; demo remains unavailable.
- tests/integration/test_corrected.py: 55 independently asserted numeric, state,
  geometry/time, reconciliation, permutation, blindness and execution cases.
- scripts/verify_phase3.py: post-execution comparison with retained literals and
  supplemental primary evidence. This is not the Phase 4 red/green runner.
- README and AI/effort logs describe current behavior. The obsolete CLI test now
  expects only demo to be unavailable; the original test count remains 184.

The calculator accepts immutable parsed rows, never opens files, never uses labels,
and never imports the legacy calculator. CLI orchestrates both independent paths.
Existing geometry/time primitives perform all projection, clipping and midnight cuts.
No new dependencies, services or geometry framework were introduced.

## Numeric results

Copy 00 shown; paired entries are November 4 / November 5. All 63 instances pass
their unchanged expectations within 0.01 m. Full precision outputs and exact records
are in results/phase3/numerical_verification.json and the segment ledgers.

| Scenario | Required m | Executed corrected m | Executed legacy m |
|---|---:|---:|---:|
| S1 | 5900.000000 | 5900.000000 | 5900.000006 |
| S2a | 5900.000000 | 5900.000000 | 5900.000006 |
| S2b | 200.000000 | 199.999999 | 299.999995 |
| S3 | 200.000000 | 199.999999 | 276.619037 |
| S3b | 200.000000 | 199.999999 | 430.277572 |
| S4 | 200.000000 | 199.999999 | 299.999995 |
| S5a | 5900.000000 | 5900.000000 | 6060.555128 |
| S5b | 5982.136492 | 5982.136487 | 5982.136494 |
| S5c | 5900.000000 | 5900.000000 | 5983.550702 |
| S6a | 6330.560000 | 6330.559988 | 6330.559994 |
| S6b | 5900.000000 | 5900.000000 | 6336.120005 |
| S6c | 5900.000000 | 5900.000000 | 7700.000001 |
| S7 | 2950.000000 / 2950.000000 | 2949.999999 / 2950.000001 | 5900.000006 / 0.000000 |
| S8 | 20.000000 / 5880.000000 | 19.999999 / 5880.000001 | 5900.000006 / 0.000000 |
| S9a | 2950.000000 | 2950.000001 | 2900.000003 |
| S9b | 2950.000000 | 2949.999999 | 3000.000004 |
| S10 | 5900.000000 | 5900.000000 | 5900.000006 |
| S11 | 600.000000 | 600.000341 | 600.000341 |
| S12 | 5900.000000 | 5900.000000 | 5900.000006 |
| S13 | 0.000000 | 0.000000 | 6099.999999 |
| S14 | 0.000000 | 0.000000 | 0.000000 |

S11 (stationary jitter) and S13 (bad initial anchor) remain characterization cases,
not evidence that drift or anchor recovery is solved. S13's 6100→0 per copy accounts
for roughly 18300 m of the full net reduction; it was excluded from Phase 2 ranking.

S7 and S8 now pass only because BOTH date allocation and geometric clipping are
implemented. S8 P010→P011 allocates about 20/30 m, not the legacy 100 m.
The original 52980 m absolute daily discrepancy was mixed R5/R6 evidence.
The independently derived date-only 52380 m absolute / 26190 m moved and 600 m
R6 residual remain historical analytical explanations. No attribution engine or
independent monetary impact is inferred.

## Full run and state reconciliation

Input rows: 3327; drivers: 63; reporting grid: 252 rows over
November 4–7. There are 45 date-labelled rows differing by more than 0.01 m,
including three S13 characterization rows.

Executed legacy total: 263099.457927 m.
Executed corrected total: 235838.090436 m.
Net change (corrected minus legacy): -27261.367491 m.
Absolute date-label difference: 80541.367485 m.
Positive differences: 26639.999997 m;
negative differences: -53901.367488 m.

States: {"accepted": 3246, "accepted_warning": 9, "quarantined": 12, "rejected_duplicate": 39, "rejected_noise": 21}.
These sum to 3327 physical rows. All 12 quarantines remain: three assignable,
nine unassignable. Every S12 copy separately has 81 accepted and four quarantined
rows (one assignable, three unassignable).

Representative traces:
- SYN-S3b-00-D001 wins earliest receipt, then is rejected OFF_ROAD with
  DUPLICATE_CONFLICT retained. P001 is rejected_duplicate; P002 connects from P000.
- SYN-S6c-00-P040 is rejected at approximately 396 km/h from P039.
  P041 still uses P039, yielding approximately 36 km/h over 20 seconds.
- S10 keeps its long-gap chord and marks the arriving accepted record with GAP.
- Rejected observations never become anchors; warnings never restore a rejection.

Both ledgers reconcile against every unrounded driver/day total before writing.
Tests also independently sum serialized allocations per key using the 6-decimal
ledger and 3-decimal report rounding budgets. The legacy segment artifact is
byte-identical to Phase 2. Missing/extra totals, missing decisions, duplicate edges
and a balanced 25 m date transfer fail reconciliation.

CSV values are report precision (3 decimals), JSON ledgers 6 decimals, coordinates
10 decimals. Rounding occurs only at output. Presence flags distinguish missing
calculation keys from explicit zeros. Legacy UTC labels remain visible alongside
corrected UTC+9 labels; this is discrepancy analysis, not normalized settlement.

## Commands and observed outcomes

| Command | Exit | Outcome |
|---|---:|---|
| .venv/bin/python -m pytest -q (entry baseline) | 0 | 184 passed |
| make lint (entry baseline) | 0 | clean |
| .venv/bin/python -m pytest tests --junitxml=.scratch/phase3/full.xml | 0 | 239 passed, 0 failures/errors/skips |
| .venv/bin/python -m pytest tests/unit tests/integration/test_baseline.py -q | 0 | 184 passed |
| .venv/bin/python -m pytest tests/integration/test_corrected.py -q | 0 | 55 passed |
| .venv/bin/python -m pytest tests/integration/test_corrected.py::test_primary_frozen_r5 -q | 0 | 1 passed |
| make lint (final) | 0 | Ruff lint and 26-file formatting check pass |
| compare command below, run1 and run2 | 0 each | reconciled outputs |
| .venv/bin/python scripts/verify_phase3.py --results .scratch/phase3/run1 | 0 | 63 instances and primary pass |
| .venv/bin/python scripts/verify_phase3.py --results .scratch/phase3/run2 | 0 | same |
| diff -r .scratch/phase3/run1 .scratch/phase3/run2 | 0 | byte-identical |

Actual console command (repeat with run2 as output):
```sh
.venv/bin/geo-audit compare --input data/synthetic/SYNTHETIC_gps_pings.csv --roads data/synthetic/roads.geojson --zone data/synthetic/zone.geojson --output .scratch/phase3/run1
```

The integration suite separately runs module invocation under UTC and Pacific/Honolulu
and compares every artifact byte-for-byte. Outputs were copied into results/phase3
only after verification. Scratch logs retain actual command output.
No Linux CI, fresh installation or Phase 4 failure-classification verifier was run.

## Preservation, limitations and scope

Phase 2's manifest still validates every original file against the unchanged Git index.
All 33 protected data, expected-value, historical-result, legacy-source and discovery
files also match in the working tree. The original manifest is not rewritten to hide
authorized source changes; those changes remain separate from its staged snapshot.

No Phase 2 prioritization was changed. No commit, identity change, remote or publication.
Private requirements remain ignored and are absent from staging.

Initial-anchor assumptions, straight-line interpolation, long gaps and eligible
stationary jitter remain documented limitations. Driver compensation and monetary
charges remain unspecified. The exact submission deadline remains unknown.
Phase 4's strict red/green verifier and CI remain deferred by authorization.


## Phase 3 audit remediation — evidence validation

This section supplements the original 239-test execution record; it does not
replace historical evidence or change any baseline figure.

The independent audit demonstrated genuine weaknesses in the QA tool:
NaN, duplicate keys, missing S14 zeros and an unexpected million-metre total
all passed the numeric gate; the writer accepted nonfinite included distance,
fabricated source metadata and allocation to an impossible date. An unterminated
CSV quote escaped the CLI as an uncaught csv.Error.

Corrections:
- verify_phase3.py validates finite totals, uniqueness and the exact expected key
  set established from independent scenario definitions/expectations before building
  its lookup. Every expected corrected zero row is required. The legacy key set
  remains its independently specified UTC dates. Explicitly absent comparison-grid
  keys are distinguished from missing required totals.
- Every comparison row is checked for finite amounts, rounding agreement,
  complete grid membership, presence flags and date-convention labels.
  Existing supplemental primary evidence must exactly match a fresh calculation;
  the verifier now also supports checking an already-populated genuine output.
- report.py validates decision identities against raw source records, accepted
  segment endpoints and timestamps, coordinate identity and source-derived length.
  Fractions must be finite, ordered, nonoverlapping and within [0,1]. Recorded
  allocations must match the actual UTC+9 partitions and overlap with the recorded
  spatial fractions. This checks evidence invariants without rerunning selection,
  noise rejection or polygon intersection as a second billing engine.
- Nonfinite evidence is rejected before output creation; JSON uses allow_nan=False.
  Existing legacy reconciliation remains intact.
- cli.py catches csv.Error explicitly and returns a concise malformed-input error
  with exit 2. Other internal exception types are not broadly suppressed. Parsing
  semantics in io.py were not changed.

### Executed negative and positive regressions

Original four numerical corruptions now exit 1 with nonfinite, duplicate-key or
missing/unexpected-key diagnostics, without PASS or repair. Additional tests reject
incorrect presence flags, missing comparison rows and NaN comparison amounts.

Original three report mutations now raise ValueError before creating output:
NaN included distance; nonexistent ping ID/fabricated timestamp; allocation to
2030-01-01. Further tests reject negative/overlapping/nonfinite fractions,
changed decision identity, nonfinite speed evidence and a balanced 25 m date transfer.

Valid midnight, zero-distance and multiple-midnight segments pass. Both check and
compare reject the malformed CSV with exit 2, no traceback and no output directory.
The unchanged canonical Phase 3 evidence passes in a temporary copy without any
byte changes.

| Command | Exit | Result |
|---|---:|---|
| .venv/bin/python -m pytest -q (before edits) | 0 | 239 passed |
| .venv/bin/python -m pytest tests/integration/test_evidence_validation.py -q | 0 | 22 passed |
| .venv/bin/python -m pytest -q NODE_ID, each new node separately | 0 each | 22 separate passing runs |
| .venv/bin/python -m pytest tests --junitxml=.scratch/p3_remediation/full.xml | 0 | 261 passed, zero failed/errors/skipped |
| make lint | 0 | lint and formatting pass, 27 files |
| compare command below for run1 and run2 | 0 each | full reconciled comparisons |
| .venv/bin/python scripts/verify_phase3.py --results .scratch/p3_remediation/run1 | 0 | 63 instances and primary pass |
| .venv/bin/python scripts/verify_phase3.py --results .scratch/p3_remediation/run2 | 0 | same |
| diff -r .scratch/p3_remediation/run1 .scratch/p3_remediation/run2 | 0 | byte-identical |

Console command:
```sh
.venv/bin/geo-audit compare --input data/synthetic/SYNTHETIC_gps_pings.csv --roads data/synthetic/roads.geojson --zone data/synthetic/zone.geojson --output .scratch/p3_remediation/run1
```

All generated comparison/verification artifacts match their original Phase 3
canonical counterparts byte-for-byte. R5 remains legacy
(100.00000273383924,0) and corrected (50.00000136691962,50.00000136691962).
S7/S8 and all 63 instances retain their prior values. No canonical numeric artifact,
legacy source, scenario multiplicity or expectation was edited.

### Git and preservation

All 49 staged Phase 2 files were checked against the freeze manifest, along with
privacy exclusions and the confirmed repository email. A local baseline commit was
attempted, but the existing gitleaks hook rejected the documentation phrase
'duplicate/missing' as a generic API key. Inspection confirms this is prose, not a
credential. The hook was not disabled, the snapshot was not altered, and no commit
was created. HEAD remains d193a999f0663feeade4801ddc7a2e2ed6dbf4ce.

The Phase 2 index still matches all original manifest hashes; 33 protected files
match in the working tree. The original Phase 3 manifest is retained as the
pre-remediation source snapshot; authorized validation-source changes are recorded
in results/phase3_validation_manifest.json. Original result hashes remain unchanged.
No remote, push, publication, history rewrite or Phase 4 implementation occurred.
