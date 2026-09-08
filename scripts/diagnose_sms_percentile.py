#!/usr/bin/env python3
"""Diagnose FMCSA SMS percentile ranking against official passenger-carrier output.

This is intentionally diagnostic: it compares several rank/tie transforms against the
published passenger BASIC percentiles. It exits zero so we can inspect evidence first
and only promote a formula into the production SMS engine after one method is clearly
supported by the current FMCSA output.
"""

from __future__ import annotations

import json
import math
import statistics
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from typing import Any, Callable

BASE = "https://data.transportation.gov/resource"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
PASSENGER_OUTPUT_ID = "m3ry-qcip"
PAGE_SIZE = 50000

BASICS = {
    "hos": {
        "measure": "hos_driv_measure",
        "percentile": "hos_driv_pct",
        "count": "driver_insp_total",
        "groups": [(1, 3, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "driver_fitness": {
        "measure": "driv_fit_measure",
        "percentile": "driv_fit_pct",
        "count": "driver_insp_total",
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "vehicle_maintenance": {
        "measure": "veh_maint_measure",
        "percentile": "veh_maint_pct",
        "count": "vehicle_insp_total",
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "controlled_substances": {
        "measure": "contr_subst_measure",
        "percentile": "contr_subst_pct",
        "count": "contr_subst_insp_w_viol",
        "groups": [(1, 1, 1), (2, 2, 2), (3, 3, 3), (4, 4, math.inf)],
    },
}


def fetch_page(offset: int) -> list[dict[str, Any]]:
    fields = ["dot_number", "driver_insp_total", "vehicle_insp_total"]
    for rule in BASICS.values():
        fields.extend([rule["measure"], rule["percentile"], rule["count"]])
    select = ",".join(dict.fromkeys(fields))
    params = urllib.parse.urlencode({"$select": select, "$limit": str(PAGE_SIZE), "$offset": str(offset)})
    url = f"{BASE}/{PASSENGER_OUTPUT_ID}.json?{params}"
    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
            if not isinstance(payload, list):
                raise RuntimeError("Passenger output returned non-array JSON")
            return payload
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 3:
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def fetch_all() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = fetch_page(offset)
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        offset += len(batch)


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", ""))
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def event_group(rule: dict[str, Any], row: dict[str, Any]) -> int | None:
    count = number(row.get(rule["count"]))
    if count is None:
        return None
    for group, lower, upper in rule["groups"]:
        if lower <= count <= upper:
            return group
    return None


def raw_rank_percentiles(measures: list[float], tie_mode: str) -> dict[float, float]:
    sorted_measures = sorted(measures)
    n = len(sorted_measures)
    if n <= 1:
        return {sorted_measures[0]: 0.0} if n == 1 else {}
    positions: dict[float, list[int]] = defaultdict(list)
    for index, measure in enumerate(sorted_measures):
        positions[measure].append(index)
    result: dict[float, float] = {}
    dense_order = {measure: index for index, measure in enumerate(sorted(positions))}
    dense_denominator = max(1, len(dense_order) - 1)
    for measure, indexes in positions.items():
        if tie_mode == "min":
            rank_index = min(indexes)
            result[measure] = 100.0 * rank_index / (n - 1)
        elif tie_mode == "max":
            rank_index = max(indexes)
            result[measure] = 100.0 * rank_index / (n - 1)
        elif tie_mode == "average":
            rank_index = statistics.mean(indexes)
            result[measure] = 100.0 * rank_index / (n - 1)
        elif tie_mode == "dense":
            result[measure] = 100.0 * dense_order[measure] / dense_denominator
        else:
            raise ValueError(tie_mode)
    return result


def transforms(raw: float) -> dict[str, float]:
    return {
        "raw": raw,
        "round_int": float(round(raw)),
        "floor_int": float(math.floor(raw + 1e-12)),
        "ceil_int": float(math.ceil(raw - 1e-12)),
        "round_1dp": round(raw, 1),
    }


def summarize(errors: list[float]) -> dict[str, Any]:
    if not errors:
        return {"n": 0}
    abs_errors = [abs(value) for value in errors]
    return {
        "n": len(errors),
        "exact": sum(value <= 1e-9 for value in abs_errors),
        "within_0_1": sum(value <= 0.1000001 for value in abs_errors),
        "within_0_5": sum(value <= 0.5000001 for value in abs_errors),
        "within_1": sum(value <= 1.0000001 for value in abs_errors),
        "mae": sum(abs_errors) / len(abs_errors),
        "max_abs": max(abs_errors),
    }


def main() -> int:
    rows = fetch_all()
    diagnostics: dict[str, Any] = {
        "status": "diagnostic_only",
        "passenger_rows": len(rows),
        "basics": {},
    }

    for basic, rule in BASICS.items():
        by_group: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            measure = number(row.get(rule["measure"]))
            group = event_group(rule, row)
            if measure is None or group is None:
                continue
            by_group[group].append(row)

        method_errors: dict[str, list[float]] = defaultdict(list)
        group_summary: dict[str, Any] = {}
        sample_disagreements: list[dict[str, Any]] = []

        for group, population in sorted(by_group.items()):
            measures = [number(row.get(rule["measure"])) for row in population]
            clean_measures = [value for value in measures if value is not None]
            official_rows = [row for row in population if number(row.get(rule["percentile"])) is not None]
            group_summary[str(group)] = {
                "ranking_population": len(clean_measures),
                "official_percentile_rows": len(official_rows),
                "unique_measures": len(set(clean_measures)),
            }
            if len(clean_measures) < 2:
                continue

            for tie_mode in ("min", "max", "average", "dense"):
                ranked = raw_rank_percentiles(clean_measures, tie_mode)
                for row in official_rows:
                    measure = number(row.get(rule["measure"]))
                    official = number(row.get(rule["percentile"]))
                    if measure is None or official is None:
                        continue
                    raw = ranked[measure]
                    for transform_name, candidate in transforms(raw).items():
                        key = f"{tie_mode}_{transform_name}"
                        method_errors[key].append(candidate - official)

            if len(sample_disagreements) < 12:
                ranked = raw_rank_percentiles(clean_measures, "average")
                for row in official_rows:
                    measure = number(row.get(rule["measure"]))
                    official = number(row.get(rule["percentile"]))
                    if measure is None or official is None:
                        continue
                    candidate = round(ranked[measure])
                    if abs(candidate - official) > 0.5:
                        sample_disagreements.append({
                            "dot_number": row.get("dot_number"),
                            "group": group,
                            "measure": measure,
                            "official": official,
                            "average_round_int": candidate,
                        })
                        if len(sample_disagreements) >= 12:
                            break

        ranked_methods = sorted(
            ((name, summarize(errors)) for name, errors in method_errors.items()),
            key=lambda item: (item[1].get("mae", math.inf), item[1].get("max_abs", math.inf)),
        )
        diagnostics["basics"][basic] = {
            "groups": group_summary,
            "best_methods": [{"method": name, **stats} for name, stats in ranked_methods[:8]],
            "sample_average_rank_disagreements": sample_disagreements,
        }

    print(json.dumps(diagnostics, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
