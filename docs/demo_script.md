# Demo walkthrough script (under 5 minutes)

This script is for a screen recording. No recording exists yet. All numbers come
from committed artifacts. Rehearse once; the demo runs in about 5 s with `.venv`
already built.

**Setup before recording:**
- Run `make install`.
- Open a terminal at the repo root with a large font.
- Open `results/phase3/r5_only/driver_day.csv` and `results/phase2/findings.md` in an editor.

## 0:00–0:35 — The problem

Say:
> "GeoAudit turns GPS pings into billed distance per driver per day, inside a zone.
> The data is synthetic: 3,327 pings, 63 drivers.
> The rule I'll focus on: the daily report is cut at midnight UTC+9, which is 15:00 UTC.
> The old calculation uses the UTC date instead."

Show: the rules table in `README.md`.

## 0:35–1:20 — One wrong number, and the checker finding it

Run:

```sh
.venv/bin/geo-audit check --input data/synthetic/SYNTHETIC_gps_pings.csv \
  --roads data/synthetic/roads.geojson --zone data/synthetic/zone.geojson --output .scratch/rec
```

Then show `results/phase2/findings.md`: the ranking table and the S8 evidence rows.

Say:
> "Segment P010 to P011 runs from 14:59:53 to 15:00:03 UTC. That crosses local midnight 7 seconds in.
> Legacy puts the whole trip on November 4: 5,900 metres, and 0 on the 5th.
> The checker flags it as R5_UTC_DATE, and also as R6_ENDPOINT on the same segment,
> because it is also the zone-entry segment. It names the rows, timestamps and the wrong date label."

## 1:20–2:10 — The isolated fix

Show `results/phase3/r5_only/driver_day.csv`:

| Day | Legacy m | Corrected m |
|---|---:|---:|
| 2026-11-04 | 100.000 | 50.000 |
| 2026-11-05 | 0.000 | 50.000 |

Say:
> "This is one 100 m segment, entirely inside the zone, crossing midnight halfway.
> The fix doesn't remove distance. It moves 50 metres to the right day.
> On the full S8 trip, 5,900 and 0 becomes 20 and 5,880."

Show `results/phase3/driver_day.csv`, rows for `SYN-S8-00`.

## 2:10–3:10 — Regression proof

Run:

```sh
make verify
```

Expected last line:
`PASS: 20 corrected greens; 13 legacy reds at their numeric assertions; 7 legacy controls green`

Say:
> "The same 20 named assertions run against both calculators.
> Legacy must fail exactly 13, each at its own number. That covers noise, duplicates, late pings, the midnight cut and the zone edge.
> The 7 controls must pass on both.
> The verifier reads structured evidence, not just exit codes. 47 tests prove it rejects fake or broken runs."

Optional, if time allows: `make demo`, to show the byte-identical regeneration.

## 3:10–4:10 — How AI was used, and one thing it got wrong

Say:
> "An AI assistant drafted most of the code. I audited every phase myself.
> One example: the AI's ranking gave all 52,980 metres of S7/S8 error to the date bug.
> Re-deriving by hand showed 600 metres were really the zone-edge bug, in the same segment.
> So I proved the fix on an isolated segment instead.
> Another example: an earlier verifier accepted NaN and missing keys as valid evidence. That's fixed, and covered by tests."

Show: `docs/ai_log.md`, section "Phase 2 audit remediation".

## 4:10–4:45 — Limits

Say:
> "Not solved: a bad first GPS point can reject good later ones.
> Stationary jitter is billed.
> Gaps are straight lines.
> Old reports aren't restated.
> And CI hasn't run on GitHub yet.
> The frequencies are synthetic, so they're not real-world prevalence."

Stop before 5:00.
