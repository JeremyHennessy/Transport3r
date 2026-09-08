#!/usr/bin/env python3
"""Reconstruct exact Vehicle Maintenance measures for the full SMS population.

This diagnostic streams the current monthly FMCSA SMS input rows through SODA3 CSV
exports, performs the already validated v3.21 arithmetic locally at full precision,
then compares candidate percentile rank transforms to live Public Passenger Carrier
Vehicle Maintenance pages from the same SMS snapshot.

Nothing from this script is presented as a calculated property percentile until the
rank transform is demonstrated against official live percentiles.
"""

from __future__ import annotations

import concurrent.futures
import csv
import html.parser
import io
import json
import math
import re
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Iterator

BASE = "https://data.transportation.gov"
SMS = "https://ai.fmcsa.dot.gov/SMS/Carrier"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
INSPECTION_ID = "rbkj-cgst"
VIOLATION_ID = "8mt8-2mdr"

EXPECTED_RELEVANT_INSPECTIONS = 3_784_585
EXPECTED_VM_VIOLATIONS = 5_130_333

# Carriers previously confirmed to expose current numeric Vehicle Maintenance
# percentiles across safety-event groups. Pages are re-read on every diagnostic run;
# no percentile/measure values are hard-coded.
VERIFY_DOTS = [
    "1868971", "2797021", "3739959", "4024810",  # 5-10 vehicle inspections
    "787669", "2785715", "240318", "1322119",  # 11-20
    "825084", "276423", "4092902", "2822783",  # 21-100
    "1848503", "665732",                          # 101-500
    "1002211",                                     # 501+
]

GROUPS = [
    (1, 5, 10),
    (2, 11, 20),
    (3, 21, 100),
    (4, 101, 500),
    (5, 501, math.inf),
]


class TextExtractor(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


def request(url: str, timeout: int = 600) -> urllib.response.addinfourl:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv,text/html"})
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body[:2000]}") from exc


def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def stream_export(source_id: str, query: str) -> Iterator[dict[str, str]]:
    params = urllib.parse.urlencode({"query": query})
    url = f"{BASE}/api/v3/views/{source_id}/export.csv?{params}"
    print(f"Streaming {source_id}: {query}", flush=True)
    with request(url) as response:
        wrapper = io.TextIOWrapper(response, encoding="utf-8-sig", newline="")
        reader = csv.reader(wrapper)
        try:
            headers = [normalize_header(value) for value in next(reader)]
        except StopIteration:
            return
        for values in reader:
            yield {headers[index]: value for index, value in enumerate(values) if index < len(headers)}


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def safety_event_group(relevant_inspections: int) -> int | None:
    for group, lower, upper in GROUPS:
        if lower <= relevant_inspections <= upper:
            return group
    return None


def build_exact_population() -> tuple[dict[str, float], dict[str, int], dict[str, int], dict[str, Any]]:
    denominator_by_dot: dict[str, float] = defaultdict(float)
    relevant_count_by_dot: dict[str, int] = defaultdict(int)

    inspection_rows = 0
    for row in stream_export(
        INSPECTION_ID,
        "SELECT dot_number,unique_id,time_weight WHERE vh_maint_insp='true'",
    ):
        dot = str(row.get("dot_number") or "").strip()
        if not dot:
            continue
        weight = number(row.get("time_weight")) or 0.0
        denominator_by_dot[dot] += weight
        relevant_count_by_dot[dot] += 1
        inspection_rows += 1
        if inspection_rows % 500_000 == 0:
            print(f"  inspection rows: {inspection_rows:,}", flush=True)

    if inspection_rows != EXPECTED_RELEVANT_INSPECTIONS:
        raise RuntimeError(
            f"Relevant Vehicle Maintenance inspection count changed during validation: "
            f"expected {EXPECTED_RELEVANT_INSPECTIONS:,}, streamed {inspection_rows:,}"
        )

    # Store one compact mutable pair per inspection that has one or more VM violations:
    # [severity sum, time weight]. This avoids retaining all 5.1M source rows.
    violation_by_inspection: dict[tuple[str, str], list[float]] = {}
    violation_rows = 0
    missing_identity = 0
    missing_time_weight = 0
    for row in stream_export(
        VIOLATION_ID,
        "SELECT dot_number,unique_id,severity_weight,oos_weight,time_weight,total_severity_wght "
        "WHERE basic_desc='Vehicle Maintenance'",
    ):
        dot = str(row.get("dot_number") or "").strip()
        unique_id = str(row.get("unique_id") or "").strip()
        if not dot or not unique_id:
            missing_identity += 1
            continue
        total = number(row.get("total_severity_wght"))
        severity = total if total is not None else (number(row.get("severity_weight")) or 0.0) + (number(row.get("oos_weight")) or 0.0)
        time_weight = number(row.get("time_weight"))
        if time_weight is None:
            missing_time_weight += 1
            time_weight = 0.0
        key = (dot, unique_id)
        current = violation_by_inspection.get(key)
        if current is None:
            violation_by_inspection[key] = [severity, time_weight]
        else:
            current[0] += severity
            if time_weight > current[1]:
                current[1] = time_weight
        violation_rows += 1
        if violation_rows % 500_000 == 0:
            print(f"  violation rows: {violation_rows:,}; unique inspections: {len(violation_by_inspection):,}", flush=True)

    if violation_rows != EXPECTED_VM_VIOLATIONS:
        raise RuntimeError(
            f"Vehicle Maintenance violation count changed during validation: "
            f"expected {EXPECTED_VM_VIOLATIONS:,}, streamed {violation_rows:,}"
        )
    if missing_identity or missing_time_weight:
        raise RuntimeError(
            f"Unexpected incomplete VM violation rows: missing identity={missing_identity}, "
            f"missing time weight={missing_time_weight}"
        )

    numerator_by_dot: dict[str, float] = defaultdict(float)
    violation_inspection_count_by_dot: dict[str, int] = defaultdict(int)
    capped_inspections = 0
    for (dot, _unique_id), (severity_sum, time_weight) in violation_by_inspection.items():
        if severity_sum > 30:
            capped_inspections += 1
        numerator_by_dot[dot] += min(30.0, severity_sum) * time_weight
        violation_inspection_count_by_dot[dot] += 1

    exact_measure_by_dot: dict[str, float] = {}
    group_by_dot: dict[str, int] = {}
    group_population: dict[int, int] = defaultdict(int)
    for dot, denominator in denominator_by_dot.items():
        relevant_count = relevant_count_by_dot[dot]
        group = safety_event_group(relevant_count)
        if group is None or denominator <= 0:
            continue
        measure = numerator_by_dot.get(dot, 0.0) / denominator
        exact_measure_by_dot[dot] = measure
        group_by_dot[dot] = group
        group_population[group] += 1

    diagnostics = {
        "streamed_relevant_inspection_rows": inspection_rows,
        "streamed_vm_violation_rows": violation_rows,
        "unique_vm_violation_inspections": len(violation_by_inspection),
        "capped_vm_inspections": capped_inspections,
        "carrier_measures": len(exact_measure_by_dot),
        "group_population": dict(sorted(group_population.items())),
    }
    return exact_measure_by_dot, group_by_dot, violation_inspection_count_by_dot, diagnostics


def fetch_page(dot_number: str) -> dict[str, Any] | None:
    url = f"{SMS}/{dot_number}/BASIC/VehicleMaint.aspx"
    try:
        with request(url, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return {"dot_number": dot_number, "url": url, "error": f"{type(exc).__name__}: {exc}"}

    parser = TextExtractor()
    parser.feed(raw)
    text = re.sub(r"\s+", " ", parser.text())
    if "Public Passenger Carrier View" not in text:
        return None
    snapshot_match = re.search(r"Summary of Activities \(as of\s*([0-9/]+), updated monthly\)", text, re.I)
    measure_match = re.search(r"On-Road Performance.*?Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    percentile_match = re.search(r"Percentile:\s*(\d+(?:\.\d+)?)%", text, re.I)
    group_match = re.search(r"Safety Event Group:\s*([^%]+?)(?:65%|Intervention|Scale 0 to 100)", text, re.I)
    if not measure_match or not percentile_match:
        return None
    return {
        "dot_number": dot_number,
        "url": url,
        "snapshot": snapshot_match.group(1) if snapshot_match else None,
        "measure": float(measure_match.group(1)),
        "percentile": float(percentile_match.group(1)),
        "group_text": group_match.group(1).strip() if group_match else None,
    }


def percentile_map(measures: list[float], mode: str) -> dict[float, float]:
    ordered = sorted(measures)
    n = len(ordered)
    if n == 0:
        return {}
    if n == 1:
        return {ordered[0]: 0.0}
    positions: dict[float, list[int]] = defaultdict(list)
    for index, measure in enumerate(ordered):
        positions[measure].append(index)
    output: dict[float, float] = {}
    for measure, indexes in positions.items():
        if mode == "min":
            position = min(indexes)
        elif mode == "max":
            position = max(indexes)
        elif mode == "average":
            position = statistics.mean(indexes)
        else:
            raise ValueError(mode)
        output[measure] = 100.0 * position / (n - 1)
    return output


def summarize(errors: list[float]) -> dict[str, Any]:
    absolute = [abs(value) for value in errors]
    return {
        "n": len(errors),
        "exact_integer": sum(value <= 1e-9 for value in absolute),
        "within_1": sum(value <= 1.0000001 for value in absolute),
        "mae": sum(absolute) / len(absolute) if absolute else None,
        "max_abs": max(absolute) if absolute else None,
    }


def main() -> int:
    started = time.monotonic()
    exact_measure_by_dot, group_by_dot, violation_count_by_dot, population_diag = build_exact_population()

    measures_by_group: dict[int, list[float]] = defaultdict(list)
    for dot, measure in exact_measure_by_dot.items():
        measures_by_group[group_by_dot[dot]].append(measure)

    maps: dict[tuple[int, str], dict[float, float]] = {}
    for group, measures in measures_by_group.items():
        for mode in ("min", "max", "average"):
            maps[(group, mode)] = percentile_map(measures, mode)

    live_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for result in pool.map(fetch_page, VERIFY_DOTS):
            if result:
                live_results.append(result)

    method_errors: dict[str, list[float]] = defaultdict(list)
    comparisons: list[dict[str, Any]] = []
    snapshots: set[str] = set()
    fetch_errors: list[dict[str, Any]] = []
    for live in live_results:
        if live.get("error"):
            fetch_errors.append(live)
            continue
        dot = str(live["dot_number"])
        if live.get("snapshot"):
            snapshots.add(str(live["snapshot"]))
        exact_measure = exact_measure_by_dot.get(dot)
        group = group_by_dot.get(dot)
        if exact_measure is None or group is None:
            continue
        candidates: dict[str, float] = {}
        for mode in ("min", "max", "average"):
            raw = maps[(group, mode)][exact_measure]
            for transform, value in {
                "raw": raw,
                "round": float(round(raw)),
                "floor": float(math.floor(raw + 1e-12)),
                "ceil": float(math.ceil(raw - 1e-12)),
            }.items():
                key = f"{mode}_{transform}"
                candidates[key] = value
                method_errors[key].append(value - float(live["percentile"]))
        comparisons.append({
            **live,
            "exact_measure": exact_measure,
            "display_measure_delta": exact_measure - float(live["measure"]),
            "group": group,
            "relevant_inspections": next((count for d, count in [] if d == dot), None),
            "violation_inspections": violation_count_by_dot.get(dot, 0),
            "candidates": candidates,
        })

    ranking = sorted(
        ({"method": method, **summarize(errors)} for method, errors in method_errors.items()),
        key=lambda item: (item["mae"] if item["mae"] is not None else math.inf, item["max_abs"] if item["max_abs"] is not None else math.inf),
    )

    best = ranking[0] if ranking else None
    payload = {
        "status": "diagnostic_only",
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "population": population_diag,
        "live_snapshots": sorted(snapshots),
        "verification_targets": len(VERIFY_DOTS),
        "numeric_live_comparisons": len(comparisons),
        "fetch_errors": fetch_errors,
        "best_methods": ranking[:12],
        "best_method": best,
        "comparisons": comparisons,
    }
    print(json.dumps(payload, indent=2), flush=True)

    if len(comparisons) < 8:
        print("Insufficient live percentile comparisons to interpret the full-population rank.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
