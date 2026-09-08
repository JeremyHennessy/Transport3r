#!/usr/bin/env python3
"""Compare candidate SMS percentile rank transforms to live FMCSA passenger pages.

The public passenger bulk file exposes measures and safety-event counts but currently
leaves percentile values blank. We therefore use passenger rows only to select public
carriers whose live SMS pages expose percentiles. The ranking population is built from
the two PassProperty output files (AB + C), which together cover the current active
property/passenger SMS carrier universe. This matters because FMCSA safety-event groups
are not separate industry/commodity ranking universes.

Diagnostic only: exits zero and never promotes a percentile formula by itself.
"""

from __future__ import annotations

import concurrent.futures
import html.parser
import json
import math
import re
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any

DATAHUB = "https://data.transportation.gov/resource"
SMS = "https://ai.fmcsa.dot.gov/SMS/Carrier"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
PASSENGER_OUTPUT_ID = "m3ry-qcip"
RANKING_OUTPUT_IDS = ("4y6x-dmck", "h9zy-gjn8")
EXPECTED_SNAPSHOT = "July 31, 2026"
PAGE_SIZE = 50_000
MAX_SOURCE_ROWS = 1_500_000

RULE = {
    "name": "Vehicle Maintenance",
    "measure": "veh_maint_measure",
    "event_count": "vehicle_insp_total",
    "violation_inspections": "veh_maint_insp_w_viol",
    "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    "page": "VehicleMaint.aspx",
}


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


def fetch(url: str, timeout: int = 30, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(min(2.0, 0.5 * (2 ** (attempt - 1))))
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


def datahub_rows(source_id: str, fields: list[str]) -> list[dict[str, Any]]:
    """Read a complete current DataHub source projection with explicit pagination."""
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "$select": ",".join(fields),
            "$limit": str(PAGE_SIZE),
            "$offset": str(offset),
            "$order": "dot_number ASC",
        })
        payload = json.loads(fetch(f"{DATAHUB}/{source_id}.json?{params}", timeout=45, attempts=3).decode("utf-8"))
        if not isinstance(payload, list):
            raise RuntimeError(f"{source_id} returned non-array JSON")
        rows.extend(payload)
        if len(rows) > MAX_SOURCE_ROWS:
            raise RuntimeError(f"{source_id} exceeded safety cap of {MAX_SOURCE_ROWS:,} projected rows")
        if len(payload) < PAGE_SIZE:
            return rows
        offset += len(payload)


def passenger_rows() -> list[dict[str, Any]]:
    return datahub_rows(PASSENGER_OUTPUT_ID, ["dot_number", RULE["measure"], RULE["event_count"], RULE["violation_inspections"]])


def ranking_rows() -> list[dict[str, Any]]:
    fields = ["dot_number", RULE["measure"], RULE["event_count"]]
    rows: list[dict[str, Any]] = []
    for source_id in RANKING_OUTPUT_IDS:
        rows.extend(datahub_rows(source_id, fields))

    # Operation classes A/B and C are mutually exclusive, but fail loudly if the
    # current output contract unexpectedly duplicates a carrier across files.
    seen: set[str] = set()
    duplicates: list[str] = []
    for row in rows:
        dot = str(row.get("dot_number") or "").strip()
        if not dot:
            continue
        if dot in seen:
            duplicates.append(dot)
        seen.add(dot)
    if duplicates:
        raise RuntimeError(f"Unexpected duplicate USDOTs across ranking outputs: {duplicates[:10]}")
    return rows


def event_group(row: dict[str, Any]) -> int | None:
    count = number(row.get(RULE["event_count"]))
    if count is None:
        return None
    for group, lower, upper in RULE["groups"]:
        if lower <= count <= upper:
            return group
    return None


def page_result(dot_number: str) -> dict[str, Any] | None:
    url = f"{SMS}/{dot_number}/BASIC/{RULE['page']}"
    raw = fetch(url, timeout=12, attempts=2).decode("utf-8", errors="replace")
    parser = TextExtractor()
    parser.feed(raw)
    text = re.sub(r"\s+", " ", parser.text())
    if "Public Passenger Carrier View" not in text or EXPECTED_SNAPSHOT not in text:
        return None
    measure_match = re.search(r"On-Road Performance.*?Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    percentile_match = re.search(r"Percentile:\s*(\d+(?:\.\d+)?)%", text, re.I)
    group_match = re.search(r"Safety Event Group:\s*([^%]+?)(?:65%|Intervention|Scale 0 to 100)", text, re.I)
    if not measure_match or not percentile_match:
        return None
    return {
        "dot_number": dot_number,
        "url": url,
        "measure": float(measure_match.group(1)),
        "percentile": float(percentile_match.group(1)),
        "group_text": group_match.group(1).strip() if group_match else None,
    }


def quantile_sample(rows: list[dict[str, Any]], per_group: int = 4) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    by_group: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        measure = number(row.get(RULE["measure"]))
        violations = number(row.get(RULE["violation_inspections"]))
        group = event_group(row)
        # FMCSA does not publish a Vehicle Maintenance percentile until at least
        # five relevant inspections resulted in a VM violation. This filter is
        # only for selecting verification pages; it is not applied to the rank population.
        if measure is None or group is None or violations is None or violations < 5:
            continue
        by_group[group].append(row)

    for group, members in sorted(by_group.items()):
        members.sort(key=lambda row: (number(row.get(RULE["measure"])) or 0.0, str(row.get("dot_number"))))
        if not members:
            continue
        count = min(per_group, len(members))
        indexes = sorted({round(index * (len(members) - 1) / max(1, count - 1)) for index in range(count)})
        selected.extend(members[index] for index in indexes)
    return selected


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
        "within_2": sum(value <= 2.0000001 for value in absolute),
        "mae": sum(absolute) / len(absolute) if absolute else None,
        "max_abs": max(absolute) if absolute else None,
    }


def fetch_sample(row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None, str | None]:
    dot_number = str(row.get("dot_number") or "").strip()
    if not dot_number:
        return row, None, "missing dot number"
    try:
        return row, page_result(dot_number), None
    except Exception as exc:  # noqa: BLE001
        return row, None, f"{type(exc).__name__}: {exc}"


def main() -> int:
    candidates = passenger_rows()
    all_rank_rows = ranking_rows()

    population: dict[int, list[float]] = defaultdict(list)
    for row in all_rank_rows:
        group = event_group(row)
        measure = number(row.get(RULE["measure"]))
        if group is not None and measure is not None:
            population[group].append(measure)

    samples = quantile_sample(candidates)
    live: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_sample, row) for row in samples]
        for future in concurrent.futures.as_completed(futures):
            row, result, error = future.result()
            dot_number = str(row.get("dot_number") or "").strip()
            if error:
                failures.append({"dot_number": dot_number, "error": error})
                continue
            if result is None:
                continue
            bulk_measure = number(row.get(RULE["measure"]))
            group = event_group(row)
            if bulk_measure is None or group is None:
                continue
            result["bulk_measure"] = bulk_measure
            result["group"] = group
            result["measure_delta"] = result["measure"] - bulk_measure
            live.append(result)

    live.sort(key=lambda row: (row["group"], row["bulk_measure"], row["dot_number"]))
    failures.sort(key=lambda row: row["dot_number"])

    method_errors: dict[str, list[float]] = defaultdict(list)
    comparisons: list[dict[str, Any]] = []
    maps: dict[tuple[int, str], dict[float, float]] = {}
    for group, measures in population.items():
        for mode in ("min", "max", "average"):
            maps[(group, mode)] = percentile_map(measures, mode)

    for row in live:
        candidates_by_method: dict[str, float] = {}
        for mode in ("min", "max", "average"):
            raw = maps[(row["group"], mode)].get(row["bulk_measure"])
            if raw is None:
                continue
            for transform, value in {
                "raw": raw,
                "round": float(round(raw)),
                "floor": float(math.floor(raw + 1e-12)),
                "ceil": float(math.ceil(raw - 1e-12)),
            }.items():
                key = f"{mode}_{transform}"
                candidates_by_method[key] = value
                method_errors[key].append(value - row["percentile"])
        comparisons.append({**row, "candidates": candidates_by_method})

    ranking = sorted(
        ({"method": method, **summarize(errors)} for method, errors in method_errors.items()),
        key=lambda item: (item["mae"] if item["mae"] is not None else math.inf, item["max_abs"] if item["max_abs"] is not None else math.inf),
    )
    print(json.dumps({
        "status": "diagnostic_only",
        "snapshot": EXPECTED_SNAPSHOT,
        "passenger_candidate_rows": len(candidates),
        "ranking_rows": len(all_rank_rows),
        "sample_candidates": len(samples),
        "live_numeric_percentiles": len(live),
        "fetch_failures": failures,
        "group_population": {str(group): len(measures) for group, measures in sorted(population.items())},
        "best_methods": ranking[:10],
        "comparisons": comparisons[:40],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
