# Phase 5A evidence — release preparation (SYNTHETIC DATA)

Executed locally on macOS arm64, Python 3.12.12, 2026-11-12 (UTC).
Nothing was published. There is no remote. Hosted CI has not run.

## 1. Gates

| Command | Exit | Result |
|---|---:|---|
| `make lint` | 0 | Ruff check and format check clean |
| `make test` | 0 | 334 passed, 0 skipped |
| `make verify` | 0 | 20 corrected greens, 13 legacy reds, 7 controls |
| `make demo` | 0 | 42 frozen hashes; byte-identical regeneration; red/green PASS |
| `python scripts/verify_frozen_history.py` | 0 | 62 Phase 2 and 22 Phase 3 hashes match their commits |
| Fresh export (tracked + new files, no `.venv`): `make demo`, `pytest tests` | 0 | DEMO PASS; 334 passed |

## 2. Frozen evidence: what is protected, and how

`results/phase2_freeze.json` has 62 entries:

| Group | Files |
|---|---:|
| Source, docs and config | 35 |
| `data/` | 6 |
| `results/phase2/` | 10 |
| `results/phase2_pre_remediation/` | 11 |

- **Immutable calculation evidence** (`data/`, `results/`): the demo checks the hashes
  on every run. Phase 4 guarded 31 of these: 6 `data/`, 10 `results/phase2/` and
  15 Phase 3 numeric files. The 11 archived pre-remediation files were not covered.
  They are now, giving **42**.
- **Source and documents** are allowed to evolve. `scripts/verify_frozen_history.py`
  confirms that every manifest entry equals the blob at its own commit (`cf4e41c`, `18d11d6`).
  It confirms `docs/ai_log.md` and `docs/effort.md` were only appended to, and lists
  the other evolved files.
- **Negative checks** in a scratch clone:
  - an edited pre-remediation file fails with `immutable evidence changed`;
  - a rewritten `effort.md` fails with `log was rewritten, not appended`.
- **Stale status lines** in `docs/phase3_evidence.md` ("no commit was created") and
  `docs/phase4_evidence.md` now carry dated "Later status" notes. The original text is unchanged.

## 3. Publication-safety audit

- **Scope:** every tracked file was searched for private context, employer names,
  credentials, home paths and hiring terms. The patches of all commits were searched too.
- **Changes made:**
  - `.gitignore` no longer names the private planning or application files.
    They are now ignored through local-only `.git/info/exclude`. `git check-ignore`
    confirms they are still ignored.
  - The docstring of `scripts/verify_red_green.py` no longer cites a non-public plan section.
- **Left as is:**
  - "plan section" comments in two hash-frozen files: `scripts/discover_baseline.py`
    and `tests/unit/test_legacy_checker.py`.
  - The word "assessment" in older `docs/effort.md` entries. That log is append-only history.
- **Still in Git history:**
  - The private file names in the Phase 1 `.gitignore`.
  - One Phase 4 AI-log line, fixed in a later commit.
  - Removing them needs a history rewrite or a fresh-history export. That is the author's decision.

## 4. Gitleaks

- **Config:** the exemption sits on the `generic-api-key` rule only, and needs both the
  file `docs/phase2_evidence.md` and the exact secret `duplicate/missing`.
- **Probes:** with the repo config, all 4 synthetic probes are reported
  (`aws-access-token`, `github-pat`, and `generic-api-key` ×2), including 2 in the exempt file.
- **Scans:** `gitleaks git` reports no leaks. A scan of the working directory reports
  17 findings, all inside ignored `.scratch/`: synthetic probes, and copies of the doc
  at other paths.

## 5. Linux readiness (not executed)

- `pip download --only-binary=:all: --platform manylinux… --python-version 3.12 -r requirements.lock`
  resolved a Linux x86_64 wheel for all 13 pins.
- The Linux pyproj and shapely wheels bundle PROJ 9.8.1 and GEOS 3.14.1, the same as
  the macOS environment that made the references.
- The Docker daemon was not running, so no Linux execution was attempted.
- **Risk:** x86_64 floating-point differences could change a last rounded digit. That
  would break the demo's byte-for-byte comparison on CI.
- **Narrowest fix if that happens:** run the workflow on `macos-14` (arm64), which
  matches the reference platform. Do not loosen the comparison or the lock.
