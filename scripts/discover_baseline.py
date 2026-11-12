"""Post-run discovery: compare executed legacy totals with independent expectations.

Runs after `geo-audit check`. Reads the check output, the generator's instance map
and the literal expectation file. It is never imported by the checker or calculator.

Steps:
1. Gate: every legacy driver/day total must equal its analytic *legacy* expectation.
2. Measure: discrepancy = executed legacy total - analytic *required-rule* expectation.
3. Explain: attach the blind checker's decision conflicts for the affected driver.
4. Rank defects by absolute driver/day discrepancy, then affected driver/day count.
"""

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

TOLERANCE_M = 0.01  # Axis-aligned scenario tolerance from plan section 3.
BASE_DAY = date(2026, 11, 4)

# Analyst grouping; original pre-measurement timing was not independently Git-frozen.
# `evidence` lists the checker decision-conflict rules that explain each defect.
DEFECTS = {
    "D-R5-UTC-DAY": dict(
        rule="R5",
        scenarios=["S7", "S8"],
        evidence=["R5_UTC_DATE"],
        title="Distance is dated by UTC calendar day, not the UTC+9 report day",
        legacy_behavior="Each segment is labelled with its end point's UTC date.",
    ),
    "D-R2-SPEED": dict(
        rule="R2",
        scenarios=["S6b", "S6c"],
        evidence=["LEGACY_RAW_PAIR_SPEED_ANOMALY"],
        title="Speed spikes above 150 km/h are billed",
        legacy_behavior="No speed filter; the spike's out-and-back chords are both counted.",
    ),
    "D-R3-DUPLICATE": dict(
        rule="R3",
        scenarios=["S2b", "S3", "S3b"],
        evidence=["R3_R4_FILE_ORDER", "R1_OFF_ROAD"],
        title="Duplicate pings (same driver and timestamp) are counted again",
        legacy_behavior="No dedupe; a late or conflicting copy becomes a new segment end.",
    ),
    "D-R1-OFF-ROAD": dict(
        rule="R1",
        scenarios=["S5a", "S5c"],
        evidence=["R1_OFF_ROAD"],
        title="Pings more than 100 m off the road are billed",
        legacy_behavior="No road filter; the detour to the noisy ping is counted.",
    ),
    "D-R6-ZONE-ENDPOINT": dict(
        rule="R6",
        scenarios=["S9a", "S9b"],
        evidence=["R6_ENDPOINT"],
        title="Zone membership decided by segment end point only",
        legacy_behavior="Entry segment counted whole; exit segment dropped whole.",
    ),
    "D-R4-FILE-ORDER": dict(
        rule="R4",
        scenarios=["S4"],
        evidence=["R3_R4_FILE_ORDER"],
        title="Late pings are joined in file order, not by their own timestamp",
        legacy_behavior="An out-of-order row creates a backward segment.",
    ),
}
CONTROLS = {"S1", "S2a", "S5b", "S6a", "S10", "S12", "S14"}
CHARACTERIZATION = {"S11", "S13"}
SEGMENT_FIELDS = (
    "segment",
    "from_id",
    "to_id",
    "from_row",
    "to_row",
    "from_time",
    "to_time",
    "from_lon",
    "from_lat",
    "to_lon",
    "to_lat",
    "length_m",
    "endpoint_inside",
    "report_date",
    "included_m",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(args):
    expected = json.loads(args.expectations.read_text())
    instances = json.loads((args.data / "instances.json").read_text())
    totals = json.loads((args.results / "legacy_totals.json").read_text())
    ledger = json.loads((args.results / "segments_legacy.json").read_text())
    decisions = json.loads((args.results / "decision_conflicts.json").read_text())
    return expected, instances, totals, ledger, decisions


def measure(expected, instances, totals):
    observed = {(r["driver_id"], r["report_date"]): r["legacy_m"] for r in totals}
    covered = set()
    rows = []
    for instance in instances:
        name, driver, copy = instance["scenario"], instance["driver"], instance["copy"]
        legacy, required = expected[name]
        for offset, (old, want) in enumerate(zip(legacy, required, strict=True)):
            day = str(BASE_DAY + timedelta(days=copy + offset))
            covered.add((driver, day))
            actual = observed.get((driver, day), 0.0)
            if abs(actual - old) > TOLERANCE_M:
                raise SystemExit(f"GATE FAIL {name} {driver} {day}: legacy {actual} != {old}")
            difference = actual - want
            if name in CHARACTERIZATION:
                kind = "characterization"
            elif abs(difference) > TOLERANCE_M:
                kind = "discrepancy"
            else:
                kind = "control"
            rows.append(
                dict(
                    scenario=name,
                    copy=copy,
                    driver_id=driver,
                    report_day_utc9=day,
                    expected_m=want,
                    expected_legacy_m=old,
                    actual_legacy_m=actual,
                    difference_m=round(difference, 6),
                    classification=kind,
                )
            )
    stray = {k: v for k, v in observed.items() if k not in covered and abs(v) > TOLERANCE_M}
    if stray:
        raise SystemExit(f"GATE FAIL: legacy totals outside expectation keys: {stray}")
    return rows


def evidence_for(driver, rules, ledger, decisions):
    by_index = {s["segment"]: s for s in ledger}
    hits = [d for d in decisions if d["driver"] == driver]
    return [
        dict(
            rule=d["rule"],
            kind=d["kind"],
            selected_category=d["rule"] in rules,
            measurements=d["measurements"],
            ledger={k: by_index[d["measurements"]["segment"]][k] for k in SEGMENT_FIELDS},
        )
        for d in hits
    ]


def ranking_key(d):
    """Compare impacts at the approved 0.01 m resolution, then breadth."""
    return (-round(d["absolute_m"] / TOLERANCE_M), -d["driver_days"], d["defect"])


def r5_attribution(measurements):
    """Analytic S7/S8 decomposition, holding legacy endpoint inclusion fixed.

    S7: 30 included segments before midnight, 29 after.
    S8: 70 m of the entry segment before midnight, 30 + 58*100 after.
    This order-specific decomposition is not independent financial attribution.
    """
    date_only = {"S7": [3000, 2900], "S8": [70, 5830]}
    observed = isolated = residual = moved = net = positive = negative = 0.0
    for m in measurements:
        if m["scenario"] not in date_only:
            continue
        offset = (date.fromisoformat(m["report_day_utc9"]) - BASE_DAY).days - m["copy"]
        dated = date_only[m["scenario"]][offset]
        delta = m["difference_m"]
        observed += abs(delta)
        net += delta
        positive += max(delta, 0)
        negative += min(delta, 0)
        isolated += abs(m["expected_legacy_m"] - dated)
        residual += abs(dated - m["expected_m"])
        moved += max(dated - m["expected_legacy_m"], 0)
    if abs(observed - isolated - residual) > TOLERANCE_M:
        raise ValueError("R5/R6 decomposition does not reconcile")
    return dict(
        observed_absolute_m=round(observed, 6),
        positive_m=round(positive, 6),
        negative_m=round(negative, 6),
        net_m=round(net, 6),
        isolated_r5_absolute_m=isolated,
        r6_interaction_absolute_m=residual,
        r5_moved_m=moved,
        date_only_vectors=date_only,
        basis="analytic; date correction first with endpoint policy held fixed",
    )


def rank(measurements, ledger, decisions):
    scenario_to_defect = {s: k for k, v in DEFECTS.items() for s in v["scenarios"]}
    defects = {
        key: dict(
            defect=key,
            **{k: v for k, v in spec.items() if k != "evidence"},
            checker_rules=spec["evidence"],
            absolute_m=0.0,
            net_m=0.0,
            overcount_m=0.0,
            undercount_m=0.0,
            driver_days=0,
            drivers=set(),
            unexplained=[],
            by_scenario={},
        )
        for key, spec in DEFECTS.items()
    }
    for m in measurements:
        if m["classification"] != "discrepancy":
            continue
        key = scenario_to_defect.get(m["scenario"])
        if key is None:
            raise SystemExit(f"unclassified discrepancy in {m['scenario']}")
        d = defects[key]
        diff = m["difference_m"]
        d["absolute_m"] += abs(diff)
        d["net_m"] += diff
        d["overcount_m" if diff > 0 else "undercount_m"] += abs(diff)
        d["driver_days"] += 1
        d["drivers"].add(m["driver_id"])
        s = d["by_scenario"].setdefault(m["scenario"], dict(driver_days=0, absolute_m=0.0))
        s["driver_days"] += 1
        s["absolute_m"] += abs(diff)
        if not evidence_for(m["driver_id"], DEFECTS[key]["evidence"], ledger, decisions):
            d["unexplained"].append(m["driver_id"])
    ranked = []
    for d in defects.values():
        d["drivers"] = len(d["drivers"])
        for field in ("absolute_m", "net_m", "overcount_m", "undercount_m"):
            d[field] = round(d[field], 6)
        for scenario in d["by_scenario"].values():
            scenario["absolute_m"] = round(scenario["absolute_m"], 6)
        if d["driver_days"]:
            ranked.append(d)
    ranked.sort(key=ranking_key)
    for position, d in enumerate(ranked, 1):
        d["rank"] = position
    return ranked


def examples(ranked, measurements, ledger, decisions):
    """Copy-00 instance of each discrepant scenario, with segment-level evidence."""
    out = []
    for d in ranked:
        for name in d["scenarios"]:
            driver = f"SYN-{name}-00"
            rows = [m for m in measurements if m["driver_id"] == driver]
            out.append(
                dict(
                    defect=d["defect"],
                    scenario=name,
                    driver_id=driver,
                    days=rows,
                    segments=evidence_for(
                        driver, DEFECTS[d["defect"]]["evidence"], ledger, decisions
                    ),
                )
            )
    return out


def flags_without_discrepancy(measurements, decisions):
    """Show that a checker flag alone is not a billing defect."""
    control_drivers = {m["driver_id"] for m in measurements if m["classification"] == "control"}
    counts = defaultdict(int)
    for d in decisions:
        if d["driver"] in control_drivers:
            counts[(d["driver"].split("-")[1], d["rule"])] += 1
    return [dict(scenario=s, rule=r, conflicts=n) for (s, r), n in sorted(counts.items())]


def markdown(payload):
    lines = [
        "# Phase 2 executed baseline discovery (SYNTHETIC DATA)",
        "",
        f"Input sha256: `{payload['input_sha256']}`",
        f"Expectations sha256: `{payload['expectations_sha256']}`",
        f"Legacy gate: {payload['legacy_gate']}",
        "",
        "## Discrepancy-group ranking (all copies; S7/S8 interact)",
        "",
        "| Rank | Defect | Rule | Driver-days | Abs. m | Net m | Positive m | Negative magnitude m |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for d in payload["ranking"]:
        lines.append(
            f"| {d['rank']} | {d['defect']} | {d['rule']} | {d['driver_days']} | "
            f"{d['absolute_m']:.3f} | {d['net_m']:+.3f} | {d['overcount_m']:.3f} | "
            f"{d['undercount_m']:.3f} |"
        )
    lines += [
        "",
        f"Provisional primary by ranking metric: **{payload['ranking'][0]['defect']}**.",
        "",
        "R5/R6 reconciliation (metres; analytical date-only decomposition):",
        "`" + json.dumps(payload["r5_attribution"], sort_keys=True) + "`",
        "",
        "## Discrepancies, copy 00 (UTC+9 report day)",
        "",
        "| Defect | Scenario | Driver | Day | Expected m | Legacy m | Diff m |",
        "|---|---|---|---|---:|---:|---:|",
    ]
    for e in payload["examples"]:
        for m in e["days"]:
            lines.append(
                f"| {e['defect']} | {e['scenario']} | {m['driver_id']} | {m['report_day_utc9']} | "
                f"{m['expected_m']:.6f} | {m['actual_legacy_m']:.6f} | {m['difference_m']:+.6f} |"
            )
    lines += ["", "## Segment evidence, copy 00", ""]
    for e in payload["examples"]:
        lines.append(f"### {e['defect']} / {e['scenario']} / {e['driver_id']}")
        lines.append("")
        lines.append(
            "| Seg | Kind / Rule | From → To | Rows | Device UTC | Length m | Included m | Date |"
        )
        lines.append("|---:|---|---|---|---|---:|---:|---|")
        for s in e["segments"]:
            g = s["ledger"]
            lines.append(
                f"| {g['segment']} | {s['kind']} / {s['rule']} | {g['from_id']} → {g['to_id']} | "
                f"{g['from_row']}→{g['to_row']} | {g['from_time']} → {g['to_time']} | "
                f"{g['length_m']:.6f} | {g['included_m']:.6f} | {g['report_date']} |"
            )
        lines.append("")
    lines += [
        "## Checker flags with no measured discrepancy (control drivers)",
        "",
        "| Scenario | Rule | Conflicts |",
        "|---|---|---:|",
    ]
    for f in payload["flags_without_discrepancy"]:
        lines.append(f"| {f['scenario']} | {f['rule']} | {f['conflicts']} |")
    lines += [
        "",
        "Positive/negative columns are daily differences, not extra billed distance.",
        "S7/S8 mix R5 and R6; grouped impacts are not independent causal or financial effects.",
        "Raw-pair speed anomalies are provisional, not accepted-anchor rejection decisions.",
        "Scenario frequency is synthetic and says nothing about production prevalence.",
        "Driver impact means recorded distance, not assumed pay.",
    ]
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--expectations", type=Path, required=True)
    args = parser.parse_args()
    expected, instances, totals, ledger, decisions = load(args)
    measurements = measure(expected, instances, totals)
    ranked = rank(measurements, ledger, decisions)
    if len(ranked) < 3:
        raise SystemExit("fewer than three measured discrepancies")
    if any(d["unexplained"] for d in ranked):
        raise SystemExit("discrepancy without checker decision evidence")
    payload = dict(
        legacy_gate="PASS: every legacy driver/day total equals its analytic legacy expectation",
        input_sha256=sha256(args.data / "SYNTHETIC_gps_pings.csv"),
        expectations_sha256=sha256(args.expectations),
        decisions_sha256=sha256(args.results / "decision_conflicts.json"),
        counts={
            c: sum(m["classification"] == c for m in measurements)
            for c in ("discrepancy", "control", "characterization")
        },
        ranking=ranked,
        r5_attribution=r5_attribution(measurements),
        speed_basis="S6b: 418.06/10*3.6=150.5016; S6c: 1100/10*3.6=396. "
        "Both spikes rejected by independent fixture arithmetic; next anchor leg "
        "200/20*3.6=36. Raw-pair flags alone do not prove this.",
        examples=examples(ranked, measurements, ledger, decisions),
        flags_without_discrepancy=flags_without_discrepancy(measurements, decisions),
        measurements=measurements,
    )
    (args.results / "discovery.json").write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n"
    )
    (args.results / "findings.md").write_text(markdown(payload))
    json.dump(
        [
            {k: d[k] for k in ("rank", "defect", "driver_days", "absolute_m", "net_m")}
            for d in ranked
        ],
        sys.stdout,
        indent=2,
    )
    print()


if __name__ == "__main__":
    main()
