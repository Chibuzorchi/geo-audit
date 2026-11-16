# directive.md — GeoAudit technical handoff

Status: verified locally and on [GitHub Actions](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369334744).
Video walkthrough: see section 14. All data is synthetic. Paths are relative to the repository root.

## 1. Objective

Make per-driver, per-day in-zone distance from GPS pings follow six declared rules.
Then prove the primary defect is gone, with before/after numbers and a regression
check that fails on the old code and passes on the new code.

## 2. Scope

**In scope:**
- A synthetic dataset.
- A deliberately wrong legacy calculation.
- A blind QA checker.
- A corrected calculation.
- Per-driver/day comparison.
- Red/green verification.
- A reproducible demo and one CI workflow.

**Out of scope:**
- Real data.
- Driver pay and monetary rates.
- Restating reports already issued.
- Anchor recovery.
- Stationary-drift filtering.
- Gap interpolation.

## 3. Requirements

| Rule | Requirement |
|---|---|
| R1 | Ignore a ping more than 100 m from the road. Exactly 100 m is kept. |
| R2 | Ignore a ping implying more than 150 km/h from the last accepted ping. Exactly 150 km/h is kept. |
| R3 | Count the same driver and device instant once. |
| R4 | Place pings by their own timestamp. |
| R5 | Report per calendar day at fixed UTC+9. Midnight is 15:00 UTC. |
| R6 | Count only distance inside the zone. The boundary counts. |

Assumptions are listed in `intent.md` and `README.md`.

## 4. Completion criteria

All criteria were met locally on 2026-11-12/13.

- [x] At least 2,000 synthetic pings with all fault types: 3,327 rows (`data/synthetic/`).
- [x] At least three measured problems, ranked, with one chosen first: six defects; R5 chosen (`intent.md`, `results/phase2/findings.md`).
- [x] A runnable QA tool that makes the problem visible: `geo-audit check` → `results/phase2/decision_conflicts.json`.
- [x] Primary fix shown per driver and day: `results/phase3/r5_only/driver_day.csv`, `results/phase3/driver_day.csv`.
- [x] Regression fails on legacy and passes on corrected: `make verify`, with 13 reds, 7 controls and 20 greens.
- [x] Noise, duplicates, late pings, the UTC+9 cut and the zone boundary are all covered by named assertions.
- [x] [Hosted CI passed](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369334744) on Ubuntu.

## 5. QA tool and how to run it

Requirements: Python 3.12, `make`, POSIX. Then:

```sh
make demo        # install from lock, regenerate, compare to references, red/green proof
```

It exits 0 only if every check passes. It prints `DEMO PASS: ...` and writes to `.scratch/demo/`.

| Command | Purpose |
|---|---|
| `geo-audit check` | Writes `findings.json` (data conditions), `decision_conflicts.json` (legacy decisions that break a rule), the legacy ledger and the quarantine list. |
| `geo-audit compare` | Writes the before/after `driver_day.csv`, per-row decisions and both ledgers. |
| `make test` | All tests. |
| `make lint` | Ruff check and format check. |
| `make verify` | Red/green proof only. |
| `python scripts/verify_frozen_history.py` | Checks freeze manifests against their commits. Needs a Git clone. |

## 6. Dataset provenance

`src/geo_audit_synthetic/generator.py` builds the dataset deterministically. There is
no randomness and no wall-clock time.
- **Shape:** 21 hand-defined scenarios × 3 copies = 63 drivers, each copy shifted by one day.
- **Fault labels** are in `data/synthetic/fault_labels.json`. The checker and the calculators never read them.
- **Expected values** are literal and hand-derived, in `tests/expectations/analytic.json` and `tests/expectations/r5_midnight.json`. They are documented in `docs/scenarios.md`.

## 7. Legacy and corrected implementations

- **Legacy** (`src/geo_audit/calc_legacy.py`, frozen):
  - joins rows in file order;
  - has no dedupe and no noise filter;
  - counts a whole segment if its end point is in the zone;
  - dates the segment by the end point's UTC date.
- **Corrected** (`src/geo_audit/calc_corrected.py`), in order:
  1. Quarantine invalid rows and conflicting IDs.
  2. Pick one duplicate survivor: earliest received, then lowest ID.
  3. Sort by device time.
  4. Apply the road filter.
  5. Apply the speed filter against the last accepted ping.
  6. Clip each segment to the zone.
  7. Split time at UTC+9 midnight.

Each row ends in exactly one state (`results/phase3/summary.json`):

| State | Rows |
|---|---:|
| accepted | 3,246 |
| accepted with warning | 9 |
| quarantined | 12 |
| duplicate rejected | 39 |
| noise rejected | 21 |
| **Total** | **3,327** |

## 8. Primary before/after evidence (R5)

Isolated fixture: one 100 m segment fully inside the zone, from 14:59:55Z to 15:00:05Z.
Source: `results/phase3/r5_only/driver_day.csv`.

| UTC+9 day | Legacy m | Corrected m | Independent expectation m |
|---|---:|---:|---:|
| 2026-11-04 | 100.000 | 50.000 | 50 |
| 2026-11-05 | 0.000 | 50.000 | 50 |

The total is unchanged. The fix moves distance to the correct day.

Full-trip effect, from `results/phase3/driver_day.csv` (these figures include the R6 fix):
- **SYN-S7-00:** 5,900 / 0 → 2,950 / 2,950.
- **SYN-S8-00:** 5,900 / 0 → 20 / 5,880.

## 9. Regression verification

`scripts/verify_red_green.py` runs `tests/regression/test_billing.py` twice, in fresh
subprocesses: once with `GEO_AUDIT_TARGET=corrected` and once with `=legacy`.

It accepts a run only if:
- corrected exits 0;
- legacy exits exactly 1;
- every case in `tests/regression/manifest.json` was collected and executed once;
- there are no skips, xfails or setup errors;
- every legacy red failed at its own assertion ID, with the expected legacy number;
- every corrected number equals the independent expectation.

The manifest itself is checked against the expectation files. Fixture hashes are
recomputed from the data. 47 negative tests (`tests/tooling/test_verifier.py`)
prove that corrupted, stale or sabotaged evidence is rejected.

## 10. CI status

`.github/workflows/ci.yml` runs on ubuntu-24.04 with Python 3.12:
1. Locked install.
2. Lint.
3. `pytest tests`.
4. `make verify`.
5. `make demo`.
6. Clean `git status` check.
7. Evidence upload, also on failure.

It has no `continue-on-error`.

**[Hosted CI passed](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369334744).**

Linux wheels exist for every pinned version. They bundle PROJ 9.8.1 and GEOS 3.14.1,
the same as the macOS references. Linux x86_64 verified 29 of 31 reference files
byte-for-byte; two supplemental unrounded JSON reports agree at six decimal places.
See [Phase 5B evidence](https://github.com/Chibuzorchi/geo-audit/blob/main/docs/phase5b_evidence.md) for the original failure and correction.

## 11. Reproduction

Local results (macOS arm64, Python 3.12.12):

| Command | Result |
|---|---|
| `make lint` | 0 |
| `make test` | 343 passed |
| `make verify` | PASS |
| `make demo` | PASS |
| `make demo` from a fresh clone with a new `.venv` | PASS |

Regeneration is byte-identical across hash seeds and host timezones. See
`docs/phase4_evidence.md` and `docs/phase5_evidence.md`.

## 12. Unresolved limitations

- A bad first anchor (S13).
- Stationary jitter (S11).
- Long gaps counted as a straight chord.
- No restatement of reports already issued.
- No pay model.

## 13. AI involvement and my review

AI assistants wrote most of the code, tests and documents. I set the requirements
and plan, and used Codex as an independent reviewer of the implementing agent. I
reviewed its findings, directed the fixes and required evidence before each next phase.

Seven AI mistakes were found and corrected. Some came from the audits I commissioned;
the implementing agent found the rest. For example:
- A ranking that credited 600 m of R6 error to R5 (audit).
- A speed diagnostic that compared raw neighbouring pings, not the last accepted ping (audit).
- A verifier that accepted `NaN` and missing keys (audit).
- A verifier draft that rejected its own valid run (agent).

The full table, with how each was found and the test that proves it, is in
[Author review summary](https://github.com/Chibuzorchi/geo-audit/blob/main/docs/ai_log.md#author-review-summary-first-person).
Numerical expectations were derived by hand from geometry and rechecked with plain arithmetic.

**Effort:** about 24 hours of my own active work, 2026-11-12 to 2026-11-16
([breakdown](https://github.com/Chibuzorchi/geo-audit/blob/main/docs/effort.md#actual-author-effort)).

## 14. Links

| Item | Link |
|---|---|
| Repository | [Chibuzorchi/geo-audit](https://github.com/Chibuzorchi/geo-audit) |
| Tool | [Checker](https://github.com/Chibuzorchi/geo-audit/blob/main/src/geo_audit/checker.py), `geo-audit check` |
| Dataset | [Synthetic data](https://github.com/Chibuzorchi/geo-audit/tree/main/data/synthetic) |
| Fix | [Corrected calculation](https://github.com/Chibuzorchi/geo-audit/blob/main/src/geo_audit/calc_corrected.py) |
| Regression check | [Verifier](https://github.com/Chibuzorchi/geo-audit/blob/main/scripts/verify_red_green.py), [regressions](https://github.com/Chibuzorchi/geo-audit/tree/main/tests/regression) |
| Results | [Before/after per driver and day](https://github.com/Chibuzorchi/geo-audit/blob/main/results/phase3/driver_day.csv), [isolated R5 fix](https://github.com/Chibuzorchi/geo-audit/blob/main/results/phase3/r5_only/driver_day.csv), [ranking](https://github.com/Chibuzorchi/geo-audit/blob/main/results/phase2/findings.md) |
| Regression results | `make verify` output; [CI run 43369334744](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369334744) and its `geo-audit-evidence` artifact |
| Video walkthrough | LOOM_URL_HERE ([script](https://github.com/Chibuzorchi/geo-audit/blob/main/docs/demo_script.md)) |
