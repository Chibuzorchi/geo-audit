# Phase 2 evidence — baseline and defect discovery (SYNTHETIC DATA)

All numbers below come from executed commands on 2026-11-12. Canonical outputs
live in `data/synthetic/` and `results/phase2/`. Regenerate with `make baseline`.
No corrected calculator exists at this stage.

## 1. Phase 1 foundation

- Commit `d193a999f0663feeade4801ddc7a2e2ed6dbf4ce`, 21 files. It already existed
  when this session started. This session did not create it.
- `git archive HEAD` extracted to a scratch directory, then that tree's `tests/unit` ran
  with `PYTHONPATH` set to its own `src`: **122 passed**, exit 0.
- `git grep` of HEAD for private-planning, employer, application and home-path strings
  found only the three `.gitignore` exclusion lines. No remote is configured.

## 2. Commands and exit codes

| Command | Exit | Result |
|---|---:|---|
| `make baseline OUT=.scratch/phase2-ref` | 0 | generate → check → discover; legacy gate PASS |
| `make baseline OUT=.scratch/phase2-rerun`, then `diff -r` against ref | 0 | byte-identical |
| `TZ=Pacific/Kiritimati make baseline` + `diff -r` | 0 | byte-identical |
| `.venv/bin/python -m pytest tests --junitxml=.scratch/phase2/full.xml` | 0 | 168 tests, 0 failures, 0 errors, 0 skipped |
| Phase 1 unit files only (`test_geo`, `test_io_cli`, `test_time_rules`) | 0 | 122 passed |
| Phase 2 files (`test_legacy_checker`, `tests/integration`) | 0 | 46 passed |
| `make lint` | 0 | Ruff check and format check clean |
| `geo-audit compare` / `geo-audit demo` | 2 | unavailable in Phase 2 |
| `geo-audit generate` into a nonempty directory | 2 | refused |
| `geo-audit check` with missing input file | 2 | error |
| `geo-audit check` on all-quarantined CSV | 2 | `NO_USABLE_DATA` |
| `geo-audit check --gate` on the synthetic dataset | 1 | findings present |

## 3. Dataset

From `data/synthetic/manifest.json`: 3327 rows, of which 3315 are structured
and 12 are malformed on purpose. Version `analytic-v1`, seed 0, 21 scenarios × 3 copies,
so 63 synthetic drivers. Copy *n* shifts all times by *n* days. All rows carry
`is_synthetic=true`, and the file is named `SYNTHETIC_gps_pings.csv`. Raw input,
`fault_labels.json` and `instances.json` are separate files. Expected outcomes
are in `tests/expectations/analytic.json`, which the generator never writes.

Scenario multiplicity is uniform (3 each), and it was fixed before this
session's measurements. The generator file is unchanged since 15:01 UTC. Frequency is synthetic and is not a prevalence claim.

## 4. Legacy calculation

`discover_baseline.py` first gates every legacy driver/day total against the
literal *legacy* expectation vector, using a 0.01 m tolerance. It also rejects
any nonzero legacy key outside the expectation keys. The gate passed for all 63
instances. The per-scenario test `test_analytic_legacy` asserts the same values.

## 5. Measured discrepancies and ranking

Discovery stdout, verbatim:

```
[
  {"rank": 1, "defect": "D-R5-UTC-DAY",       "driver_days": 12, "absolute_m": 52980.000036, "net_m": 3.6e-05},
  {"rank": 2, "defect": "D-R2-SPEED",         "driver_days": 6,  "absolute_m": 6708.360018,  "net_m": 6708.360018},
  {"rank": 3, "defect": "D-R3-DUPLICATE",     "driver_days": 9,  "absolute_m": 1220.689812,  "net_m": 1220.689812},
  {"rank": 4, "defect": "D-R1-OFF-ROAD",      "driver_days": 6,  "absolute_m": 732.31749,    "net_m": 732.31749},
  {"rank": 5, "defect": "D-R6-ZONE-ENDPOINT", "driver_days": 6,  "absolute_m": 300.000003,   "net_m": 2.1e-05},
  {"rank": 6, "defect": "D-R4-FILE-ORDER",    "driver_days": 3,  "absolute_m": 299.999985,   "net_m": 299.999985}
]
```

(Whitespace compacted; values unchanged.) Per-driver/day rows, segment IDs,
rows, timestamps and coordinates are in `results/phase2/findings.md` and
`results/phase2/discovery.json`. Measurement classes: 42 discrepancy, 21
control, and 6 characterization driver-days (S11/S13).

How each was found: the blind checker (`inspect` + `audit_legacy`) flagged a
segment decision that contradicts one rule. The post-run comparison then measured the driver/day
difference against the independent expectation. The script refuses any
discrepancy that has no matching checker decision evidence. None were refused.

Flags without discrepancy are reported separately. Example: S2a's 30 exact-duplicate
segments add 0 m, and S1's entry/exit endpoint errors cancel.

## 6. Provisional primary problem — selected before any correction

**D-R5-UTC-DAY: distance is dated by the end point's UTC date instead of the UTC+9 report day.**

- Ranked first by the plan §6 metric (absolute driver/day discrepancy, then
  driver-day count). It is the largest single measured error.
- Every affected driver-day is wrong, in both directions. Net totals over two days balance.
  So advertisers are billed the right metres on the wrong report day. Each driver's daily
  recorded distance is wrong on both days.
- Root cause is one decision visible in every ledger row: `date_basis="UTC endpoint"`.
  It is reproducible, and the S7/S8 day vectors are independent literals.
- Trade-off for the reviewer: D-R2-SPEED is the largest *net overcount*.
  It would rank first if the metric were net advertiser overbilling. The
  magnitude of D-R5 also reflects S7/S8 placing whole trips after midnight.

This selection is recorded here and in `results/phase2/discovery.json` and is not
to be rewritten later.

## 7. Separation checks

- Generator imports no `geo_audit` module (AST test).
- Checker imports only `geo`, `rules`, `timecut`, `collections` and `shapely`.
  It never calls `open` (AST test). It runs with `open` patched to fail (integration test).
- The checker emits only `condition`, `rule_violation` and `decision_conflict`.
  It never emits expected or corrected values, or driver/day totals.
- Labels are compared with checker output only after the run (`test_post_run_labels_match_blind_checker`).
- Expectation literals are rechecked with plain `math` (`test_expectation_literals_match_independent_arithmetic`).

## 8. Deviations and limitations

- Ranking groups isolated scenarios into six root-cause defects. Per-scenario
  figures are kept in `by_scenario`. S7 and S8 share one cause.
- The expectations file is `tests/expectations/analytic.json`, not `tests/expected_outcomes.json` as the plan tree names it.
- `check` writes the legacy ledger and totals, and `make baseline` runs the
  post-run discovery script. No new public CLI command was added.
- `R2_PAIR` uses raw adjacent chronological pairs, not the last-accepted anchor (A2).
  It is a condition, not a rejection decision.
- An earlier assistant session drafted the generator, legacy calculator,
  expectations and a test asserting `primary == "S8"`. This session replaced that
  assertion with ranking invariants. The selection is per defect, not per scenario.
