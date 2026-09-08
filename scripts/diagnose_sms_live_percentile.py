#!/usr/bin/env python3
"""Validate current SMS percentile ranking mechanics from official FMCSA passenger pages.

FMCSA v3.21 generates percentile relationships from U.S.-domiciled interstate/HM
carriers and explicitly states that safety-event groups are not segmented by commodity
or industry. Public passenger BASIC pages expose official percentiles; property pages
do not. Therefore this diagnostic uses:

* `SMS AB Pass` (passenger) + `SMS AB PassProperty` (property) to construct the
  combined AB measure distribution inside each safety-event group; and
* public passenger BASIC pages as the official measure/percentile observations.

To keep the diagnostic compact, DataHub performs server-side grouping by measure and
relevant-inspection count. No national row-level dataset is committed or downloaded.
This stage intentionally does not yet remove non-U.S.-domiciled carriers; if the
combined AB distribution fits closely but not exactly, domicile filtering is the next
single hypothesis to test.
"""

from __future__ import annotations

import concurrent.futures
import html
import json
import math
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

DATAHUB = "https://data.transportation.gov/resource"
SMS_SITE = "https://ai.fmcsa.dot.gov/SMS/Carrier"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
PASSENGER_OUTPUT_ID = "m3ry-qcip"
PROPERTY_OUTPUT_ID = "4y6x-dmck"
EXPECTED_SNAPSHOT = "July 31, 2026"
PAGE_WORKERS = 6
PAGE_SAMPLE_PER_BASIC = 18
AGGREGATE_PAGE_SIZE = 50_000

BASICS = {
    "hos": {
        "label": "Hours-of-Service Compliance",
        "measure": "hos_driv_measure",
        "violation_inspections": "hos_driv_insp_w_viol",
        "event_total": "driver_insp_total",
        "path": "HOSCompliance.aspx",
        "groups": [(1, 3, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
        "display_min_violation_inspections": 3,
    },
    "driver_fitness": {
        "label": "Driver Fitness",
        "measure": "driv_fit_measure",
        "violation_inspections": "driv_fit_insp_w_viol",
        "event_total": "driver_insp_total",
        "path": "DriverFitness.aspx",
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
        "display_min_violation_inspections": 5,
    },
    "vehicle_maintenance": {
        "label": "Vehicle Maintenance",
        "measure": "veh_maint_measure",
        "violation_inspections": "veh_maint_insp_w_viol",
        "event_total": "vehicle_insp_total",
        "path": "VehicleMaint.aspx",
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
        "display_min_violation_inspections": 5,
    },
}


def fetch_bytes(url: str, timeout: int = 12, attempts: int = 2) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(0.5)
    assert last_error is not None
    raise last_error


def fetch_json(source_id: str, params: dict[str, str], timeout: int = 30, attempts: int = 3) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    payload = json.loads(fetch_bytes(f"{DATAHUB}/{source_id}.json?{query}", timeout=timeout, attempts=attempts).decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"{source_id} returned non-array JSON")
    return payload


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def integer(value: Any) -> int:
    parsed = number(value)
    return int(parsed) if parsed is not None else 0


def safety_group(event_total: int, groups: list[tuple[int, int, float]]) -> int | None:
    for group, minimum, maximum in groups:
        if minimum <= event_total <= maximum:
            return group
    return None


def strip_html(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_basic_page(raw: bytes) -> dict[str, Any]:
    text = strip_html(raw)
    snapshot_match = re.search(r"24-month record ending\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    measure_match = re.search(r"On-Road Performance\s+Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I) or re.search(r"Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    percentile_match = re.search(r"Percentile:\s*([0-9]+(?:\.[0-9]+)?)%", text, re.I) or re.search(r"([0-9]+(?:\.[0-9]+)?)%\s+Percentile", text, re.I)
    group_match = re.search(r"Safety Event Group:\s*([^%]+?)(?:\d+%\s+Intervention|Investigation Results|Carrier Measure Over Time)", text, re.I)
    return {
        "snapshot": snapshot_match.group(1) if snapshot_match else None,
        "measure": float(measure_match.group(1)) if measure_match else None,
        "percentile": float(percentile_match.group(1)) if percentile_match else None,
        "group_text": group_match.group(1).strip() if group_match else None,
    }


def fetch_distribution_rows(source_id: str, measure_field: str, event_field: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = fetch_json(
            source_id,
            {
                "$select": f"{measure_field},{event_field},count(*) as n",
                "$where": f"{measure_field} is not null and {event_field} is not null",
                "$group": f"{measure_field},{event_field}",
                "$limit": str(AGGREGATE_PAGE_SIZE),
                "$offset": str(offset),
            },
            timeout=45,
            attempts=3,
        )
        rows.extend(batch)
        if len(batch) < AGGREGATE_PAGE_SIZE:
            break
        offset += AGGREGATE_PAGE_SIZE
        if offset > 500_000:
            raise RuntimeError(f"Aggregate distribution for {source_id} exceeded safety pagination limit")
    return rows


def combined_distribution(rule: dict[str, Any]) -> dict[int, dict[float, int]]:
    distributions: dict[int, dict[float, int]] = defaultdict(lambda: defaultdict(int))
    for source_id in (PASSENGER_OUTPUT_ID, PROPERTY_OUTPUT_ID):
        for row in fetch_distribution_rows(source_id, rule["measure"], rule["event_total"]):
            measure = number(row.get(rule["measure"]))
            event_total = integer(row.get(rule["event_total"]))
            count = integer(row.get("n"))
            group = safety_group(event_total, rule["groups"])
            if measure is None or measure <= 0 or group is None or count <= 0:
                continue
            distributions[group][measure] += count
    return {group: dict(counts) for group, counts in distributions.items()}


def percentile_predictions(distribution: dict[float, int], target_measure: float) -> dict[str, float]:
    ordered = sorted(distribution.items())
    total = sum(count for _, count in ordered)
    if total <= 1:
        return {}
    unique_measures = [measure for measure, _ in ordered]
    if target_measure not in distribution:
        return {}

    less = sum(count for measure, count in ordered if measure < target_measure)
    equal = distribution[target_measure]
    min_rank = float(less)
    max_rank = float(less + equal - 1)
    average_rank = (min_rank + max_rank) / 2
    dense_rank = float(unique_measures.index(target_measure))
    dense_denominator = max(1, len(unique_measures) - 1)
    row_denominator = max(1, total - 1)

    raw_by_method = {
        "min": 100 * min_rank / row_denominator,
        "max": 100 * max_rank / row_denominator,
        "average": 100 * average_rank / row_denominator,
        "dense": 100 * dense_rank / dense_denominator,
    }
    predictions: dict[str, float] = {}
    for method, raw in raw_by_method.items():
        transformed = {
            "raw": raw,
            "round": float(round(raw)),
            "floor": float(math.floor(raw)),
            "ceil": float(math.ceil(raw)),
            "one_decimal": round(raw, 1),
        }
        for transform_name, value in transformed.items():
            predictions[f"{method}:{transform_name}"] = value
    return predictions


def quantile_sample(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(rows) <= count:
        return rows
    selected: list[dict[str, Any]] = []
    for index in range(count):
        position = round(index * (len(rows) - 1) / (count - 1)) if count > 1 else 0
        selected.append(rows[position])
    return list({str(row["dot_number"]): row for row in selected}.values())


def fetch_candidate(rule: dict[str, Any], row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    dot_number = str(row["dot_number"])
    url = f"{SMS_SITE}/{dot_number}/BASIC/{rule['path']}"
    try:
        return row, parse_basic_page(fetch_bytes(url)), None
    except Exception as exc:  # noqa: BLE001
        return row, None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    passenger_rows = fetch_json(PASSENGER_OUTPUT_ID, {"$limit": "50000"})
    reports: dict[str, Any] = {}
    overall_observations = 0

    for basic_key, rule in BASICS.items():
        distribution_by_group = combined_distribution(rule)
        display_candidates: list[dict[str, Any]] = []
        for row in passenger_rows:
            measure = number(row.get(rule["measure"]))
            group = safety_group(integer(row.get(rule["event_total"])), rule["groups"])
            if measure is None or measure <= 0 or group is None:
                continue
            if integer(row.get(rule["violation_inspections"])) < rule["display_min_violation_inspections"]:
                continue
            display_candidates.append({**row, "_measure": measure, "_group": group})

        display_candidates.sort(key=lambda row: (row["_group"], row["_measure"], str(row["dot_number"])))
        observations: list[dict[str, Any]] = []
        fetch_errors: list[dict[str, str]] = []

        with concurrent.futures.ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
            futures = [pool.submit(fetch_candidate, rule, row) for row in quantile_sample(display_candidates, PAGE_SAMPLE_PER_BASIC)]
            for future in concurrent.futures.as_completed(futures):
                row, page, error = future.result()
                dot_number = str(row["dot_number"])
                if error:
                    fetch_errors.append({"dot_number": dot_number, "error": error})
                    continue
                assert page is not None
                if page["snapshot"] != EXPECTED_SNAPSHOT or page["percentile"] is None or page["measure"] is None:
                    continue
                if abs(page["measure"] - row["_measure"]) > 0.02:
                    continue
                predictions = percentile_predictions(distribution_by_group.get(row["_group"], {}), row["_measure"])
                if not predictions:
                    continue
                observations.append({
                    "dot_number": dot_number,
                    "group": row["_group"],
                    "bulk_measure": row["_measure"],
                    "violation_inspections": integer(row.get(rule["violation_inspections"])),
                    "official_measure": page["measure"],
                    "official_percentile": page["percentile"],
                    "official_group_text": page["group_text"],
                    "predictions": predictions,
                })

        observations.sort(key=lambda row: (row["group"], row["bulk_measure"], row["dot_number"]))
        method_errors: dict[str, list[float]] = defaultdict(list)
        for observation in observations:
            for name, predicted in observation["predictions"].items():
                method_errors[name].append(abs(predicted - observation["official_percentile"]))
        scored_methods = []
        for name, errors in method_errors.items():
            scored_methods.append({
                "method": name,
                "observations": len(errors),
                "exact": sum(error < 0.001 for error in errors),
                "within_0_5": sum(error <= 0.5 for error in errors),
                "within_1": sum(error <= 1 for error in errors),
                "mae": sum(errors) / len(errors),
                "max_error": max(errors),
            })
        scored_methods.sort(key=lambda item: (item["mae"], item["max_error"], item["method"]))
        reports[basic_key] = {
            "label": rule["label"],
            "peer_population": "combined SMS AB passenger + property, positive measures, grouped by relevant inspections",
            "ranking_population": {str(group): sum(counts.values()) for group, counts in distribution_by_group.items()},
            "unique_measure_counts": {str(group): len(counts) for group, counts in distribution_by_group.items()},
            "display_candidate_count": len(display_candidates),
            "official_observations": len(observations),
            "best_methods": scored_methods[:10],
            "observations": observations[:12],
            "fetch_errors": fetch_errors[:10],
        }
        overall_observations += len(observations)

    payload = {
        "status": "diagnostic_only" if overall_observations >= 12 else "insufficient_official_percentiles",
        "snapshot": EXPECTED_SNAPSHOT,
        "passenger_rows": len(passenger_rows),
        "official_observations": overall_observations,
        "basics": reports,
    }
    print(json.dumps(payload, indent=2))
    return 0 if overall_observations >= 12 else 2


if __name__ == "__main__":
    raise SystemExit(main())
