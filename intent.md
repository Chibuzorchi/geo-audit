# intent.md — what was found, how it was ranked, and what was left out

All data is synthetic. Figures come from `results/phase2/findings.md`,
`results/phase2/discovery.json` and `results/phase3/`. They are isolated
scenario impacts, summed over 3 copies. They are not real-world prevalence, and
not an additive financial breakdown.

## Problems found

The legacy calculation joins each driver's rows in file order. It has no dedupe
and no noise filter. It counts a whole segment when its end point is in the zone,
and it labels the segment with the end point's **UTC** date.

| # | Problem | How it was found | Synthetic impact |
|---|---|---|---|
| 1 | **R5 — wrong reporting day.** Distance is dated by UTC, not by the UTC+9 day that starts at 15:00 UTC. | Checker rule `R5_UTC_DATE`: the segment's UTC label is not its UTC+9 day. S7/S8 day vectors are compared with hand-derived splits. | 12 driver-days; 52,980 m absolute; net ≈ 0 |
| 2 | **R2 — speed spikes billed.** The out-and-back chords of an impossible jump are both counted. | `LEGACY_RAW_PAIR_SPEED_ANOMALY` is provisional evidence; S6b/S6c totals vs independent 5,900 m expectations establish the discrepancy. | 6 driver-days; +6,708.36 m |
| 3 | **R3 — duplicates counted again.** A late or conflicting copy becomes a new segment end. | `R3_R4_FILE_ORDER` (segments with zero or negative elapsed time); S2b/S3/S3b. | 9 driver-days; +1,220.69 m |
| 4 | **R1 — off-road pings billed.** The detour to a noisy point is counted. | `R1_OFF_ROAD`; S5a/S5c. | 6 driver-days; +732.32 m |
| 5 | **R6 — zone decided by end point.** An entry segment counts whole; an exit segment counts zero. | `R6_ENDPOINT`: the clipped in-zone length differs from the included length; S9a/S9b. | 6 driver-days; 300 m absolute; net ≈ 0 |
| 6 | **R4 — late pings joined in file order.** | Backward segment; S4. | 3 driver-days; +300 m |

Discovery was blind:
- The checker receives only parsed rows, roads and zone. `test_checker_blind_and_specific` runs it with file opening disabled.
- Expected values are literals in `tests/expectations/analytic.json`, derived from geometry.
- A discrepancy counts only when an executed total differs from that literal.
- The discovery script also refuses any discrepancy that has no matching checker evidence.

A flag on its own is not a defect. Exact duplicates next to their original add 0 m
(S2a), and S1's zone-entry and zone-exit errors cancel out. These cases are listed
separately as flags with no discrepancy.

## Ranking and the choice of R5

Defects were ranked by absolute driver/day discrepancy, then by number of
driver-days. R5 ranks first on that metric.

**Daily misallocation is not overcounting.** R5 does not add distance. Its
positive and negative errors are each 26,490 m, and the net is 0.00004 m.
- Removing the R6 overlap, R5 alone moves 26,190 m to the wrong day (52,380 m absolute).
- By either measure it is still about four times the R2 overcount.

R5 was chosen first because:
- Daily reporting is an explicit requirement.
- Every report is per driver per day.
- One wrong day label corrupts both days at once: the advertiser sees the wrong day, and the driver's daily record is wrong.
- The root cause is a single decision visible on every ledger row (`date_basis="UTC endpoint"`). That makes it easy to explain and to lock in.

**The case against R5.** R2 is the largest *net* overcount (+6,708 m).
If only period distance totals mattered, R2 would take priority on net overcount.
No monetary impact can be inferred without a payment model. That
trade-off was recorded before the fix was written.

## Interactions

- **R5/R6 overlap.** In S7 and S8, the segment that crosses midnight is also a zone-edge segment.
  - Fixing only the date gives (3,000, 2,900) for S7 and (70, 5,830) for S8.
  - The required (2,950, 2,950) and (20, 5,880) need R6 too.
  - So 600 m of the 52,980 m belongs to R6. That is why the primary fix is proven on
    an isolated segment: 100 m inside the zone, 14:59:55Z → 15:00:05Z.
  - Legacy gives 100 / 0. Corrected gives 50 / 50, with the same total.
- **Cancellation.** Endpoint inclusion over-counts the entry segment and under-counts the exit segment, so a full trip looks correct (S1). Only half trips (S9a, S9b) expose it.
- **Duplicates and order.** An exact copy next to its original is harmless (S2a). The same copy arriving late adds 100 m (S2b).

## Assumptions

- Road distance is measured to the nearest line in the road file.
- Speed is checked against the last *accepted* ping.
- For duplicates, the earliest received copy wins, then the lowest ping ID.
- UTC+9 is a fixed offset.
- Movement between pings is a straight line at constant speed.
- The zone boundary is inclusive.
- Invalid rows are quarantined, not repaired.

## Left unresolved, on purpose

- **A bad first anchor** (S13): an early noisy point makes valid later points look like
  speed violations. No anchor-recovery policy was invented.
- **Stationary jitter** (S11) is billed. No stationary filter was specified.
- **Long gaps** are counted as a straight chord, with a warning only.
- **Late data** does not restate reports that were already issued.
- **Driver pay** and monetary rates are not modelled. "Driver impact" means recorded distance only.

## Hosted CI

[GitHub Actions run 43369334744](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369334744)
passed on Ubuntu 24.04 with Python 3.12: 343 tests, 13 intended legacy reds, 7 controls
and 20 corrected greens. CI runs on every push.

## What existed before, and what I did for this Quest

**Before:** my experience building QA automation (Playwright, Python, pytest, API and
database checks, CI). I had the AI look at my earlier repositories only as references
for structure and testing practice. No code from them, no employer code and no real
data was reused.

**Built for this Quest:** all of GeoAudit. That means:
- the synthetic data generator and its 3,327 rows;
- the flawed legacy calculation and the QA checker;
- the corrected calculation and the independent expectations;
- the regression suite, the red/green verifier and the integrity checks;
- the CI workflow and these documents.

AI assistants wrote most of it. I planned it, commissioned independent reviews,
directed the fixes and checked the evidence. See the
[author review summary](https://github.com/Chibuzorchi/geo-audit/blob/main/docs/ai_log.md#author-review-summary-first-person).
