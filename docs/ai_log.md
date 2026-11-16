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


## Phase 3 — corrected calculation

The assistant implemented the corrected calculation, ID normalization/selection,
accepted-anchor state, reporting reconciliation, compare command and 55 focused tests.
It first executed the isolated midnight allocation primitive, then the complete
pipeline. The original Phase 2 checker flags were not used as acceptance decisions.
Independent literal expectations and elementary fraction/speed arithmetic verified
the outputs; no corrected code computed its own expected answers.

All 239 tests passed, including the retained 184-case suite. No failing test or
invented AI mistake is claimed in this session. The obsolete assertion that compare
was unavailable was updated because activation is explicitly authorized.
Ruff reformatted new code. Two comparison runs matched byte-for-byte.
The assistant retained S11/S13 as characterization and did not attribute the total
distance reduction solely to R5. Human independent Phase 3 review remains pending.


## Phase 3 audit remediation — testing the QA tool

The user supplied independently reproduced F1–F3 findings. The assistant corrected
the verifier's NaN/duplicate/missing/extra-key acceptance, strengthened source and
spatial/time allocation integrity, and handled csv.Error specifically at the CLI.
It added 22 focused cases, ran each separately, and executed the 261-test full suite.
All tests passed; the first lint passes corrected import ordering, not product logic.

The audit's vulnerabilities are real failures of the earlier AI-authored evidence
validation. This session did not invent additional failed implementations or human
verification. Fresh output matched canonical results byte-for-byte. A commit attempt
was stopped by a gitleaks false positive on documentation prose; no hook bypass,
staging change or commit occurred. Independent review of the remediation is pending.

## Phase 4 — 2026-11-12

An earlier session left an uncommitted draft: `tests/regression/` and
`scripts/verify_red_green.py`. This session's assistant:

- Ran the draft verifier on a genuine run. It **failed its own valid evidence**: it
  expected the JUnit message to be the bare assertion ID, but pytest writes
  `conftest.BillingMismatch: <ID>`. Fixed to an exact match.
- Found the draft could not name a setup failure. Setup errors skip the call phase,
  so it reported only "missing phases". Setup/teardown/xfail checks now run first.
- Added a manifest-versus-literal check and an independent fixture hash recompute.
  The draft trusted the manifest as its own oracle.
- Found the committed gitleaks allowlist exempted the whole file
  (`docs/phase2_evidence.md`), not one token. Synthetic probes proved it. Rescoped to one rule.
- Its own test drafts had four bugs, all fixed in tests:
  - a keyword collision;
  - an `Infinity` probe aimed at a value absent from corrected evidence;
  - a "legacy fixed" sabotage that actually caused a setup error;
  - a wrong ledger field name (`reporting_date` vs `report_date`) in the demo.
- Removed a glob for private planning-file names that it had written into a public test.

Historical Phase 2/3 findings and expectations were not modified. Human review pending.

## Phase 5A — release preparation, 2026-11-12 (UTC)

The assistant rewrote `README.md` for reviewers. It drafted `intent.md`,
`directive.md` and `docs/demo_script.md` from canonical artifacts only. It also
added `scripts/verify_frozen_history.py`, and widened the demo's frozen-hash guard
to the 11 archived pre-remediation files that were not covered before.

Corrected during drafting:
- **An unsupported claim.** Its first `intent.md` said a "runtime file-open trace" proved the
  checker was blind. That trace existed only in an earlier audit's scratch output, not in
  committed evidence. It now cites `test_checker_blind_and_specific`.
- **Privacy.** Private file names moved from `.gitignore` to local `.git/info/exclude`.
  A "plan section 7" reference to a non-public document was removed from a non-frozen
  script. Frozen files were left unchanged.

## Phase 5B — first hosted Linux run and correction

The first private Ubuntu run (43368453702) executed 334 tests: 330 passed,
four failed. AI inspected the actual logs: inverse projection escaped the upper
latitude bound by one floating-point step, and exact comparisons rejected R5 raw
float differences of approximately 5.8e-11 m. No billing expectation changed.
The correction bounds inverse-only envelope roundoff to four ULPs, retains strict
raw-coordinate validation, and compares two supplemental unrounded JSON reports
at the existing six-decimal serialization precision. Ordinary artifacts remain
byte-compared and every frozen file remains hash-checked. Existing evidence is
validated without rewriting its historical raw floats. Nine focused tests cover
the inverse guard and rejection of larger/nonfinite/schema differences.
Local lint, 343 tests, strict red/green and demo passed before the next push.
Hosted rerun results are recorded separately; local success is not hosted success.

The corrected Ubuntu run 43369010547 succeeded with 343 tests. AI downloaded its
artifact, revalidated both structured red/green runs and checked all 31 regenerated
reference files (29 byte-identical; two supplemental raw-float reports equal at
serialization precision). All 63 scenarios, 3,327 states and 252 driver/date rows
reconciled. README and directive now distinguish verified private hosted access
from pending public release. No human verification or public accessibility is claimed.

## Phase 5C — final documentation review

The assistant aligned intent, directive, README and recording narration with
successful private Ubuntu run 43369334744. It removed unsupported claims of
personal execution of every audit and corrected provisional speed-diagnostic
wording. The script uses the recorded NaN/key-validation failure as an AI-assisted
engineering mistake. Historical failures and canonical artifacts were preserved.
Human effort remains unknown. The branch migration is a recommendation only;
no rename, visibility change, recording, submission or push is part of this phase.

Phase 5C checks: `make lint` passed; `make test` reported 343 passed with no
failures or skips; `make verify` confirmed 20 greens, 13 intended reds and seven
controls. Historical verification matched 62 Phase 2 and 22 Phase 3 hashes.
Relative Markdown links in the four final documents resolve to tracked files.
The script contains 425 spoken words (about 3.54 minutes at 120 words/minute),
not a timed human rehearsal. Canonical R5, S7/S8, state counts and S13 contribution
were cross-checked. Full-history Gitleaks passed before the local documentation
commit. No new hosted CI run is claimed for these unpushed documentation changes.

## Author review summary (first person)

The entries above are the AI assistants' own session logs. They stay unchanged
because this log is append-only. This section is my own account, added on 2026-11-16.

**What AI produced.** AI assistants wrote most of the code, tests and documents.
I set the requirements, constraints and plan. I didn't trust that output on its
own, so I had a second AI tool (Codex) audit the implementing agent's work. I
reproduced its findings, decided the fixes and required evidence before each next phase.

**What went wrong and how it was corrected.** I did not personally discover every
issue. The "How it was found" column says who did.

| Mistake | How it was found | Fix | Proof |
|---|---|---|---|
| Ranking credited 600 m of R6 zone error to R5 | Codex audit (Phase 2 F1–F6). I reproduced the finding and decided the fix. | Reconciled R5/R6 with numbers; proved R5 on an isolated segment | `tests/unit/test_phase2_remediation.py::test_r5_only_midnight_literal_vectors`, `::test_combined_conflicts_visible_and_r5_reconciles`; `results/phase3/r5_only/driver_day.csv` |
| Speed diagnostic compared raw neighbouring pings, not the last accepted ping | Same audit. I reproduced the finding and decided the fix. This was a diagnostic issue, not a wrong corrected total. | Diagnostic marked provisional; the corrected calculator checks speed against the last accepted ping | `test_phase2_remediation.py::test_speed_anomalies_never_assert_acceptance`, `::test_s6b_return_is_not_speed_rejection`; `tests/integration/test_corrected.py::test_offroad_precedes_speed_and_does_not_anchor` |
| Verifier accepted NaN, duplicate, missing or extra keys, so it could report a false pass | Second Codex audit (Phase 3 F1–F3). I reproduced the finding and decided the fix. | Checks finite values and the exact key set before comparing numbers | `tests/integration/test_evidence_validation.py::test_verifier_rejects_corrupt_evidence` |
| Verifier draft rejected its own valid run | Implementing agent, Phase 4 | Matches pytest's real message, `conftest.BillingMismatch: <ID>` | `scripts/verify_red_green.py`; `tests/tooling/test_verifier.py::test_genuine_evidence_is_accepted` |
| Coordinate rounding lost about 0.1 m | Implementing agent, Phase 2 | Coordinates serialize at 10 dp, not 6 | `src/geo_audit/report.py` |
| Gitleaks allowlist exempted a whole file | Implementing agent, Phase 4 | Narrowed to one rule and one token | `.gitleaks.toml` |
| Checker could not explain why totals were wrong | Implementing agent, Phase 2 | Added segment-level `decision_conflict` evidence | `results/phase2/decision_conflicts.json`; `tests/unit/test_legacy_checker.py::test_checker_flags_rule_and_decision` |

**Decisions I made.** This is my own account. Some of it also appears in the plan,
phase evidence and entries above.
- I rejected assuming S8 must rank first. Defects had to be grouped and ranked by
  measured discrepancy.
- I required independent numerical expectations. No calculator may produce its own answer.
- I kept implementation and review separate: a second AI tool audited the first.
- I kept fixes inside the approved plan. No extra features or architecture changes.
- I rejected counting crashes, missing tests or setup errors as valid regression reds.
- I had unsupported claims removed, including claims about evidence that was not preserved.
- I required historical numbers to stay intact, not be silently rewritten.
- I required a real hosted CI run, not just local test passes.

**How I verified the corrections.** For each fix, I checked the new tests and the
updated evidence before approving the next phase. I also checked the hosted CI result.
