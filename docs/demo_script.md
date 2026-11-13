# Loom recording script — target 4 minutes 30 seconds

No recording exists yet. Loom URL: **PENDING RECORDING**.
Only blockquoted text is spoken. Rehearse with a timer; runtime is not guaranteed.
At 120 words per minute, the narration leaves time for screen changes and commands.
Do not claim personal verification beyond work you actually performed.

## Preparation (off camera)

- Run `make install` and `make verify` before recording.
- Open the [synthetic CSV](../data/synthetic/SYNTHETIC_gps_pings.csv),
  [findings](../results/phase2/findings.md), [isolated comparison](../results/phase3/r5_only/driver_day.csv),
  [full comparison](../results/phase3/driver_day.csv) and [AI log](ai_log.md).
- Open [successful Ubuntu run 43369334744](https://github.com/Chibuzorchi/geo-audit/actions/runs/43369334744).
  Access requires repository permission. Show the run summary, not account settings or credentials.
- Prepare a fresh checker output directory using `mktemp -d .scratch/recording.XXXXXX`.
  Set `REC` to its printed path. Do not show private files or unrelated browser tabs.
- Keep a verified terminal run visible if a live command takes longer than rehearsed.
  Describe prerecorded output honestly. Do not run installation during the recording.

## 0:00–0:35 — Synthetic input and discovered problems

Show the CSV, then the ranking in `results/phase2/findings.md`.

> GeoAudit audits GPS distance per driver and day inside a campaign zone.
> These are 3,327 synthetic observations across 63 drivers, not a real billing incident.
> The deliberately flawed baseline exposes six measured problems: wrong dates,
> speed spikes, duplicates, road noise, zone boundaries and arrival ordering.
> Conditions alone are not proof; the findings compare executed totals with independent expectations.

## 0:35–1:15 — The checker and reporting-day error

```sh
.venv/bin/geo-audit check --input data/synthetic/SYNTHETIC_gps_pings.csv \
  --roads data/synthetic/roads.geojson --zone data/synthetic/zone.geojson --output "$REC/check"
```

Show the S8 evidence in the findings file.

> Reporting midnight is 15:00 UTC because the reporting timezone is fixed UTC+9.
> Legacy instead uses the endpoint's UTC date.
> For S8, this segment crosses midnight and enters the zone. The checker exposes both conflicts,
> with source IDs and timestamps. The full trip is incorrectly reported as 5,900 metres on
> November fourth and zero on November fifth. This is date misallocation, not necessarily extra distance.

## 1:15–2:00 — Isolated and combined corrections

Show the isolated CSV, then `SYN-S7-00` and `SYN-S8-00` in the full comparison.

> The isolated fixture removes the zone complication. A hundred-metre segment lies entirely
> inside the zone and crosses midnight halfway through ten seconds.
> Legacy reports 100 and zero. Corrected reports 50 and 50. The total stays unchanged.
> The combined scenarios also need zone clipping: S7 becomes 2,950 and 2,950;
> S8 becomes 20 and 5,880. These demonstrate both the date and zone rules together.

## 2:00–2:45 — Regression proof

Run `make verify`. Expected final line:

```text
PASS: 20 corrected greens; 13 legacy reds at their numeric assertions; 7 legacy controls green
```

> The same twenty assertions run against both calculators.
> All twenty must pass on corrected. Legacy must fail thirteen at their designated numerical assertions;
> seven unaffected controls must pass. A crash or setup failure does not count as a valid red.
> The verifier checks structured evidence, fixture hashes, numerical values and complete test collection.

## 2:45–3:25 — One genuine AI-assisted mistake

Show the Phase 3 evidence-validation remediation section in `docs/ai_log.md`.

> AI assistants helped draft the code, tests and documentation. Independent review found an important mistake:
> an earlier numerical verifier accepted NaN, duplicate keys and missing required zero rows.
> The correction checks finite numbers and the complete expected key set before comparing values.
> Negative tests reproduce those corruptions and require rejection. Testing the QA tool itself was essential.
> The log separates assistant-run checks from human work; it does not claim unrecorded human verification.

## 3:25–4:00 — Actual hosted CI

Show the successful run and its `geo-audit-evidence` artifact.

> GitHub Actions passed on Ubuntu 24.04 with Python 3.12: 343 tests, no failures or skips.
> It also passed strict regression verification, deterministic regeneration and evidence-integrity checks.
> Linux exposed tiny projection roundoff differences, now covered by focused tests without changing billing expectations.
> Twenty-nine reference files match byte-for-byte; two unrounded reports agree at documented serialization precision.
> This repository and its CI evidence are currently private.

## 4:00–4:30 — Limits and close

> Bad initial anchors, stationary jitter and straight-line movement across long gaps remain limitations.
> Issued reports are not restated. Synthetic fault frequency is not real-world prevalence.
> Distance differences are not monetary losses or driver payments; no payment model exists here.
> The input, findings, corrected figures and regression proof are all traceable in the repository.

Stop recording. Review the actual duration and screen privacy before sharing.
Public repository URL and Loom URL remain pending; do not invent either.
