# Phase 2 evidence — audit remediation (SYNTHETIC DATA)

This report supersedes the attribution and diagnostic claims in the original report.
The original report and all prior result files are preserved in
`results/phase2_pre_remediation/`; they contain known audit findings, not current claims.
No corrected calculator or final red/green verifier exists.

## Current verified baseline

The original 3327 rows (3315 structured, 12 quarantined), 63 drivers, 21 scenarios
and uniform multiplicity of three are unchanged. Original analytic expectations,
legacy calculator, legacy totals, segment ledger, quarantine and run metadata are unchanged.
Two fresh runs matched byte-for-byte; their data matched `data/synthetic/`.
Supplemental R5-only evidence is separate and does not change ranking frequencies.

## Audit resolutions

- F1: discovery now exposes every relevant driver/segment conflict, including R6
  alongside R5. The selected-category boolean distinguishes the ranking category
  from other interactions. S7/S8 remain combined integration cases.
- F2: raw chronological and legacy file-order speed pairs are explicitly
  `provisional_anomaly`, named `RAW_PAIR_SPEED_ANOMALY` and
  `LEGACY_RAW_PAIR_SPEED_ANOMALY`. These are not confirmed R2 violations,
  rejection decisions or definitive root-cause evidence. Raw pairs can miss
  consecutive spikes or implicate a valid return observation; road/dedupe checks
  also precede speed validation. Final accepted-anchor state belongs to Phase 3.
  Independent S6b/S6c fixture arithmetic establishes the speed defect:
  418.06/10×3.6=150.5016 and 1100/10×3.6=396; the subsequent accepted-anchor
  leg is 200/20×3.6=36. S6b's raw return is only 78.5016 km/h.
- F3: every driver/UTC-date key reconciles before output. Source edges, IDs,
  timestamps, dates, finite nonnegative distances and inclusion are checked;
  missing/extra keys, duplicate/missing edges and malformed records fail.
  Explicit zero keys for valid input driver/UTC dates remain required.
  The full comparison date grid is deferred to its approved phase.
- F4: ranking compares distance at 0.01 m resolution, then affected driver-days,
  then stable ID. Raw measured values remain unchanged. The 300 m tie puts
  zone endpoint (six days) before file order (three).
- F5: absolute daily discrepancy is not added billable distance. Signed differences,
  positive and negative components and net are retained. No prices, losses,
  driver payments or real-world frequencies are inferred.
- F6: no independent Git freeze preceded original discovery. See provenance below.

## Executed ranking

| Rank | Group | Days | Absolute m | Positive m | Negative m | Net m |
|---:|---|---:|---:|---:|---:|---:|
| 1 | D-R5-UTC-DAY | 12 | 52980.000036 | 26490.000036 | -26490.000000 | 0.000036 |
| 2 | D-R2-SPEED | 6 | 6708.360018 | 6708.360018 | -0.000000 | 6708.360018 |
| 3 | D-R3-DUPLICATE | 9 | 1220.689812 | 1220.689812 | -0.000000 | 1220.689812 |
| 4 | D-R1-OFF-ROAD | 6 | 732.317490 | 732.317490 | -0.000000 | 732.317490 |
| 5 | D-R6-ZONE-ENDPOINT | 6 | 300.000003 | 150.000012 | -149.999991 | 0.000021 |
| 6 | D-R4-FILE-ORDER | 3 | 299.999985 | 299.999985 | -0.000000 | 299.999985 |

The primary remains R5, based on daily reporting error; this is a discrepancy-group
ranking, not an additive causal attribution. R2 has the largest net overcount.
S7/S8 also contain R6. Daily recorded distance affects reporting; driver compensation
has not been specified.

## R5/R6 independent reconciliation

S7's date-only allocation holding legacy endpoint inclusion fixed is (3000,2900):
30 included 100 m segments before midnight and 29 after. S8 is (70,5830):
70 m before midnight, then 30+58×100 after. Correct full-rule vectors remain
(2950,2950) and (20,5880).

Across three copies:
- Observed absolute daily error: 3×(5900+11760)=52980 m.
- Date-only R5 absolute difference: 3×(5800+11660)=52380 m.
- R6 residual in this particular decomposition: 3×(100+100)=600 m.
- R5 distance moved: 3×(2900+5830)=26190 m.
- Full observed positive/negative daily differences: +26490/−26490 m; net 0 m
  analytically (serialization produces a 0.000036 m residual).

This is a small analytical explanation with the endpoint policy held fixed, not a
general attribution engine. The 600 m is already in the observed 52980 m and is not
added again to any impact total. S8 P010→P011 has 50 m in zone, allocated 20/30,
while legacy includes 100 m on November 4.

## Clean primary proof, supplemental only

`tests/expectations/r5_midnight.json` defines E=3000→3100, N=0,
14:59:55Z→15:00:05Z on November 4, 2026. Both endpoints and the whole segment
are in zone; 100 m /10 s=36 km/h. Independent required vector is (50,50).
Executed legacy vector is (100.00000273383924,0), within 0.01 m of (100,0).
`results/phase2/r5_only.json` retains raw rows and the ledger.
Only R5 conflicts are emitted. No corrected result has been executed.
This fixture can anchor the future primary red/green proof; S7/S8 need both fixes.

## Verification commands

| Command | Exit | Result |
|---|---:|---|
| `.venv/bin/python -m pytest -q` before remediation | 0 | 168 passed |
| `.venv/bin/python -m pytest tests --junitxml=.scratch/remediation/full.xml` | 0 | 184 passed, 0 failed/errors/skipped |
| `.venv/bin/python -m pytest tests/unit/test_phase2_remediation.py -q` | 0 | 16 passed |
| `.venv/bin/python -m pytest -q NODE_ID` for each new collected node | 0 each | 16 separate processes, one pass each |
| `.venv/bin/python scripts/verify_r5_fixture.py --output .scratch/remediation/r5_only.json` | 0 | matches supplemental canonical evidence byte-for-byte |
| `make lint` | 0 | Ruff lint and formatting pass |
| `make baseline OUT=.scratch/remediation/run3` | 0 | all analytic legacy vectors pass |
| `make baseline OUT=.scratch/remediation/run4` | 0 | same files and hashes as run3 |

Execution output and individual node commands are in ignored `.scratch/remediation/`.
Regression negative cases pass by rejecting corrupt reports; they are not hidden test
failures. Existing Phase 1 numerical tests and all baseline expectations still pass.
No Linux CI or clean-checkout installation was performed in this remediation.

## Provenance and freeze

Phase 1 HEAD is `d193a999f0663feeade4801ddc7a2e2ed6dbf4ce`; it is unchanged.
The approved private plan already specified absolute driver/day impact, then breadth.
The original Phase 2 files were uncommitted before measurement. Claims in historical
docs about when multiplicity was chosen rest on file timestamps/agent logs, not an
independent versioned freeze; they cannot establish that history conclusively.
Current files demonstrate uniform multiplicity, retained data and analytic expectations.
This remediation changes reports, diagnostics, reconciliation, ranking and tests only.

`results/phase2_freeze.json` records current file hashes and runtime versions.
It is a present snapshot, not proof of earlier chronology. Hash verification detects
later drift; Git commitment remains pending explicit confirmation of author identity.
No remote or publication has been created. Private requirements remain excluded.
