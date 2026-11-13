# GeoAudit

GeoAudit checks how GPS pings become billed distance, finds where that goes wrong,
and proves a fix with numbers. It is an independent portfolio project. All data is
**synthetic**; there is no real customer, driver or billing incident behind it.

## The problem

Imagine you pay by the kilometre driven inside a zone, reported per day. Raw phone
GPS is messy:
- noisy points far off the road;
- impossible speed jumps;
- duplicated or late pings;
- trips that cross the zone edge or midnight.

A naive calculation joins pings in file order, so each of these turns into wrong
distance, on the wrong day.

GeoAudit applies six rules:

| Rule | Requirement |
|---|---|
| R1 | Ignore pings more than 100 m from the road. |
| R2 | Ignore pings implying more than 150 km/h. |
| R3 | Count the same driver and timestamp once. |
| R4 | Order pings by their own timestamp, even if they arrive late. |
| R5 | Cut the daily report at 00:00 UTC+9, which is 15:00 UTC. |
| R6 | Count only distance travelled inside the zone. |

## Run it

Requirements: Python 3.12 (`python3.12` on `PATH`), `make` and a POSIX shell.
Internet or a pip cache is needed for the first install.

```sh
make demo
```

This builds `.venv` from `requirements.lock`, then:
1. Regenerates the dataset.
2. Runs the checker, the legacy calculation and the corrected calculation.
3. Requires outputs to match committed references: byte-for-byte except two supplemental raw-float JSON reports, compared at the documented six-decimal serialization precision. Frozen reference hashes remain exact.
4. Runs the strict red/green proof.

It takes about 30 s on first run. It ends with:

```
  PASS: 20 corrected greens; 13 legacy reds at their numeric assertions; 7 legacy controls green
DEMO PASS: data, baseline and corrected results verified at documented serialization precision; 13 legacy reds and 20 corrected greens verified.
```

Exit codes: 0 means every check passed, 1 means a check failed, and 2 means a prerequisite is missing.

Other targets:

| Command | What it does |
|---|---|
| `make test` | 343 tests |
| `make lint` | Ruff check and format check |
| `make verify` | Red/green proof only |
| `make baseline` | Discovery only |

Generated output goes to `.scratch/` and never overwrites the references.

Single commands, after `make install`:

```sh
.venv/bin/geo-audit generate --output OUT/data
.venv/bin/geo-audit check   --input OUT/data/SYNTHETIC_gps_pings.csv \
  --roads OUT/data/roads.geojson --zone OUT/data/zone.geojson --output OUT/check
.venv/bin/geo-audit compare --input OUT/data/SYNTHETIC_gps_pings.csv \
  --roads OUT/data/roads.geojson --zone OUT/data/zone.geojson --output OUT/compare
```

## Synthetic dataset

`data/synthetic/SYNTHETIC_gps_pings.csv` has 3,327 rows. It is 21 hand-defined
scenarios × 3 copies, giving 63 drivers, with each copy shifted by one day. Every
row has `is_synthetic=true`.

- **Geography:** a straight 10 km road and a 5.9 km rectangular zone, in UTM 52N metres.
- **Timing:** one ping every 10 s.
- **Faults:** each scenario plants one fault, or is a control. Planted faults include
  off-road noise, speed spikes, exact and conflicting duplicates, late and
  out-of-order pings, zone entry and exit, midnight crossings, a long gap, and 12
  malformed rows.
- **Separate files:** fault labels are in `fault_labels.json`. The checker never reads them.
- **Frequencies are synthetic.** They say nothing about real-world prevalence.

Fixture formulas are in `docs/scenarios.md`.

## What was found

The legacy calculation joins rows in file order. It has no dedupe and no noise
filter. It counts a whole segment if its end point is inside the zone, and it dates
the segment by the end point's UTC date.

The checker (`geo-audit check`) flags each segment decision that breaks a rule.
The discovery step then compares legacy totals with independent expected values.
Figures below are from `results/phase2/findings.md`, summed over all copies:

| Rank | Defect | Driver-days | Absolute error m | Net error m |
|---:|---|---:|---:|---:|
| 1 | R5: dated by UTC, not UTC+9 | 12 | 52,980.000 | +0.000 |
| 2 | R2: speed spikes billed | 6 | 6,708.360 | +6,708.360 |
| 3 | R3: duplicates counted again | 9 | 1,220.690 | +1,220.690 |
| 4 | R1: off-road pings billed | 6 | 732.317 | +732.317 |
| 5 | R6: zone decided by end point | 6 | 300.000 | +0.000 |
| 6 | R4: late pings joined in file order | 3 | 300.000 | +300.000 |

**R5 was chosen first.**
- It has the largest per-day error.
- It affects every driver-day on both sides of midnight.
- Its root cause is one visible decision, `date_basis="UTC endpoint"`.

R5 moves distance between days; it does not add any.
- 26,190 m sits on the wrong day.
- The two-day net is zero.
- 600 m of the 52,980 m is really R6 overlapping in the same segments.

R2 is the largest true overcount. It is discussed in `intent.md`.

## The primary fix, isolated

One 100 m segment lies wholly inside the zone. It runs from 14:59:55Z to 15:00:05Z,
crossing UTC+9 midnight halfway (`results/phase3/r5_only/driver_day.csv`):

| Reporting day (UTC+9) | Legacy m | Corrected m |
|---|---:|---:|
| 2026-11-04 | 100.000 | 50.000 |
| 2026-11-05 | 0.000 | 50.000 |

The total stays 100 m. The fix only splits it by time at midnight.

On the full trips, `results/phase3/driver_day.csv` shows:
- **S7:** legacy 5,900 / 0 becomes 2,950 / 2,950.
- **S8:** legacy 5,900 / 0 becomes 20 / 5,880.

Those vectors also include the R6 zone-edge correction.

## Corrected calculation

`src/geo_audit/calc_corrected.py` runs these steps in order:
1. Quarantine invalid rows and conflicting IDs.
2. Keep one survivor per driver and timestamp.
3. Sort by device time.
4. Drop off-road pings.
5. Drop speed violations, measured against the last accepted ping.
6. Clip each segment to the zone.
7. Split each segment at UTC+9 midnight.

Each input row gets exactly one state (`results/phase3/summary.json`):

| State | Rows |
|---|---:|
| accepted | 3,246 |
| accepted with warning | 9 |
| quarantined | 12 |
| duplicate rejected | 39 |
| noise rejected | 21 |
| **Total** | **3,327** |

Across all data, the legacy total is 263,099.458 m and the corrected total is
235,838.090 m. That difference mixes every rule. It is a reporting comparison,
not a financial settlement.

## How correctness is proven

- **Independent expected values.** `tests/expectations/analytic.json` holds literal
  numbers derived by hand from geometry. A test re-derives them with plain `math`,
  and no calculator computes its own answer.
- **Red/green proof** (`make verify`).
  - The same 20 named assertions run with `GEO_AUDIT_TARGET=legacy` and with `=corrected`, each in a fresh pytest subprocess.
  - Corrected must pass all 20.
  - Legacy must fail exactly 13, each at its own numeric assertion. Those are S2b, S3, S3b, S4, S5a, S5c, S6b, S6c, S7, S8, S9a, S9b and R5_ONLY.
  - The 7 controls must pass on both: S1, S2a, S5b, S6a, S10, S12 and S14.
  - The verifier reads structured evidence and JUnit, not exit codes alone.
  - 47 negative tests prove it rejects corrupted, stale, skipped, setup-error or sabotaged runs.
- **Characterization only.** S11 (stationary jitter) and S13 (a bad first anchor) are tested separately. They are not proof of a fix.
- **Frozen evidence.** 42 hashes of data and results are checked by every demo run.
  `scripts/verify_frozen_history.py` checks the freeze manifests against their Git
  commits, and confirms the logs were only appended to.

## Where the evidence is

| Path | Contents |
|---|---|
| `data/synthetic/` | Input CSV, road and zone GeoJSON, fault labels, manifest |
| `results/phase2/` | Legacy ledger, checker findings, discovery ranking (`findings.md`) |
| `results/phase3/` | Corrected ledger, per-row decisions, `driver_day.csv` before/after |
| `docs/phase1_evidence.md` … `docs/phase5_evidence.md` | Executed commands and results, per phase |
| `docs/ai_log.md`, `docs/effort.md` | AI provenance and recorded time |
| `intent.md`, `directive.md` | Problem write-up and technical handoff |

## Assumptions and limitations

**Assumptions:**
- Road distance means distance to the nearest line in the supplied road file.
- Movement between accepted pings is a straight line at constant speed. Long gaps
  are counted as one chord, with a warning.
- For duplicates, the earliest received copy wins, then the lowest ping ID. A
  noisy winner is not swapped for a valid copy.
- UTC+9 is a fixed offset, with no daylight saving.
- Distance along the zone boundary counts.

**Not solved:**
- A bad first anchor rejects good later pings (S13).
- Stationary jitter is billed (S11).
- Gaps are not interpolated.
- Late data never restates a report already issued.
- Driver pay rules are not modelled.

**Platform:** [Ubuntu hosted CI passed](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369010547) on Python 3.12.16:
343 tests, 13 verified legacy reds, seven controls and 20 corrected greens.
The repository and CI evidence are **private**, accessible only to authorized users.
Linux reproduced 29 of 31 reference files byte-for-byte; two supplemental raw-float
JSON reports match at six decimal places. Frozen references and numerical
expectations are unchanged. See [hosted evidence](docs/phase5b_evidence.md).
Public repository URL and Loom URL remain **pending public release**.

## How AI was used

An AI coding assistant (Claude) drafted most of the code, tests and documents, phase
by phase. The author audited each phase independently and supplied findings for it
to fix. Every number was checked against hand-derived expectations, not against the
code's own output. Mistakes caught and corrected included:
- A checker that could not explain *why* totals were wrong.
- A coordinate rounding loss of about 0.1 m.
- A ranking that credited 600 m of zone error to R5.
- A speed diagnostic that compared raw neighbouring pings instead of the last accepted ping.
- A verifier that accepted `NaN` and missing keys.
- A verifier draft that rejected its own valid run.
- A secret-scan allowlist that silently exempted a whole file.

Details are in `docs/ai_log.md`.

## Technical reference

**Geometry**
- Coordinates are projected EPSG:4326 → EPSG:32652 with `always_xy`.
- Supported area: longitude 126.8–127.3, latitude 37.3–37.7.
- Point-only zone contact has zero length.

**Time**
- Timestamps need an explicit `Z` or `±HH:MM` offset, with at most microsecond precision.

**Thresholds**
- Rejection is strictly `>` 100 m and `>` 150 km/h. Exactly 100 m or 150 km/h is kept.

**Input**
- CSV fields: `ping_id,driver_id,ts_utc,lat,lon,received_at_utc,is_synthetic`.
- Malformed rows are quarantined, not dropped.

**Modules**
- `config`: constants.
- `io`: parsing.
- `geo`, `timecut`: spatial and time primitives.
- `rules`: selection and thresholds.
- `calc_legacy`, `calc_corrected`: the two calculators.
- `checker`: diagnostics.
- `report`: serialization and reconciliation.
- `demo`: orchestration.

**Without make**

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.lock
.venv/bin/python -m pip install --no-deps --no-build-isolation -e .
.venv/bin/geo-audit demo --output .scratch/demo
```
