#!/usr/bin/env python3
"""Validate Transport3r's SMS v3.21 inspection-based measure replay.

The public property-carrier SMS output intentionally exposes absolute BASIC measures
but not property-carrier percentiles. This validator compares our deterministic
replay against those official FMCSA measures using the current monthly SMS input
inspection and violation files.

Validated here:
- Hours-of-Service Compliance
- Driver Fitness
- Controlled Substances/Alcohol
- Vehicle Maintenance

Unsafe Driving is not included because exact current-month reproduction requires the
historical 6- and 18-month power-unit inputs used in FMCSA's exposure denominator.
Hazardous Materials Compliance is not included because the public property output does
not publish that official measure.
"""

from __future__ import annotations

import json
import argparse
import datetime as dt
import pathlib
import math
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

BASE = "https://data.transportation.gov/resource"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
OUTPUT_ID = "4y6x-dmck"
INSPECTION_ID = "rbkj-cgst"
VIOLATION_ID = "8mt8-2mdr"

RULES = {
    "hos": {
        "label": "Hours-of-Service Compliance",
        "flag": "fatigued_insp",
        "matches": ("hours-of-service", "hours of service", "hos compliance"),
        "official": "hos_driv_measure",
    },
    "driver_fitness": {
        "label": "Driver Fitness",
        "flag": "dr_fitness_insp",
        "matches": ("driver fitness",),
        "official": "driv_fit_measure",
    },
    "controlled_substances": {
        "label": "Controlled Substances/Alcohol",
        "flag": "subt_alcohol_insp",
        "matches": ("controlled substances/alcohol", "controlled substances and alcohol", "drugs/alcohol"),
        "official": "contr_subst_measure",
    },
    "vehicle_maintenance": {
        "label": "Vehicle Maintenance",
        "flag": "vh_maint_insp",
        "matches": ("vehicle maintenance", "vehicle maint"),
        "official": "veh_maint_measure",
    },
}


def fetch_json(source_id: str, params: dict[str, str], attempts: int = 3) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    url = f"{BASE}/{source_id}.json?{query}"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=45) as response:
                payload = json.load(response)
            if not isinstance(payload, list):
                raise RuntimeError(f"{source_id} returned non-array JSON")
            return payload
        except Exception as exc:  # noqa: BLE001 - surface exact upstream error in validation logs
            last_error = exc
            if attempt < attempts:
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def number(value: Any) -> float:
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else 0.0
    except (TypeError, ValueError):
        return 0.0


def optional_number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def truthy(value: Any) -> bool:
    return str(value or "").strip().upper() in {"Y", "YES", "TRUE", "T", "1"}


def replay(inspections: list[dict[str, Any]], violations: list[dict[str, Any]], rule: dict[str, Any]) -> dict[str, Any]:
    inspection_weights: dict[str, float] = {}
    for inspection in inspections:
        if not truthy(inspection.get(rule["flag"])):
            continue
        unique_id = str(inspection.get("unique_id") or "").strip()
        if not unique_id:
            continue
        inspection_weights[unique_id] = number(inspection.get("time_weight"))

    severity_by_inspection: dict[str, float] = defaultdict(float)
    time_by_inspection: dict[str, float] = {}
    for violation in violations:
        basic_desc = str(violation.get("basic_desc") or "").lower()
        if not any(match in basic_desc for match in rule["matches"]):
            continue
        unique_id = str(violation.get("unique_id") or "").strip()
        if not unique_id:
            continue
        total_severity = optional_number(violation.get("total_severity_wght"))
        if total_severity is None:
            total_severity = number(violation.get("severity_weight")) + number(violation.get("oos_weight"))
        severity_by_inspection[unique_id] += total_severity
        row_time = number(violation.get("time_weight"))
        if row_time > 0:
            time_by_inspection[unique_id] = row_time

    numerator = 0.0
    capped = 0
    for unique_id, severity_sum in severity_by_inspection.items():
        capped_severity = min(30.0, severity_sum)
        if severity_sum > 30:
            capped += 1
        time_weight = time_by_inspection.get(unique_id, inspection_weights.get(unique_id, 0.0))
        numerator += capped_severity * time_weight

    denominator = sum(inspection_weights.values())
    return {
        "numerator": numerator,
        "denominator": denominator,
        "measure": numerator / denominator if denominator > 0 else None,
        "relevant_inspections": len(inspection_weights),
        "violation_inspections": len(severity_by_inspection),
        "capped_inspections": capped,
    }


def choose_candidates() -> list[dict[str, Any]]:
    rows = fetch_json(
        OUTPUT_ID,
        {
            "$limit": "300",
            "$where": "hos_driv_measure is not null or driv_fit_measure is not null or contr_subst_measure is not null or veh_maint_measure is not null",
        },
    )
    candidates: list[dict[str, Any]] = []
    for row in rows:
        insp_total = int(number(row.get("insp_total")))
        available = sum(optional_number(row.get(rule["official"])) is not None for rule in RULES.values())
        if 3 <= insp_total <= 90 and available >= 2:
            candidates.append(row)
        if len(candidates) >= 12:
            break
    if len(candidates) < 6:
        raise RuntimeError(f"Only {len(candidates)} suitable property-carrier validation candidates found")
    return candidates


def main(runtime_sample: str | None = None) -> int:
    candidates = choose_candidates()
    comparisons: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    runtime_carriers: list[dict[str, Any]] = []

    for output in candidates:
        dot_number = str(output["dot_number"])
        inspections = fetch_json(INSPECTION_ID, {"$where": f"dot_number='{dot_number}'", "$limit": "10000"})
        violations = fetch_json(VIOLATION_ID, {"$where": f"dot_number='{dot_number}'", "$limit": "20000"})
        if len(inspections) >= 10000 or len(violations) >= 20000:
            skipped.append({"dot_number": dot_number, "reason": "validation query hit row limit"})
            continue
        runtime_carriers.append({'dot_number':dot_number,'official':output,'inspections':inspections,'violations':violations})

        for key, rule in RULES.items():
            official = optional_number(output.get(rule["official"]))
            if official is None:
                continue
            result = replay(inspections, violations, rule)
            calculated = result["measure"]
            if calculated is None:
                skipped.append({"dot_number": dot_number, "basic": key, "reason": "no denominator", "official": official})
                continue
            delta = calculated - official
            comparisons.append(
                {
                    "dot_number": dot_number,
                    "basic": key,
                    "official": official,
                    "calculated": calculated,
                    "delta": delta,
                    **{field: result[field] for field in ("numerator", "denominator", "relevant_inspections", "violation_inspections", "capped_inspections")},
                }
            )

    if len(comparisons) < 12:
        print(json.dumps({"status": "insufficient_validation", "comparisons": comparisons, "skipped": skipped}, indent=2))
        return 2

    tolerance = 0.015
    mismatches = [row for row in comparisons if abs(row["delta"]) > tolerance]
    summary = {
        "status": "ok" if not mismatches else "mismatch",
        "ruleset": "SMS_3_21_CURRENT",
        "comparison_count": len(comparisons),
        "candidate_carriers": len(candidates),
        "match_count": len(comparisons) - len(mismatches),
        "mismatch_count": len(mismatches),
        "max_abs_delta": max(abs(row["delta"]) for row in comparisons),
        "mean_abs_delta": sum(abs(row["delta"]) for row in comparisons) / len(comparisons),
        "mismatches": mismatches[:20],
        "sample_matches": [row for row in comparisons if abs(row["delta"]) <= tolerance][:12],
        "skipped": skipped,
    }
    if runtime_sample:
        with pathlib.Path(runtime_sample).open('x',encoding='utf-8') as handle:
            json.dump({'captured_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                       'purpose':'LIVE_RUNTIME_REGRESSION_NOT_HISTORICAL_TRAINING',
                       'source_ids':[OUTPUT_ID,INSPECTION_ID,VIOLATION_ID],'carriers':runtime_carriers},handle,indent=2)
    print(json.dumps(summary, indent=2))
    return 0 if not mismatches else 2


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-sample',help='Write the live inputs once for application TypeScript regression')
    args=parser.parse_args()
    raise SystemExit(main(args.runtime_sample))
