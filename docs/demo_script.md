# Loom recording script — target under 5 minutes

Only blockquoted text is spoken. The file or command to show is in brackets.
Rehearse with a timer before recording.

The order follows the brief: show the problem, run the tool, show the fix, show the
before and after numbers, then explain how AI was used.

## Preparation (off camera)

- Run `make install` first, so `make demo` does not install anything on camera.
- Run `make demo` once and note how long it takes. If it is slow, keep a finished
  run in a second terminal tab and say so on camera.
- Open these files in tabs, in order:
  - [synthetic CSV](../data/synthetic/SYNTHETIC_gps_pings.csv)
  - `.scratch/demo/check/findings.md` (written by `make demo`; reload it after the live run)
  - [legacy calculator, line 28](../src/geo_audit/calc_legacy.py)
  - [the fix, `day_intervals` at line 53](../src/geo_audit/timecut.py)
  - [isolated comparison](../results/phase3/r5_only/driver_day.csv)
  - [full comparison](../results/phase3/driver_day.csv), searched for `SYN-S8-00`
  - [AI log, author review summary](ai_log.md#author-review-summary-first-person)
- Optionally open [CI run 43893670309](https://github.com/Chibuzorchi/geo-audit/actions/runs/43893670309).
- Close unrelated tabs and private files. Do not show account settings or credentials.

## 1. Problem [CSV]

> Hi, I'm Emmanuel, and this is GeoAudit. Advertisers pay per kilometre that drivers
> travel inside a campaign zone, reported per day. But phone GPS is messy. Some pings
> are off the road. Some imply impossible speeds. Some are duplicated, some arrive
> late, and trips cross the zone edge and the midnight cut. So I generated a synthetic
> dataset: 3,327 pings from 63 drivers, with all of those faults planted on purpose.
> Everything is labelled synthetic. I also wrote a legacy calculator that gets the
> distance wrong, the way a naive one would.

## 2. Run the tool [terminal: `make demo`, then `.scratch/demo/check/findings.md`]

> Anyone can reproduce this with one command: make demo. It regenerates the data, runs
> the checker, runs both calculators, compares them against the expected numbers, and
> runs the regression proof… and it passes.

Expected final line starts with `DEMO PASS:`. Then open the findings file it just wrote.

> This is what the tool just produced.
> I didn't trust flags alone. My checker flags every segment that breaks a rule. Then
> I compare the legacy totals against values I worked out by hand from the geometry.
> A problem only counts if the numbers really differ. That gave me six real defects.
> Ranked by how much distance ends up in the wrong place: one, the wrong reporting day.
> Two, speed spikes getting billed. Three, duplicates counted twice. Then off-road
> pings, the zone boundary, and late pings. I fixed the reporting day first. It
> misplaces the most distance, about 26 kilometres, and it breaks every daily report,
> so both the advertiser's report and the driver's record are wrong. To be fair, it
> doesn't add distance. Speed spikes are the biggest real overcount, about 6.7
> kilometres. If only the monthly total mattered, I'd fix that first.

## 3. Root cause [src/geo_audit/calc_legacy.py, line 28]

Highlight `day = ping.timestamp.date().isoformat()`.

> Here's why it happens. The rule says the day ends at midnight UTC+9, which is 3 PM
> UTC. The legacy code stamps each segment with the UTC date of its end point. So
> distance driven just after local midnight gets booked to the day before, and a
> segment that crosses midnight lands entirely on one day.
> Here's the line that does it.

## 4. The fix [src/geo_audit/timecut.py, `day_intervals`, line 53]

Highlight the `cut = ...` line, then `calc_corrected.py` line 12, which calls it.

> The fix splits each segment by time at local midnight and clips it to the zone. The
> corrected calculator applies all six rules.

## 5. Before and after [results/phase3/r5_only/driver_day.csv, then results/phase3/driver_day.csv, search SYN-S8-00]

> Here's the cleanest proof: one 100-metre segment inside the zone, crossing midnight
> halfway. Before: 100 metres on November 4th, zero on the 5th. After: 50 and 50. Same total, just on the right days. On a full
> trip, driver S8: before, 5,900 metres on the 4th and zero on the 5th. After, 20 and
> 5,880. That one includes the zone-boundary fix too. This file has before and after
> for every driver and every day.

## 6. Lock it in [terminal: `make verify`]

Expected final line:

```text
PASS: 20 corrected greens; 13 legacy reds at their numeric assertions; 7 legacy controls green
```

> To lock it in, I run the same twenty number checks against both calculators. The
> corrected one passes all twenty. The old one fails thirteen, each at the exact wrong
> number I expected, and seven control cases pass on both. The checks cover GPS noise,
> duplicates, late pings, the UTC+9 cut and the zone boundary. They also run on GitHub
> Actions on every push.

## 7. AI, limits, close [docs/ai_log.md, author review summary]

> AI assistants wrote most of the code, tests and docs. I didn't trust that output on
> its own, so I had a second AI tool audit the first one's work, then reproduced its
> findings and decided the fixes. That review caught real mistakes. First, the ranking
> credited the date bug with 600 metres that were really zone-boundary error, which is
> why I proved the fix on an isolated segment. Second, the speed check compared each
> ping to the one right before it instead of the last accepted ping, which breaks the
> rule. Third, the verifier accepted invalid values and missing results, so it could
> report a false pass. Each one was fixed, with tests that try to fool it. What's still
> not solved: stationary jitter is billed, a bad first ping can reject good ones after
> it, long gaps count as a straight line, and late data doesn't restate old reports.
> So the reporting-day problem is gone, and the tests prove it stays gone. Thanks.

After recording, replace the Loom placeholder in `README.md` and `directive.md` with the real URL.
