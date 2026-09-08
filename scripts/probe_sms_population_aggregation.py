#!/usr/bin/env python3
"""Prove the server-side aggregation contract needed for full SMS percentile replay.

Before attempting a nationwide reconstruction, this probe tests one hypothesis only:
Socrata can aggregate the current monthly SMS inspection/violation inputs in a way that
reproduces the already validated Vehicle Maintenance measure for real carriers.
"""

from __future__ import annotations

import json
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


def fetch_json(source_id: str, params: dict[str, str], attempts: int = 3) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    url = f"{BASE}/{source_id}.json?{query}"
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            if not isinstance(payload, list):
                raise RuntimeError(f"{source_id} returned non-array JSON")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(min(3.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def choose_candidates() -> list[dict[str, Any]]:
    rows = fetch_json(
        OUTPUT_ID,
        {
            "$select": "dot_number,veh_maint_measure,vehicle_insp_total,veh_maint_insp_w_viol",
            "$where": "veh_maint_measure is not null and veh_maint_insp_w_viol is not null",
            "$order": "dot_number ASC",
            "$limit": "300",
        },
    )
    selected: list[dict[str, Any]] = []
    for row in rows:
        inspections = number(row.get("vehicle_insp_total")) or 0
        violations = number(row.get("veh_maint_insp_w_viol")) or 0
        if 5 <= inspections <= 100 and violations >= 1:
            selected.append(row)
        if len(selected) >= 12:
            break
    if len(selected) < 8:
        raise RuntimeError(f"Only {len(selected)} aggregation-probe candidates found")
    return selected


def main() -> int:
    candidates = choose_candidates()
    dots = [str(row["dot_number"]) for row in candidates]
    in_list = ",".join(f"'{dot}'" for dot in dots)

    denominators = fetch_json(
        INSPECTION_ID,
        {
            "$select": "dot_number,sum(to_number(time_weight)) as denominator,count(*) as relevant_inspections",
            "$where": f"dot_number in ({in_list}) and vh_maint_insp='Y'",
            "$group": "dot_number",
            "$order": "dot_number ASC",
            "$limit": "1000",
        },
    )
    denominator_by_dot = {str(row["dot_number"]): row for row in denominators}

    inspection_violations = fetch_json(
        VIOLATION_ID,
        {
            "$select": "dot_number,unique_id,max(to_number(time_weight)) as time_weight,sum(to_number(severity_weight)+to_number(oos_weight)) as severity",
            "$where": f"dot_number in ({in_list}) and basic_desc='Vehicle Maintenance'",
            "$group": "dot_number,unique_id",
            "$order": "dot_number ASC,unique_id ASC",
            "$limit": "10000",
        },
    )

    numerator_by_dot: dict[str, float] = defaultdict(float)
    capped_by_dot: dict[str, int] = defaultdict(int)
    for row in inspection_violations:
        dot = str(row["dot_number"])
        severity = number(row.get("severity")) or 0.0
        time_weight = number(row.get("time_weight")) or 0.0
        if severity > 30:
            capped_by_dot[dot] += 1
        numerator_by_dot[dot] += min(30.0, severity) * time_weight

    comparisons: list[dict[str, Any]] = []
    for output in candidates:
        dot = str(output["dot_number"])
        denominator_row = denominator_by_dot.get(dot)
        denominator = number(denominator_row.get("denominator")) if denominator_row else None
        if denominator is None or denominator <= 0:
            raise RuntimeError(f"No Vehicle Maintenance denominator returned for USDOT {dot}")
        numerator = numerator_by_dot.get(dot, 0.0)
        calculated = numerator / denominator
        official = number(output.get("veh_maint_measure"))
        if official is None:
            raise RuntimeError(f"No official Vehicle Maintenance measure for USDOT {dot}")
        delta = calculated - official
        comparisons.append(
            {
                "dot_number": dot,
                "official": official,
                "calculated": calculated,
                "delta": delta,
                "numerator": numerator,
                "denominator": denominator,
                "aggregated_relevant_inspections": int(number(denominator_row.get("relevant_inspections")) or 0),
                "official_vehicle_inspections": int(number(output.get("vehicle_insp_total")) or 0),
                "official_violation_inspections": int(number(output.get("veh_maint_insp_w_viol")) or 0),
                "aggregated_violation_inspections": sum(1 for row in inspection_violations if str(row["dot_number"]) == dot),
                "capped_inspections": capped_by_dot.get(dot, 0),
            }
        )

    mismatches = [row for row in comparisons if abs(row["delta"]) > 0.015]
    inspection_count_mismatches = [
        row for row in comparisons
        if row["aggregated_relevant_inspections"] != row["official_vehicle_inspections"]
    ]
    payload = {
        "status": "ok" if not mismatches and not inspection_count_mismatches else "mismatch",
        "candidate_count": len(comparisons),
        "measure_mismatches": mismatches,
        "inspection_count_mismatches": inspection_count_mismatches,
        "max_abs_delta": max(abs(row["delta"]) for row in comparisons),
        "comparisons": comparisons,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
