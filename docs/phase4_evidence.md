# Phase 4 evidence — regression proof, reproducibility and CI (SYNTHETIC DATA)

All results below were executed locally on macOS (Python 3.12.12) on 2026-11-12.
**Hosted GitHub Actions has not run.** The repository has no remote.

## 1. Starting state (verified, not assumed)

- HEAD was `18d11d6` (Phase 3) on `cf4e41c` (Phase 2) on `d193a99` (Phase 1).
  Phase 2 and 3 were already committed before this session. Those two commits and
  `.gitleaks.toml` are not described in earlier docs. `docs/phase3_evidence.md` still
  says the commit was blocked.
- `results/phase2_freeze.json`: all 62 hashes match `cf4e41c`. The 9 that differ at
  HEAD are exactly the files changed by the Phase 3 commit. Legacy code, expectations,
  `data/` and `results/phase2/` are unchanged since `cf4e41c`.
- `results/phase3_validation_manifest.json`: 7 files and 15 numeric artifacts match.
- 261 tests passed, excluding an uncommitted draft in `tests/regression/`.
- A fresh `compare` plus `verify_phase3.py` reproduced `results/phase3` byte-for-byte.

## 2. Gitleaks

- Reproduced the original finding: `generic-api-key`, secret `duplicate/missing`,
  `docs/phase2_evidence.md` line 32 ("duplicate/missing edges"). It is prose, so a false positive.
- **The earlier allowlist was too broad.** It was a global `[[allowlists]]` with a
  path. Gitleaks skips a path-matched file before rules run. Synthetic probes in that
  file (`github-pat`, `generic-api-key`) were **not reported**.
- Fix (`6e59896`): the exemption moved onto the `generic-api-key` rule. It requires
  the file *and* the exact secret. With it, all four synthetic probes are reported,
  including two in the exempt file. History scan: no leaks.
- The real global pre-commit hook ran on both commits. A throwaway repo with the new
  config showed the hook blocking a synthetic `ghp_` token in the exempt file
  (exit 1) while allowing the prose (exit 0). No hook was disabled or bypassed.
- The frozen document was not changed.

## 3. Red/green system

- `tests/regression/manifest.json`: 20 named assertions. `tests/regression/conftest.py`
  runs the same assertion for both targets via `GEO_AUDIT_TARGET`.
- The verifier first checks the manifest against `tests/expectations/analytic.json`
  and `r5_midnight.json`. It also recomputes every fixture hash from the data. S11
  and S13 are refused in the billing manifest; they live in
  `tests/integration/test_characterization.py`.
- `scripts/verify_red_green.py` runs pytest twice in fresh subprocesses. Plugin
  autoload is off, `PYTEST_ADDOPTS` is removed, and a per-run UUID is checked in both
  the evidence and JUnit. It validates exit codes, collection, every phase, failure
  type and assertion ID, numeric vectors, raw date keys, and JUnit totals/messages.
- Result: 20 corrected greens; 13 legacy reds (S2b, S3, S3b, S4, S5a, S5c, S6b,
  S6c, S7, S8, S9a, S9b, R5_ONLY) each at its own `*_REQUIRED_DISTANCE` /
  `R5_ONLY_LOCAL_DAY_ALLOCATION` assertion; 7 legacy controls green (S1, S2a, S5b,
  S6a, S10, S12, S14). Per-case numbers are in `red_green/summary.json`.

## 4. Verifier negative tests (`tests/tooling/test_verifier.py`, 47 cases)

There are 33 evidence corruptions, each asserting its rejection message. They cover:
- corrected failure (exit and record);
- legacy unexpected pass;
- wrong assertion ID;
- wrong exception type;
- setup and teardown errors;
- collection exit 2;
- missing results or collection entries;
- duplicate IDs or phases;
- deselection;
- missing or truncated JUnit;
- JUnit skip count;
- missing evidence;
- stale evidence or JUnit run ID;
- invalid fixture hash;
- incorrect legacy value;
- `NaN`/`Infinity` tokens and `"NaN"` strings;
- a missing explicit zero;
- unexpected raw or outcome days;
- skipped and xfailed tests;
- wrong target;
- changed tolerance;
- malformed records.

There are 8 manifest/data cases: oracle drift, legacy drift, wrong red/control
class, fixture hash, tolerance, a characterization case in the manifest, a
duplicate ID, and an edited dataset row.

There are 4 real-subprocess sabotage cases:
- broken corrected calculator, rejected by `exit status: 1`;
- harness ignoring the target, rejected by `wrong evidence target`;
- setup error disguised as a legacy red, rejected by `unexpected setup outcome`;
- conftest import error, rejected by `missing ... evidence`.

The remaining tests are the existing-output case, the genuine-run acceptance, and
the module fixture.

## 5. Demo and reproducibility

`geo-audit demo --output DIR` (or `make demo`) checks prerequisites, then verifies
31 frozen reference hashes. It runs generate → check → discovery → R5 fixture →
compare → numeric verification. Each output must be **byte-identical** to
`data/synthetic`, `results/phase2` and `results/phase3`. It then reconciles row
states (sum = 3327) and the corrected ledger against the totals, and finally runs
the strict red/green verifier. Exit 0 needs every gate. Exit 1 is a failed gate;
exit 2 is a prerequisite failure.

| Run | Exit | Result |
|---|---:|---|
| `make demo` (repo venv) | 0 | DEMO PASS |
| `PYTHONHASHSEED=0 TZ=UTC` vs `PYTHONHASHSEED=987654 TZ=Pacific/Kiritimati` | 0, 0 | data/check/compare/summaries identical |
| Fresh source export (tracked + new files only), new `.venv` from lock, `make demo` | 0 | DEMO PASS, 27 s; package imported from the export |
| CI steps in that export: `make lint`, `pytest tests`, `make verify`, `make demo` | 0 | 334 passed; reference `data/` and `results/` unchanged |

The wheels in the fresh export came from the local pip cache (macOS arm64).

## 6. CI

`.github/workflows/ci.yml` is one job on `ubuntu-24.04` with Python 3.12. Its steps:
1. Locked install.
2. Lint.
3. `pytest tests` (corrected).
4. `make verify`.
5. `make demo`.
6. A check that git status is clean.
7. Evidence upload with `if: always()`.

It has no `continue-on-error` and no `|| true`. `actionlint` 1.7.12 exits 0. The same
commands were run locally (section 5). **Not yet run on GitHub**, so Linux wheel
availability for the pinned versions is unverified.

## 7. Tests

`pytest tests`: 334 passed, 0 failed/errors/skipped.

| Group | Count |
|---|---:|
| Pre-existing | 261 |
| Regression (corrected target) | 20 |
| Characterization | 2 |
| Verifier | 47 |
| Demo | 4 |

`make lint`: exit 0.

## 8. Living documents

This phase appended to `docs/ai_log.md`, `docs/effort.md` and `README.md`. Their
hashes in `results/phase3_validation_manifest.json` (`files`) therefore no longer
match HEAD. The verified earlier versions remain in commit `18d11d6`. The demo guards only the
frozen data and numeric evidence, and those are unchanged.

## 9. Later status (added 2026-11-12, Phase 5A)

- The demo's frozen-hash guard grew from 31 to 42. It now also covers the 11
  archived `results/phase2_pre_remediation/` files. Source files and append-only
  logs are checked against their commits by `scripts/verify_frozen_history.py`.
- Private file names moved from `.gitignore` to local-only `.git/info/exclude`.
