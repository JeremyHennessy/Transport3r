#!/usr/bin/env python3
"""Capture and validate FMCSA's official SMS measure→percentile conversion curves.

FMCSA's Help Center directs users to each BASIC's public "Measure vs. Percentile"
graph as the conversion chart. Passenger-carrier BASIC percentiles are also public.
Transport3r uses those two public surfaces instead of reverse-engineering FMCSA tie or
ranking behavior.

For HOS Compliance, Driver Fitness, and Vehicle Maintenance, this job discovers public
passenger carriers in every v3.21 safety-event group, parses their BASIC and graph
pages, requires multiple carriers in the same group to return the same curve, and
validates deterministic curve lookup against their published percentiles.

The graph artifact is source evidence. Any property percentile derived from it must be
labelled TRANSPORT_CALCULATED, never an official FMCSA property percentile.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
from html.parser import HTMLParser
import html
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
        "event_field": "driver_insp_total",
        "violation_field": "hos_driv_insp_w_viol",
        "min_violations": 3,
        "groups": [(1, 3, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "driver_fitness": {
        "label": "Driver Fitness",
        "path": "DriverFitness",
        "measure_field": "driv_fit_measure",
        "event_field": "driver_insp_total",
        "violation_field": "driv_fit_insp_w_viol",
        "min_violations": 5,
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
    "vehicle_maintenance": {
        "label": "Vehicle Maintenance",
        "path": "VehicleMaint",
        "measure_field": "veh_maint_measure",
        "event_field": "vehicle_insp_total",
        "violation_field": "veh_maint_insp_w_viol",
        "min_violations": 5,
        "groups": [(1, 5, 10), (2, 11, 20), (3, 21, 100), (4, 101, 500), (5, 501, math.inf)],
    },
}


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.table: list[list[str]] | None = None
        self.row: list[str] | None = None
        self.cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in {"td", "th"} and self.row is not None:
            self.cell = []

    def handle_data(self, data: str) -> None:
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.table is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table:
                self.tables.append(self.table)
            self.table = None


def fetch_bytes(url: str, timeout: int = 15, attempts: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            })
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - validation needs exact upstream failure
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
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(str(value).replace(",", "").rstrip("%"))
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
    snapshot = re.search(r"24-month record ending\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", text, re.I)
    measure = re.search(r"On-Road Performance\s+Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    if not measure:
        measure = re.search(r"Measure:\s*([0-9]+(?:\.[0-9]+)?)", text, re.I)
    percentile = re.search(r"Percentile:\s*([0-9]+(?:\.[0-9]+)?)%", text, re.I)
    if not percentile:
        percentile = re.search(r"([0-9]+(?:\.[0-9]+)?)%\s+Percentile", text, re.I)
    return {
        "snapshot": snapshot.group(1) if snapshot else None,
        "measure": float(measure.group(1)) if measure else None,
        "percentile": float(percentile.group(1)) if percentile else None,
    }


def parse_curve(raw: bytes) -> list[dict[str, float]]:
    parser = TableParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    for table in parser.tables:
        header_index = next((index for index, row in enumerate(table)
                             if len(row) >= 2 and row[0].strip().lower() == "measure"
                             and row[1].strip().lower() == "percentile"), None)
        if header_index is None:
            continue
        points: list[dict[str, float]] = []
        for row in table[header_index + 1:]:
            if len(row) < 2:
                continue
            measure = number(row[0])
            percentile = number(row[1])
            if measure is not None and percentile is not None:
                points.append({"measure": measure, "percentile": percentile})
        if len(points) >= 90:
            return sorted(points, key=lambda point: point["measure"])
    raise RuntimeError("Could not parse Measure | Percentile conversion table")


def curve_signature(curve: list[dict[str, float]]) -> str:
    return json.dumps(curve, sort_keys=True, separators=(",", ":"))


def lookup(curve: list[dict[str, float]], measure: float, mode: str) -> float:
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
    candidates = []
    for row in rows:
        measure = number(row.get(rule["measure_field"]))
        event_total = integer(row.get(rule["event_field"]))
        if measure is None or measure <= 0 or group_for(event_total, rule["groups"]) != group:
            continue
        if integer(row.get(rule["violation_field"])) < rule["min_violations"]:
            continue
        dot = str(row.get("dot_number") or "").strip()
        if dot:
            candidates.append({
                "dot_number": dot,
                "bulk_measure": measure,
                "event_total": event_total,
                "violation_inspections": integer(row.get(rule["violation_field"])),
            })
    candidates.sort(key=lambda row: (row["bulk_measure"], row["dot_number"]))
    if len(candidates) <= CANDIDATES_PER_GROUP:
        return candidates
    selected = []
    for index in range(CANDIDATES_PER_GROUP):
        position = round(index * (len(candidates) - 1) / (CANDIDATES_PER_GROUP - 1))
        selected.append(candidates[position])
    return list({row["dot_number"]: row for row in selected}.values())


def fetch_observation(basic: str, rule: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    dot = candidate["dot_number"]
    base = f"{SMS_ROOT}/Carrier/{dot}/BASIC/{rule['path']}"
    return {
        **candidate,
        "basic": basic,
        "basic_url": f"{base}.aspx",
        "graph_url": f"{base}/MeasurePercentileGraph.aspx",
        "page": parse_basic_page(fetch_bytes(f"{base}.aspx")),
        "curve": parse_curve(fetch_bytes(f"{base}/MeasurePercentileGraph.aspx")),
    }


def main() -> int:
    passenger_rows = fetch_json(PASSENGER_OUTPUT_ID, {"$limit": "50000"})
    consensus_snapshot: str | None = None
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
                    if page["snapshot"] is None:
                        failures.append({"dot_number": observation["dot_number"], "error": "SMS snapshot missing from BASIC page"})
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

            group_snapshots = {str(observation["page"]["snapshot"]) for observation in observations}
            if len(group_snapshots) != 1:
                raise RuntimeError(f"{basic} group {group}: BASIC pages disagree on SMS snapshot {sorted(group_snapshots)}")
            group_snapshot = next(iter(group_snapshots))
            if consensus_snapshot is None:
                consensus_snapshot = group_snapshot
            elif group_snapshot != consensus_snapshot:
                raise RuntimeError(f"{basic} group {group}: snapshot {group_snapshot} != consensus {consensus_snapshot}")

            signatures: dict[str, int] = {}
            for observation in observations:
                signature = curve_signature(observation["curve"])
                signatures[signature] = signatures.get(signature, 0) + 1
            winning_signature, winning_count = max(signatures.items(), key=lambda item: item[1])
            matched = [observation for observation in observations if curve_signature(observation["curve"]) == winning_signature]
            if winning_count < MIN_VALIDATORS_PER_GROUP:
                raise RuntimeError(f"{basic} group {group}: public graph curves disagree across validators")
            curve = matched[0]["curve"]

            mode_results: dict[str, dict[str, Any]] = {}
            for mode in ("exact", "floor", "ceiling", "nearest"):
                comparisons = []
                for observation in matched:
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
                }

            supported = [mode for mode, result in mode_results.items()
                         if len(result["comparisons"]) >= MIN_VALIDATORS_PER_GROUP
                         and result["match_count"] == len(result["comparisons"])]
            if not supported:
                raise RuntimeError(f"{basic} group {group}: no lookup mode reproduced public percentiles; {mode_results}")
            lookup_mode = next(mode for mode in ("exact", "ceiling", "floor", "nearest") if mode in supported)
            representative = matched[0]
            group_outputs[str(group)] = {
                "event_min": minimum,
                "event_max": None if math.isinf(maximum) else maximum,
                "curve_source": representative["graph_url"],
                "representative_dot_number": representative["dot_number"],
                "lookup_mode": lookup_mode,
                "validator_count": len(matched),
                "validator_dot_numbers": [observation["dot_number"] for observation in matched],
                "curve": curve,
            }
            total_validations += len(matched)

        output_basics[basic] = {
            "label": rule["label"],
            "group_basis": rule["event_field"],
            "groups": group_outputs,
        }

    if consensus_snapshot is None:
        raise RuntimeError("No SMS snapshot established from validated BASIC pages")

    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "sms_snapshot": consensus_snapshot,
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
        "sms_snapshot": consensus_snapshot,
        "ruleset": RULESET,
        "validation_count": total_validations,
        "basic_count": len(output_basics),
        "group_count": sum(len(basic["groups"]) for basic in output_basics.values()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
