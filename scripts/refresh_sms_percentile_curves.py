#!/usr/bin/env python3
"""Capture and validate FMCSA's official SMS measure→percentile conversion curves.

FMCSA's public SMS Help Center explicitly directs users to the BASIC "Measure vs.
Percentile" graph as the conversion chart between a carrier measure and percentile.
For passenger carriers the BASIC percentile is also public. This script uses those two
public surfaces to avoid reverse-engineering FMCSA's internal peer-ranking tie logic.

For HOS Compliance, Driver Fitness, and Vehicle Maintenance, the job:
1. Reads current passenger SMS bulk output to discover data-sufficient carriers in
   each current v3.21 safety-event group.
2. Fetches the public BASIC page and its MeasurePercentileGraph page.
3. Requires the BASIC page snapshot to match the current SMS homepage snapshot.
4. Parses the official graph's Measure | Percentile table.
5. Requires multiple carriers in the same BASIC/group to return an identical curve.
6. Determines the only lookup convention (exact/floor/ceiling/nearest) that reproduces
   all sampled official passenger percentiles.
7. Writes a compact versioned curve artifact for Transport3r.

The artifact is source evidence. Property-carrier percentiles derived from these curves
must be labelled TRANSPORT_CALCULATED, never official FMCSA property percentiles.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import html
from html.parser import HTMLParser
import json
import math
import pathlib
import re
import time
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "public" / "data" / "sms-percentile-curves.json"
DATAHUB = "https://data.transportation.gov/resource"
SMS_ROOT = "https://ai.fmcsa.dot.gov/SMS"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
PASSENGER_OUTPUT_ID = "m3ry-qcip"
RULESET = "SMS_3_21_CURRENT"
WORKERS = 6
CANDIDATES_PER_GROUP = 6
MIN_VALIDATORS_PER_GROUP = 2

BASICS: dict[str, dict[str, Any]] = {
    "hos": {
        "label": "Hours-of-Service Compliance",
        "path": "HOSCompliance",
        "measure_field": "hos_driv_measure",
        "percentile_field": "hos_driv_pct",
        "event_field": "driver_insp_total",
        "violation_inspection_field": "hos_driv_insp_w_viol",
        "min_violation_inspections": 3,
        "groups": [(1, 3, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "driver_fitness": {
        "label": "Driver Fitness",
        "path": "DriverFitness",
        "measure_field": "driv_fit_measure",
        "percentile_field": "driv_fit_pct",
        "event_field": "driver_insp_total",
        "violation_inspection_field": "driv_fit_insp_w_viol",
        "min_violation_inspections": 5,
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "vehicle_maintenance": {
        "label": "Vehicle Maintenance",
        "path": "VehicleMaint",
        "measure_field": "veh_maint_measure",
        "percentile_field": "veh_maint_pct",
        "event_field": "vehicle_insp_total",
        "violation_inspection_field": "veh_maint_insp_w_viol",
        "min_violation_inspections": 5,
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
}


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def fetch_bytes(url: str, timeout: int = 15, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - preserve exact upstream failure
            last_error = exc
            if attempt < attempts:
                time.sleep(min(3.0, 0.5 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def fetch_json(source_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    payload = json.loads(fetch_bytes(f"{DATAHUB}/{source_id}.json?{query}", timeout=30).decode("utf-8"))
    if not isinstance(payload, list):
        raise RuntimeError(f"{source_id} returned non-array JSON")
    return payload


def strip_html(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def current_sms_snapshot() -> str:
    text = strip_html(fetch_bytes(f"{SMS_ROOT}/"))
    match = re.search(r"Data current as of:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    if not match:
        raise RuntimeError("Could not determine current SMS snapshot date")
    return match.group(1)


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


def group_for(event_total: int, groups: list[tuple[int, int, float]]) -> int | None:
    for group, minimum, maximum in groups:
        if minimum <= event_total <= maximum:
            return group
    return None


def parse_basic_page(raw: bytes) -> dict[str, Any]:
    text = strip_html(raw)
    snapshot_match = re.search(r"24-month record ending\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    measure_match = re.search(r"On-Road Performance\s+Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if not measure_match:
        measure_match = re.search(r"Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    percentile_match = re.search(r"Percentile:\s*([0-9]+(?:\.[0-9]+)?)%", text, re.I)
    if not percentile_match:
        percentile_match = re.search(r"([0-9]+(?:\.[0-9]+)?)%\s+Percentile", text, re.I)
    group_match = re.search(r"Safety Event Group:\s*([^%]+?)(?:Investigation Results|Carrier Measure Over Time|More Info)", text, re.I)
    return {
        "snapshot": snapshot_match.group(1) if snapshot_match else None,
        "measure": float(measure_match.group(1)) if measure_match else None,
        "percentile": float(percentile_match.group(1)) if percentile_match else None,
        "group_text": group_match.group(1).strip() if group_match else None,
    }


def parse_curve(raw: bytes) -> list[dict[str, float]]:
    parser = TableParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    for table in parser.tables:
        header_index = None
        for index, row in enumerate(table):
            normalized = [cell.strip().lower() for cell in row]
            if len(normalized) >= 2 and normalized[0] == "measure" and normalized[1] == "percentile":
                header_index = index
                break
        if header_index is None:
            continue
        points: list[dict[str, float]] = []
        for row in table[header_index + 1 :]:
            if len(row) < 2:
                continue
            measure = number(row[0])
            percentile = number(row[1].rstrip("%"))
            if measure is None or percentile is None:
                continue
            points.append({"measure": measure, "percentile": percentile})
        if len(points) >= 90:
            points.sort(key=lambda point: point["measure"])
            return points
    raise RuntimeError("Could not parse Measure | Percentile conversion table")


def curve_signature(curve: list[dict[str, float]]) -> str:
    return json.dumps(curve, sort_keys=True, separators=(",", ":"))


def lookup(curve: list[dict[str, float]], measure: float, mode: str) -> float:
    if not curve:
        raise ValueError("Empty percentile curve")
    exact = [point for point in curve if abs(point["measure"] - measure) < 1e-9]
    if mode == "exact":
        if not exact:
            raise KeyError(measure)
        return exact[0]["percentile"]
    if exact:
        return exact[0]["percentile"]
    if mode == "floor":
        choices = [point for point in curve if point["measure"] <= measure]
        return (choices[-1] if choices else curve[0])["percentile"]
    if mode == "ceiling":
        choices = [point for point in curve if point["measure"] >= measure]
        return (choices[0] if choices else curve[-1])["percentile"]
    if mode == "nearest":
        return min(curve, key=lambda point: (abs(point["measure"] - measure), point["measure"]))["percentile"]
    raise ValueError(mode)


def candidate_rows(rows: list[dict[str, Any]], rule: dict[str, Any], group: int) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        measure = number(row.get(rule["measure_field"]))
        if measure is None or measure <= 0:
            continue
        if integer(row.get(rule["violation_inspection_field"])) < rule["min_violation_inspections"]:
            continue
        event_total = integer(row.get(rule["event_field"]))
        if group_for(event_total, rule["groups"]) != group:
            continue
        candidates.append({
            "dot_number": str(row.get("dot_number") or "").strip(),
            "bulk_measure": measure,
            "event_total": event_total,
            "violation_inspections": integer(row.get(rule["violation_inspection_field"])),
        })
    candidates = [row for row in candidates if row["dot_number"]]
    candidates.sort(key=lambda row: (row["bulk_measure"], row["dot_number"]))
    if len(candidates) <= CANDIDATES_PER_GROUP:
        return candidates
    selected: list[dict[str, Any]] = []
    for index in range(CANDIDATES_PER_GROUP):
        position = round(index * (len(candidates) - 1) / (CANDIDATES_PER_GROUP - 1))
        selected.append(candidates[position])
    return list({row["dot_number"]: row for row in selected}.values())


def fetch_observation(basic: str, rule: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    dot = candidate["dot_number"]
    base = f"{SMS_ROOT}/Carrier/{dot}/BASIC/{rule['path']}"
    basic_raw = fetch_bytes(f"{base}.aspx")
    graph_raw = fetch_bytes(f"{base}/MeasurePercentileGraph.aspx")
    return {
        **candidate,
        "basic": basic,
        "basic_url": f"{base}.aspx",
        "graph_url": f"{base}/MeasurePercentileGraph.aspx",
        "page": parse_basic_page(basic_raw),
        "curve": parse_curve(graph_raw),
    }


def main() -> int:
    snapshot = current_sms_snapshot()
    passenger_rows = fetch_json(PASSENGER_OUTPUT_ID, {"$limit": "50000"})
    output_basics: dict[str, Any] = {}
    total_validations = 0

    for basic, rule in BASICS.items():
        group_outputs: dict[str, Any] = {}
        for group, minimum, maximum in rule["groups"]:
            candidates = candidate_rows(passenger_rows, rule, group)
            if len(candidates) < MIN_VALIDATORS_PER_GROUP:
                raise RuntimeError(f"{basic} group {group}: only {len(candidates)} candidate passenger carriers")

            observations: list[dict[str, Any]] = []
            failures: list[dict[str, str]] = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(WORKERS, len(candidates))) as pool:
                futures = [pool.submit(fetch_observation, basic, rule, candidate) for candidate in candidates]
                for future in concurrent.futures.as_completed(futures):
                    try:
                        observation = future.result()
                    except Exception as exc:  # noqa: BLE001
                        failures.append({"error": f"{type(exc).__name__}: {exc}"})
                        continue
                    page = observation["page"]
                    if page["snapshot"] != snapshot:
                        failures.append({"dot_number": observation["dot_number"], "error": f"snapshot {page['snapshot']!r} != {snapshot!r}"})
                        continue
                    if page["measure"] is None or page["percentile"] is None:
                        failures.append({"dot_number": observation["dot_number"], "error": "public measure/percentile unavailable"})
                        continue
                    if abs(page["measure"] - observation["bulk_measure"]) > 0.02:
                        failures.append({"dot_number": observation["dot_number"], "error": f"bulk/live measure mismatch {observation['bulk_measure']} vs {page['measure']}"})
                        continue
                    observations.append(observation)

            if len(observations) < MIN_VALIDATORS_PER_GROUP:
                raise RuntimeError(f"{basic} group {group}: only {len(observations)} validated public observations; failures={failures[:4]}")

            signatures: dict[str, int] = {}
            for observation in observations:
                signature = curve_signature(observation["curve"])
                signatures[signature] = signatures.get(signature, 0) + 1
            winning_signature, winning_count = max(signatures.items(), key=lambda item: item[1])
            matching_curve_observations = [observation for observation in observations if curve_signature(observation["curve"]) == winning_signature]
            if winning_count < MIN_VALIDATORS_PER_GROUP:
                raise RuntimeError(f"{basic} group {group}: public graph curves disagree across validators")
            curve = matching_curve_observations[0]["curve"]

            mode_results: dict[str, dict[str, Any]] = {}
            for mode in ("exact", "floor", "ceiling", "nearest"):
                comparisons: list[dict[str, Any]] = []
                for observation in matching_curve_observations:
                    page = observation["page"]
                    try:
                        predicted = lookup(curve, float(page["measure"]), mode)
                    except KeyError:
                        continue
                    comparisons.append({
                        "dot_number": observation["dot_number"],
                        "measure": page["measure"],
                        "official_percentile": page["percentile"],
                        "predicted_percentile": predicted,
                        "error": abs(predicted - page["percentile"]),
                    })
                mode_results[mode] = {
                    "comparisons": comparisons,
                    "match_count": sum(item["error"] < 0.001 for item in comparisons),
                    "max_error": max((item["error"] for item in comparisons), default=None),
                }

            supported_modes = [
                mode for mode, result in mode_results.items()
                if len(result["comparisons"]) >= MIN_VALIDATORS_PER_GROUP and result["match_count"] == len(result["comparisons"])
            ]
            if not supported_modes:
                raise RuntimeError(f"{basic} group {group}: no curve lookup mode reproduced public percentiles; {mode_results}")
            # Prefer the least assumptive deterministic ordering if multiple modes are
            # equivalent because every sampled measure lands exactly on a curve point.
            lookup_mode = next(mode for mode in ("exact", "ceiling", "floor", "nearest") if mode in supported_modes)

            representative = matching_curve_observations[0]
            group_outputs[str(group)] = {
                "event_min": minimum,
                "event_max": None if math.isinf(maximum) else maximum,
                "curve_source": representative["graph_url"],
                "representative_dot_number": representative["dot_number"],
                "lookup_mode": lookup_mode,
                "validator_count": len(matching_curve_observations),
                "validator_dot_numbers": [observation["dot_number"] for observation in matching_curve_observations],
                "curve": curve,
            }
            total_validations += len(matching_curve_observations)

        output_basics[basic] = {
            "label": rule["label"],
            "group_basis": rule["event_field"],
            "groups": group_outputs,
        }

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "sms_snapshot": snapshot,
        "ruleset": RULESET,
        "source": "FMCSA SMS public Measure vs. Percentile graphs",
        "passenger_output_source_id": PASSENGER_OUTPUT_ID,
        "validation_count": total_validations,
        "basics": output_basics,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": "ok",
        "sms_snapshot": snapshot,
        "ruleset": RULESET,
        "validation_count": total_validations,
        "basic_count": len(output_basics),
        "group_count": sum(len(basic["groups"]) for basic in output_basics.values()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
