#!/usr/bin/env python3
"""Capture and validate FMCSA's official SMS measure→percentile conversion curves.

FMCSA's Help Center directs users to each BASIC's public "Measure vs. Percentile"
graph as the conversion chart. Passenger-carrier BASIC percentiles are also public.
Transport3r uses those official public surfaces instead of reverse-engineering FMCSA
ranking or tie behavior.

For each HOS Compliance, Driver Fitness, and Vehicle Maintenance safety-event group:
1. Find a data-sufficient passenger carrier in current SMS bulk output.
2. Fetch that carrier's BASIC page and official MeasurePercentileGraph page.
3. Verify current bulk and live measures agree and establish the SMS snapshot.
4. Determine which graph lookup modes reproduce the anchor carrier percentile.
5. Fetch a second independent passenger BASIC page in the same group and require the
   same graph to reproduce that carrier's published percentile.

Only one official graph is fetched per group; the second independent carrier validates
that the curve generalizes to another carrier in the same group. Requests are
sequential with bounded fallback candidates because the public SMS site throttles
bursty traffic.
"""

from __future__ import annotations

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
CANDIDATES_PER_GROUP = 10
REQUEST_PAUSE_SECONDS = 0.6
GROUP_PAUSE_SECONDS = 0.8

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


def fetch_bytes(url: str, timeout: int = 12, attempts: int = 2) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - preserve exact upstream failure
            last_error = exc
            if attempt < attempts:
                time.sleep(1.0)
    assert last_error is not None
    raise last_error


def fetch_json(source_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode(params)
    payload = json.loads(fetch_bytes(f"{DATAHUB}/{source_id}.json?{query}", timeout=30, attempts=3).decode("utf-8"))
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
        header = next(
            (
                index
                for index, row in enumerate(table)
                if len(row) >= 2 and row[0].strip().lower() == "measure" and row[1].strip().lower() == "percentile"
            ),
            None,
        )
        if header is None:
            continue
        points: list[dict[str, float]] = []
        for row in table[header + 1 :]:
            if len(row) < 2:
                continue
            measure = number(row[0])
            percentile = number(row[1])
            if measure is not None and percentile is not None:
                points.append({"measure": measure, "percentile": percentile})
        if len(points) >= 90:
            return sorted(points, key=lambda point: point["measure"])
    raise RuntimeError("Could not parse Measure | Percentile conversion table")


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
    eligible: list[dict[str, Any]] = []
    for row in rows:
        measure = number(row.get(rule["measure_field"]))
        event_total = integer(row.get(rule["event_field"]))
        if measure is None or measure <= 0 or group_for(event_total, rule["groups"]) != group:
            continue
        if integer(row.get(rule["violation_field"])) < rule["min_violations"]:
            continue
        dot = str(row.get("dot_number") or "").strip()
        if dot:
            eligible.append({"dot_number": dot, "bulk_measure": measure, "event_total": event_total})
    eligible.sort(key=lambda row: (row["bulk_measure"], row["dot_number"]))
    if len(eligible) <= CANDIDATES_PER_GROUP:
        return eligible
    selected: list[dict[str, Any]] = []
    for index in range(CANDIDATES_PER_GROUP):
        position = round(index * (len(eligible) - 1) / (CANDIDATES_PER_GROUP - 1))
        selected.append(eligible[position])
    return list({row["dot_number"]: row for row in selected}.values())


def basic_url(rule: dict[str, Any], dot: str) -> str:
    return f"{SMS_ROOT}/Carrier/{dot}/BASIC/{rule['path']}.aspx"


def graph_url(rule: dict[str, Any], dot: str) -> str:
    return f"{SMS_ROOT}/Carrier/{dot}/BASIC/{rule['path']}/MeasurePercentileGraph.aspx"


def valid_page(candidate: dict[str, Any], page: dict[str, Any], expected_snapshot: str | None) -> str | None:
    if page["snapshot"] is None or page["measure"] is None or page["percentile"] is None:
        return "snapshot/measure/percentile unavailable"
    if expected_snapshot is not None and page["snapshot"] != expected_snapshot:
        return f"snapshot {page['snapshot']} != {expected_snapshot}"
    if abs(float(page["measure"]) - float(candidate["bulk_measure"])) > 0.02:
        return f"bulk/live measure mismatch {candidate['bulk_measure']} vs {page['measure']}"
    return None


def modes_matching(curve: list[dict[str, float]], page: dict[str, Any], allowed: list[str] | None = None) -> list[str]:
    modes = allowed or ["exact", "ceiling", "floor", "nearest"]
    matched: list[str] = []
    for mode in modes:
        try:
            predicted = lookup(curve, float(page["measure"]), mode)
        except KeyError:
            continue
        if abs(predicted - float(page["percentile"])) < 1e-9:
            matched.append(mode)
    return matched


def validate_group(
    basic: str,
    rule: dict[str, Any],
    group: int,
    candidates: list[dict[str, Any]],
    expected_snapshot: str | None,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, float]], str, list[dict[str, str]]]:
    failures: list[dict[str, str]] = []
    anchor: dict[str, Any] | None = None
    curve: list[dict[str, float]] | None = None
    supported_modes: list[str] = []

    # Phase 1: obtain one official graph and prove it reproduces its own carrier's
    # published percentile.
    for candidate in candidates:
        try:
            page = parse_basic_page(fetch_bytes(basic_url(rule, candidate["dot_number"])))
            problem = valid_page(candidate, page, expected_snapshot)
            if problem:
                failures.append({"dot_number": candidate["dot_number"], "error": problem})
                continue
            time.sleep(REQUEST_PAUSE_SECONDS)
            candidate_curve = parse_curve(fetch_bytes(graph_url(rule, candidate["dot_number"])))
            modes = modes_matching(candidate_curve, page)
            if not modes:
                failures.append({"dot_number": candidate["dot_number"], "error": "official graph did not reproduce anchor percentile"})
                continue
            anchor = {**candidate, "page": page}
            curve = candidate_curve
            supported_modes = modes
            break
        except Exception as exc:  # noqa: BLE001
            failures.append({"dot_number": candidate["dot_number"], "error": f"{type(exc).__name__}: {exc}"})
        finally:
            time.sleep(REQUEST_PAUSE_SECONDS)

    if anchor is None or curve is None:
        raise RuntimeError(f"{basic} group {group}: no valid anchor graph; failures={failures[:6]}")

    # Phase 2: validate the same curve against a second independent public passenger
    # carrier. No second graph request is needed because the first graph is the
    # official conversion source for the group.
    for candidate in candidates:
        if candidate["dot_number"] == anchor["dot_number"]:
            continue
        try:
            page = parse_basic_page(fetch_bytes(basic_url(rule, candidate["dot_number"])))
            problem = valid_page(candidate, page, str(anchor["page"]["snapshot"]))
            if problem:
                failures.append({"dot_number": candidate["dot_number"], "error": problem})
                continue
            modes = modes_matching(curve, page, supported_modes)
            if not modes:
                failures.append({"dot_number": candidate["dot_number"], "error": "anchor graph did not reproduce validator percentile"})
                continue
            validator = {**candidate, "page": page}
            preferred = next(mode for mode in ("exact", "ceiling", "floor", "nearest") if mode in modes)
            return anchor, validator, curve, preferred, failures
        except Exception as exc:  # noqa: BLE001
            failures.append({"dot_number": candidate["dot_number"], "error": f"{type(exc).__name__}: {exc}"})
        finally:
            time.sleep(REQUEST_PAUSE_SECONDS)

    raise RuntimeError(f"{basic} group {group}: no independent validator for anchor {anchor['dot_number']}; failures={failures[:8]}")


def main() -> int:
    passenger_rows = fetch_json(PASSENGER_OUTPUT_ID, {"$limit": "50000"})
    consensus_snapshot: str | None = None
    output_basics: dict[str, Any] = {}
    total_validations = 0

    for basic, rule in BASICS.items():
        groups_out: dict[str, Any] = {}
        for group, minimum, maximum in rule["groups"]:
            candidates = candidate_rows(passenger_rows, rule, group)
            if len(candidates) < 2:
                raise RuntimeError(f"{basic} group {group}: only {len(candidates)} data-sufficient passenger candidates")
            anchor, validator, curve, lookup_mode, failures = validate_group(
                basic, rule, group, candidates, consensus_snapshot
            )
            snapshot = str(anchor["page"]["snapshot"])
            if consensus_snapshot is None:
                consensus_snapshot = snapshot
            representative_dot = anchor["dot_number"]
            groups_out[str(group)] = {
                "event_min": minimum,
                "event_max": None if math.isinf(maximum) else maximum,
                "curve_source": graph_url(rule, representative_dot),
                "representative_dot_number": representative_dot,
                "lookup_mode": lookup_mode,
                "validator_count": 2,
                "validator_dot_numbers": [representative_dot, validator["dot_number"]],
                "failed_candidate_count": len(failures),
                "curve": curve,
            }
            total_validations += 2
            time.sleep(GROUP_PAUSE_SECONDS)
        output_basics[basic] = {"label": rule["label"], "group_basis": rule["event_field"], "groups": groups_out}

    if consensus_snapshot is None:
        raise RuntimeError("No SMS snapshot established")

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
        "group_count": sum(len(item["groups"]) for item in output_basics.values()),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
