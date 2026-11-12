# Analytic fixture basis

Frozen before measurement: three copies of each S1–S14 variant listed in the
literal expectation file, with one driver per instance. Copy n shifts both
timestamps by n days. No observation from one instance links to another.
`tests/expectations/analytic.json` stores legacy and required-rule day vectors,
starting November 4 plus copy offset. These are mathematical expectations, not
outputs computed by either calculator. S11 and S13 are characterization only.

The base has E=1000+100k, N=0, k=0..80 at ten-second intervals. Road is N=0;
zone E=2050..7950, N=-500..500. All local coordinates offset UTM (320000,4150000).
Base in-zone length is 7950−2050=5900. Legacy's 59 endpoint-included 100 m
segments happen to cancel entry and exit error.

- S2b: 3000→3100→3200→3100 in file order: 100+100+100=300, required 200.
- S3: 3000→3100→(3100,60)→3200: 100+60+sqrt(13600)=276.619037896906; required 200.
- S3b: replace 60 with 150: 100+150+sqrt(32500)=430.277563773199; required 200.
- S4: file order 3000→3200→3100: 200+100=300; required 200.
- S5a/b/c: replace 200 m around the middle point with 2sqrt(10000+N²).
  N=150 or 100.5 is ignored under the rules; N=99.5 remains eligible.
- S6a/b/c: excursions replace 200 m with forward+backward movement.
  415.28+215.28 yields 6330.56; 418.06+218.06 yields 6336.12;
  1100+900 yields 7700. The last two spikes exceed the speed ceiling.
- S7: midnight at E=5000 divides 5900 into 2950/2950; legacy labels all 5900 on UTC November 4.
- S8: midnight at E=2070 leaves 20 m in the old day and 5880 in the new day.
- S9a/b: half trips each require 2950; endpoint inclusion produces 2900/3000.
- S10: missing indices 20..59 leaves the 4100 m chord inside the zone;
  both totals remain 5900. This is a gap diagnostic, not a billing discrepancy.
- S11: sixty 10 m jitter movements total 600; no stationary filter is assumed.
- S12: four malformed rows are quarantined without changing the base total.
- S13: initial E=9000 then 3000 and 3100 at 10/20 s: legacy 6100;
  the initial-anchor policy rejects both later points. This is a limitation.
- S14: E=0→100 stays outside, yielding zero.

S2a's adjacent identical copies add zero baseline length. Labels record planted
conditions separately; labels are never checker input. CSV coordinates use ten
decimal places; the fixed 0.01 m tolerance covers serialization noise.

## Frozen multiplicity (analytic-v1)

Each of the 21 scenarios appears 3 times: 63 drivers, 3327 rows, 3315 structured.
Rows per copy: S1 81, S2a 91, S2b 4, S3 4, S3b 4, S4 3, S5a/b/c 81 each,
S6a/b/c 81 each, S7 81, S8 81, S9a 41, S9b 41, S10 41, S11 61, S12 85, S13 3, S14 2.
Frequency is synthetic and uniform; it does not model production prevalence.
