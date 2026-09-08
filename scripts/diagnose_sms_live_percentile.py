#!/usr/bin/env python3
"""Infer current SMS percentile ranking mechanics from official FMCSA passenger pages.

Bulk passenger output (`SMS AB Pass`, m3ry-qcip) currently exposes measures and
safety-event counts but leaves percentile columns blank. FMCSA's live passenger BASIC
pages do publish the official percentile. This diagnostic therefore builds the full
passenger comparison population from bulk output, samples carriers likely to have a
percentile, fetches their live BASIC page, and tests ranking/tie transforms.

Diagnostic-only: this script does not bless a production percentile formula.
"""

from __future__ import annotations

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
EXPECTED_SNAPSHOT = "July 31, 2026"

BASICS = {
    "hos": {
        "label": "Hours-of-Service Compliance",
        "measure": "hos_driv_measure",
        "violation_inspections": "hos_driv_insp_w_viol",
        "event_total": "driver_insp_total",
        "path": "HOSCompliance.aspx",
        "groups": [(1, 3, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
        "min_violation_inspections": 3,
    },
    "driver_fitness": {
        "label": "Driver Fitness",
        "measure": "driv_fit_measure",
        "violation_inspections": "driv_fit_insp_w_viol",
        "event_total": "driver_insp_total",
        "path": "DriverFitness.aspx",
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
        "min_violation_inspections": 5,
    },
    "vehicle_maintenance": {
        "label": "Vehicle Maintenance",
        "measure": "veh_maint_measure",
        "violation_inspections": "veh_maint_insp_w_viol",
        "event_total": "vehicle_insp_total",
        "path": "VehicleMaint.aspx",
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
        "min_violation_inspections": 5,
    },
}


def fetch_bytes(url: str, timeout: int = 35, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def fetch_json(source_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    payload = json.loads(fetch_bytes(f"{DATAHUB}/{source_id}.json?{query}").decode("utf-8"))
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


def tie_ranks(values: list[float], method: str) -> list[float]:
    positions: dict[float, list[int]] = defaultdict(list)
    for index, value in enumerate(values):
        positions[value].append(index)
    dense_order = {value: rank for rank, value in enumerate(sorted(positions))}
    result: list[float] = []
    for value in values:
        indexes = positions[value]
        if method == "min":
            result.append(float(indexes[0]))
        elif method == "max":
            result.append(float(indexes[-1]))
        elif method == "average":
            result.append((indexes[0] + indexes[-1]) / 2)
        elif method == "dense":
            result.append(float(dense_order[value]))
        else:
            raise ValueError(method)
    return result


def scaled_percentiles(values: list[float], method: str) -> list[float]:
    if not values:
        return []
    ranks = tie_ranks(values, method)
    denominator = max(ranks) if method == "dense" else max(1, len(values) - 1)
    return [0.0 if denominator == 0 else 100.0 * rank / denominator for rank in ranks]


def transforms(raw: float) -> dict[str, float]:
    return {"raw": raw, "round": float(round(raw)), "floor": float(math.floor(raw)), "ceil": float(math.ceil(raw)), "one_decimal": round(raw, 1)}


def quantile_sample(rows: list[dict[str, Any]], count: int) -> list[dict[str, Any]]:
    if len(rows) <= count:
        return rows
    selected: list[dict[str, Any]] = []
    for index in range(count):
        position = round(index * (len(rows) - 1) / (count - 1)) if count > 1 else 0
        selected.append(rows[position])
    return list({str(row["dot_number"]): row for row in selected}.values())


def main() -> int:
    rows = fetch_json(PASSENGER_OUTPUT_ID, {"$limit": "50000"})
    reports: dict[str, Any] = {}
    overall_observations = 0

    for basic_key, rule in BASICS.items():
        populations: dict[int, list[dict[str, Any]]] = defaultdict(list)
        candidates: list[dict[str, Any]] = []
        for row in rows:
            measure = number(row.get(rule["measure"]))
            if measure is None:
                continue
            group = safety_group(integer(row.get(rule["event_total"])), rule["groups"])
            if group is None:
                continue
            enriched = {**row, "_measure": measure, "_group": group}
            populations[group].append(enriched)
            if integer(row.get(rule["violation_inspections"])) >= rule["min_violation_inspections"] and measure > 0:
                candidates.append(enriched)

        rank_maps: dict[tuple[int, str], dict[str, float]] = {}
        for group, population in populations.items():
            population.sort(key=lambda row: (row["_measure"], str(row["dot_number"])))
            measures = [float(row["_measure"]) for row in population]
            for method in ("min", "max", "average", "dense"):
                pct_values = scaled_percentiles(measures, method)
                rank_maps[(group, method)] = {str(row["dot_number"]): pct for row, pct in zip(population, pct_values, strict=True)}

        candidates.sort(key=lambda row: (row["_group"], row["_measure"], str(row["dot_number"])))
        observations: list[dict[str, Any]] = []
        fetch_errors: list[dict[str, str]] = []
        for row in quantile_sample(candidates, 28):
            dot_number = str(row["dot_number"])
            url = f"{SMS_SITE}/{dot_number}/BASIC/{rule['path']}"
            try:
                page = parse_basic_page(fetch_bytes(url))
            except Exception as exc:  # noqa: BLE001
                fetch_errors.append({"dot_number": dot_number, "error": f"{type(exc).__name__}: {exc}"})
                continue
            if page["snapshot"] != EXPECTED_SNAPSHOT or page["percentile"] is None or page["measure"] is None:
                continue
            if abs(page["measure"] - row["_measure"]) > 0.02:
                continue
            predictions: dict[str, float] = {}
            for method in ("min", "max", "average", "dense"):
                raw_pct = rank_maps[(row["_group"], method)][dot_number]
                for transform_name, transformed in transforms(raw_pct).items():
                    predictions[f"{method}:{transform_name}"] = transformed
            observations.append({
                "dot_number": dot_number,
                "group": row["_group"],
                "bulk_measure": row["_measure"],
                "official_measure": page["measure"],
                "official_percentile": page["percentile"],
                "official_group_text": page["group_text"],
                "predictions": predictions,
            })
            time.sleep(0.08)

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
            "ranking_population": {str(group): len(population) for group, population in populations.items()},
            "eligible_candidate_count": len(candidates),
            "official_observations": len(observations),
            "best_methods": scored_methods[:10],
            "observations": observations[:12],
            "fetch_errors": fetch_errors[:10],
        }
        overall_observations += len(observations)

    payload = {"status": "diagnostic_only" if overall_observations >= 12 else "insufficient_official_percentiles", "snapshot": EXPECTED_SNAPSHOT, "passenger_rows": len(rows), "official_observations": overall_observations, "basics": reports}
    print(json.dumps(payload, indent=2))
    return 0 if overall_observations >= 12 else 2


if __name__ == "__main__":
    raise SystemExit(main())
