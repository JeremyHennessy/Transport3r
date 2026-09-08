#!/usr/bin/env python3
"""Prove the streaming extraction contract needed for full SMS percentile replay.

Rejected hypotheses:
1. FMCSA DataHub's SODA2 endpoint does not expose `to_number()` on these text weight
   columns, so server-side numeric aggregation is not viable.
2. Do not assume SMS relevance flags are encoded specifically as `Y`; inspect the
   current monthly contract and interpret truthy values client-side.

Current hypothesis: use DataHub only to project/filter stable identity/category fields,
stream raw text weights, then perform the already validated v3.21 arithmetic locally.
"""

from __future__ import annotations

import csv
import io
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

BASE = "https://data.transportation.gov"
RESOURCE = f"{BASE}/resource"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
OUTPUT_ID = "4y6x-dmck"
INSPECTION_ID = "rbkj-cgst"
VIOLATION_ID = "8mt8-2mdr"


def request_bytes(url: str, timeout: int = 60, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:2000]}") from exc
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(min(3.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def fetch_json(source_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    payload = json.loads(request_bytes(f"{RESOURCE}/{source_id}.json?{query}").decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"{source_id} returned non-array JSON")
    return payload


def count_rows(source_id: str, where: str | None = None) -> int:
    params = {"$select": "count(*) as count"}
    if where:
        params["$where"] = where
    rows = fetch_json(source_id, params)
    if not rows:
        return 0
    return int(float(str(rows[0].get("count") or 0)))


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def truthy(value: Any) -> bool:
    return str(value or "").strip().upper() in {"Y", "YES", "1", "TRUE", "T"}


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
        raise RuntimeError(f"Only {len(selected)} streaming-probe candidates found")
    return selected


def soda3_export_probe(source_id: str, query: str) -> dict[str, Any]:
    params = urllib.parse.urlencode({"query": query})
    url = f"{BASE}/api/v3/views/{source_id}/export.csv?{params}"
    try:
        payload = request_bytes(url, timeout=45, attempts=1)
        text = payload.decode("utf-8-sig", errors="replace")
        rows = list(csv.DictReader(io.StringIO(text)))
        return {"status": "ok", "url": url, "bytes": len(payload), "rows": rows[:3]}
    except Exception as exc:  # noqa: BLE001
        return {"status": "failed", "url": url, "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    candidates = choose_candidates()
    dots = [str(row["dot_number"]) for row in candidates]
    in_list = ",".join(f"'{dot}'" for dot in dots)

    flag_distribution = fetch_json(
        INSPECTION_ID,
        {
            "$select": "vh_maint_insp,count(*) as count",
            "$group": "vh_maint_insp",
            "$order": "count DESC",
            "$limit": "100",
        },
    )
    truthy_flag_values = [
        str(row.get("vh_maint_insp"))
        for row in flag_distribution
        if truthy(row.get("vh_maint_insp"))
    ]
    if not truthy_flag_values:
        raise RuntimeError(f"No recognized truthy Vehicle Maintenance inspection flag in current monthly file: {flag_distribution}")

    relevant_where = "vh_maint_insp in (" + ",".join("'" + value.replace("'", "''") + "'" for value in truthy_flag_values) + ")"
    relevant_inspection_rows = count_rows(INSPECTION_ID, relevant_where)
    vm_violation_rows = count_rows(VIOLATION_ID, "basic_desc='Vehicle Maintenance'")

    export_probes = {
        "inspection": soda3_export_probe(
            INSPECTION_ID,
            f"SELECT dot_number,unique_id,time_weight,vh_maint_insp WHERE {relevant_where} LIMIT 3",
        ),
        "violation": soda3_export_probe(
            VIOLATION_ID,
            "SELECT dot_number,unique_id,severity_weight,oos_weight,time_weight,total_severity_wght WHERE basic_desc='Vehicle Maintenance' LIMIT 3",
        ),
    }

    # Batch extraction intentionally does not filter the relevance flag server-side.
    # This proves our local truthy handling matches the already validated replay.
    inspection_rows = fetch_json(
        INSPECTION_ID,
        {
            "$select": "dot_number,unique_id,time_weight,vh_maint_insp",
            "$where": f"dot_number in ({in_list})",
            "$order": "dot_number ASC,unique_id ASC",
            "$limit": "10000",
        },
    )
    violation_rows = fetch_json(
        VIOLATION_ID,
        {
            "$select": "dot_number,unique_id,severity_weight,oos_weight,time_weight,total_severity_wght",
            "$where": f"dot_number in ({in_list}) and basic_desc='Vehicle Maintenance'",
            "$order": "dot_number ASC,unique_id ASC",
            "$limit": "20000",
        },
    )
    if len(inspection_rows) >= 10_000 or len(violation_rows) >= 20_000:
        raise RuntimeError("Batch replay hit a row cap; reduce candidate batch before trusting parity")

    denominator_by_dot: dict[str, float] = defaultdict(float)
    relevant_count_by_dot: dict[str, int] = defaultdict(int)
    inspection_time_by_key: dict[tuple[str, str], float] = {}
    for row in inspection_rows:
        if not truthy(row.get("vh_maint_insp")):
            continue
        dot = str(row.get("dot_number") or "")
        unique_id = str(row.get("unique_id") or "")
        time_weight = number(row.get("time_weight")) or 0.0
        if not dot or not unique_id:
            continue
        denominator_by_dot[dot] += time_weight
        relevant_count_by_dot[dot] += 1
        inspection_time_by_key[(dot, unique_id)] = time_weight

    severity_by_key: dict[tuple[str, str], float] = defaultdict(float)
    violation_time_by_key: dict[tuple[str, str], float] = {}
    for row in violation_rows:
        dot = str(row.get("dot_number") or "")
        unique_id = str(row.get("unique_id") or "")
        if not dot or not unique_id:
            continue
        total = number(row.get("total_severity_wght"))
        severity = total if total is not None else (number(row.get("severity_weight")) or 0.0) + (number(row.get("oos_weight")) or 0.0)
        severity_by_key[(dot, unique_id)] += severity
        row_time = number(row.get("time_weight")) or 0.0
        if row_time > 0:
            violation_time_by_key[(dot, unique_id)] = row_time

    numerator_by_dot: dict[str, float] = defaultdict(float)
    violation_inspection_count_by_dot: dict[str, int] = defaultdict(int)
    capped_by_dot: dict[str, int] = defaultdict(int)
    for (dot, unique_id), severity_sum in severity_by_key.items():
        capped = min(30.0, severity_sum)
        if severity_sum > 30:
            capped_by_dot[dot] += 1
        time_weight = violation_time_by_key.get((dot, unique_id), inspection_time_by_key.get((dot, unique_id), 0.0))
        numerator_by_dot[dot] += capped * time_weight
        violation_inspection_count_by_dot[dot] += 1

    comparisons: list[dict[str, Any]] = []
    for output in candidates:
        dot = str(output["dot_number"])
        denominator = denominator_by_dot.get(dot, 0.0)
        if denominator <= 0:
            raise RuntimeError(f"No Vehicle Maintenance denominator returned for USDOT {dot}; flag distribution={flag_distribution}")
        calculated = numerator_by_dot.get(dot, 0.0) / denominator
        official = number(output.get("veh_maint_measure"))
        if official is None:
            raise RuntimeError(f"No official Vehicle Maintenance measure for USDOT {dot}")
        comparisons.append(
            {
                "dot_number": dot,
                "official": official,
                "calculated": calculated,
                "delta": calculated - official,
                "numerator": numerator_by_dot.get(dot, 0.0),
                "denominator": denominator,
                "raw_relevant_inspections": relevant_count_by_dot.get(dot, 0),
                "official_vehicle_inspections": int(number(output.get("vehicle_insp_total")) or 0),
                "raw_violation_inspections": violation_inspection_count_by_dot.get(dot, 0),
                "official_violation_inspections": int(number(output.get("veh_maint_insp_w_viol")) or 0),
                "capped_inspections": capped_by_dot.get(dot, 0),
            }
        )

    measure_mismatches = [row for row in comparisons if abs(row["delta"]) > 0.015]
    relevant_count_mismatches = [row for row in comparisons if row["raw_relevant_inspections"] != row["official_vehicle_inspections"]]
    violation_count_mismatches = [row for row in comparisons if row["raw_violation_inspections"] != row["official_violation_inspections"]]
    payload = {
        "status": "ok" if not measure_mismatches and not relevant_count_mismatches and not violation_count_mismatches else "mismatch",
        "rejected_server_cast": "FMCSA SODA2 endpoint returns query.soql.no-such-function for to_number(text)",
        "vh_maint_insp_distribution": flag_distribution,
        "truthy_flag_values": truthy_flag_values,
        "relevant_inspection_rows": relevant_inspection_rows,
        "vehicle_maintenance_violation_rows": vm_violation_rows,
        "soda3_export_probes": export_probes,
        "candidate_count": len(comparisons),
        "measure_mismatches": measure_mismatches,
        "relevant_count_mismatches": relevant_count_mismatches,
        "violation_count_mismatches": violation_count_mismatches,
        "max_abs_delta": max(abs(row["delta"]) for row in comparisons),
        "comparisons": comparisons,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["status"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
