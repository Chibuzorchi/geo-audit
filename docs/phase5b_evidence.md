# Phase 5B — first hosted Ubuntu verification

Repository: https://github.com/Chibuzorchi/geo-audit. It was not yet public during
this phase; it is public now, and the default branch has since been renamed `main`.
The existing default branch was retained during this phase. Initial HEAD was
`8e29cf0b4af4f2292be85c85d909038a4999776f`; inspection found seven commits,
not the eight anticipated by the request. All seven remain intact.

## Local release and security

Before repository creation, `make lint`, `make test` (334 passed), `make verify`
(20 corrected greens / 13 intended legacy reds / seven controls), and `make demo`
passed with exit 0. Historical verification matched 62 Phase 2 and 22 Phase 3
hashes against their commits. Full-history Gitleaks found no leaks. Review of
128 unique historical blobs found only harmless private filenames in old ignore
rules, with no private source material, credentials or employer content.
The actual pre-commit hook passed; it was not disabled or bypassed.
Identity remained the configured personal Git identity. No history was rewritten.

## First hosted failure and minimal correction

[Run 43368453702](https://github.com/Chibuzorchi/geo-audit/actions/runs/43368453702)
on the initial HEAD failed: 330 passed, four failed. Installation and lint passed.
A latitude round trip produced 37.70000000000001 at the supported upper edge.
The raw R5 length differed from macOS by approximately 5.8e-11 m. Exact equality
in the primary test, numerical verifier and supplemental report comparison caused
three further failures. The runner was not changed to conceal the failures.

Commit `bf9709cc1af70e6cd9bc61b65e316a463dc47968`:

- Limits inverse-projection edge normalization to four ULPs; raw coordinate input
  validation remains strict, and points farther outside are rejected.
- Compares the primary raw distance with a 1e-6 m absolute bound (no relative tolerance).
- Compares only `results/phase2/r5_only.json` and
  `results/phase3/numerical_verification.json` at existing serialization precision:
  six decimal places for measurements. Other regenerated files remain byte-compared.
- Preserves historical raw values rather than rewriting the existing verifier output.
- Adds nine tests for edge roundoff, larger differences, invalid JSON numbers and
  changed evidence structure. All 343 local tests passed; lint, verify, demo and
  historical checks returned 0. No independent expectation, calculator rule,
  dataset frequency or canonical result was changed.

## Successful hosted execution

[Run 43369010547](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369010547)
verified commit `bf9709cc1af70e6cd9bc61b65e316a463dc47968` with conclusion **success**.
Runner: Ubuntu 24.04.5 x64, image ubuntu-24.04 version 20261101.360.1,
CPython 3.12.16. Locked install, Ruff lint/format, full tests, strict regression,
demo regeneration, evidence integrity, clean-tree check and upload all succeeded.
Full suite: **343 passed, zero failed/errors/skipped**, 42.404 seconds in JUnit.
Both standalone and demo regression runs validated 20 corrected greens,
13 legacy failures at designated numeric assertions and seven legacy controls.

Commands used to inspect the actual hosted output:

```sh
gh run view 43369010547 --repo Chibuzorchi/geo-audit --log
gh run download 43369010547 --repo Chibuzorchi/geo-audit \
  --name geo-audit-evidence --dir .scratch/phase5b/linux-artifacts
```

Downloaded JUnit and both structured regression evidence sets were independently
revalidated using the strict validator and the unchanged local manifest. Fresh
Linux files were compared against the local frozen references:

| Group | Files verified | Byte-identical |
|---|---:|---:|
| Synthetic data | 6 | 6 |
| Baseline/check evidence | 10 | 9 |
| Corrected comparison | 8 | 7 |
| Isolated R5 comparison | 7 | 7 |

The two differences are exclusively supplemental unrounded floats and agree at
the documented precision. All 42 immutable reference hashes remain exact.
All 63 scenario instances passed independent numerical verification. The R5
raw Linux result is legacy [100.00000273378103, 0] and corrected
[50.000001366890515, 50.000001366890515], within the unchanged 0.01 m fixture bound.
The 3,327 states reconcile (3,246 accepted, nine warnings, 39 duplicates,
21 rejected noise, 12 quarantines); all 252 driver/date rows reconcile.
Legacy total 263,099.457927 m and corrected total 235,838.090436 m are unchanged.

Artifact: `geo-audit-evidence`, ID 14011394186, 783538 bytes.
GitHub archive SHA-256:
`b4783f058f01f37f66b23f8c594572a31dfe9bd49cfea7f39ee181546e73e7b5`.
Contains full-suite JUnit, two red/green evidence sets and logs, generated input,
checker output, legacy/corrected ledgers, decisions, comparison, numerical
verification and demo summary. The initial failed-run artifact/logs remain on
GitHub; local inspection copies are ignored temporary evidence.

This records the successful code run. The subsequent documentation commit runs
the same workflow again; its final SHA and run are recorded in the execution
handoff, avoiding a self-referential documentation commit. Nothing has been made
public, no Loom has been created and no assessment has been submitted.
