#!/usr/bin/env python3
"""Runtime smoke test for Transport3r's FMCSA Carrier 360 join contract.

The test discovers a real USDOT + inspection ID from the current public inspection
file, then exercises every live query shape used by Carrier 360. A source is allowed
to return zero rows for that carrier; malformed joins, missing required join columns,
HTTP failures and non-array payloads fail the smoke test.

The fleet contract is checked explicitly because the Inspection Per Unit file uses
INSP_UNIT_* field names rather than generic VIN/MAKE/LICENSE names. The carrier
directory query is also checked because its fleet filter/sort uses FMCSA's published
single-letter FLEETSIZE code rather than treating the text POWER_UNITS field as numeric.
"""

from __future__ import annotations

import json
import pathlib
import time
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "public" / "data" / "source-schemas.json"
BASE = "https://data.transportation.gov/resource"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"

USDOT_ALIASES = {"DOT_NUMBER", "USDOT_NUMBER", "USDOT_NUM", "USDOT_NO", "DOT_NO", "US_DOT_NUMBER"}
INSPECTION_ID_ALIASES = {"INSPECTION_ID", "INSP_ID"}
FLEET_FIELDS = {
    "insp_unit_vehicle_id_number",
    "insp_unit_make",
    "insp_unit_type_id",
    "insp_unit_license",
    "insp_unit_license_state",
    "insp_unit_number",
}

DIRECT_DOT_SOURCES = {
    "az4n-8mr2": "Company Census",
    "fx4q-ay7w": "Vehicle Inspection",
    "aayw-vxb3": "Crash",
    "inys-ebih": "MOTUS Carrier",
    "yu5v-wbh6": "MOTUS AuthHist",
    "c5y8-a4uz": "MOTUS Insurance",
    "3uet-3z4i": "MOTUS Insurance History",
    "wb4f-neki": "MOTUS RevokeSuspend",
    "kjg3-diqy": "SMS Input Census",
    "rbkj-cgst": "SMS Input Inspection",
    "4wxs-vbns": "SMS Input Crash",
    "8mt8-2mdr": "SMS Input Violation",
    "4y6x-dmck": "SMS AB PassProperty",
    "h9zy-gjn8": "SMS C PassProperty",
    "p2mt-9ige": "New Entrant OOS",
}

INSPECTION_CHILD_SOURCES = {
    "wt8s-2hbx": "Inspection Units",
    "876r-jsdb": "Inspection Violations",
    "qbt8-7vic": "Inspection Citations",
}


def normalize(value: Any) -> str:
    text = str(value or "").strip().upper()
    out: list[str] = []
    prior_sep = False
    for char in text:
        if char.isalnum():
            out.append(char)
            prior_sep = False
        elif not prior_sep:
            out.append("_")
            prior_sep = True
    return "".join(out).strip("_")


def fetch_json(url: str, timeout: int = 30, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001 - exact upstream failures belong in CI logs
            last_error = exc
            if attempt < attempts:
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def find_column(schema: dict[str, Any], aliases: set[str]) -> dict[str, Any] | None:
    for column in schema.get("columns", []):
        if normalize(column.get("name")) in aliases or normalize(column.get("field_name")) in aliases:
            return column
    return None


def literal(column: dict[str, Any], value: str) -> str:
    if column.get("data_type") == "number":
        return str(int(float(value)))
    return "'" + value.replace("'", "''") + "'"


def query(source_id: str, where: str, limit: int = 1, order: str | None = None) -> list[dict[str, Any]]:
    values = {"$where": where, "$limit": str(limit)}
    if order:
        values["$order"] = order
    params = urllib.parse.urlencode(values)
    payload = fetch_json(f"{BASE}/{source_id}.json?{params}")
    if not isinstance(payload, list):
        raise RuntimeError(f"{source_id} returned non-array JSON")
    return payload


def main() -> int:
    registry = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schemas = {source["id"]: source for source in registry["sources"]}

    missing_schemas = sorted((set(DIRECT_DOT_SOURCES) | set(INSPECTION_CHILD_SOURCES)) - set(schemas))
    if missing_schemas:
        raise RuntimeError(f"Missing schema registry entries: {', '.join(missing_schemas)}")

    fleet_schema_fields = {str(column.get("field_name") or "") for column in schemas["wt8s-2hbx"].get("columns", [])}
    missing_fleet_fields = sorted(FLEET_FIELDS - fleet_schema_fields)
    if missing_fleet_fields:
        raise RuntimeError(f"Inspection Units schema lost required Carrier Fleet fields: {', '.join(missing_fleet_fields)}")

    inspection_schema = schemas["fx4q-ay7w"]
    inspection_dot = find_column(inspection_schema, USDOT_ALIASES)
    inspection_id_column = find_column(inspection_schema, INSPECTION_ID_ALIASES)
    if not inspection_dot or not inspection_id_column:
        raise RuntimeError("Vehicle Inspection schema is missing USDOT or INSPECTION_ID")

    seed_where = f"{inspection_dot['field_name']} is not null and {inspection_id_column['field_name']} is not null"
    seed_rows = query("fx4q-ay7w", seed_where, limit=1)
    if not seed_rows:
        raise RuntimeError("No current inspection row available to seed Carrier 360 smoke test")

    seed = seed_rows[0]
    dot_number = str(seed[inspection_dot["field_name"]])
    inspection_id = str(seed[inspection_id_column["field_name"]])
    print(f"Seed carrier USDOT={dot_number} inspection_id={inspection_id}")

    results: list[dict[str, Any]] = []

    for source_id, name in DIRECT_DOT_SOURCES.items():
        schema = schemas[source_id]
        dot_column = find_column(schema, USDOT_ALIASES)
        if not dot_column:
            raise RuntimeError(f"{source_id} {name} has no registered USDOT column but Carrier 360 queries it by USDOT")
        rows = query(source_id, f"{dot_column['field_name']}={literal(dot_column, dot_number)}", limit=2)
        results.append({"source": source_id, "name": name, "join": dot_column["field_name"], "rows": len(rows)})

    for source_id, name in INSPECTION_CHILD_SOURCES.items():
        schema = schemas[source_id]
        child_inspection_id = find_column(schema, INSPECTION_ID_ALIASES)
        if not child_inspection_id:
            raise RuntimeError(f"{source_id} {name} has no registered INSPECTION_ID column")
        rows = query(
            source_id,
            f"{child_inspection_id['field_name']}={literal(child_inspection_id, inspection_id)}",
            limit=2,
        )
        result: dict[str, Any] = {"source": source_id, "name": name, "join": child_inspection_id["field_name"], "rows": len(rows)}
        if source_id == "wt8s-2hbx" and rows:
            populated_fleet_fields = sorted({field for row in rows for field in FLEET_FIELDS if str(row.get(field) or "").strip()})
            if not populated_fleet_fields:
                raise RuntimeError("Inspection Units returned rows but none of the registered fleet display fields were populated")
            result["populated_fleet_fields"] = populated_fleet_fields
            result["sample_vin"] = next((str(row.get("insp_unit_vehicle_id_number")) for row in rows if row.get("insp_unit_vehicle_id_number")), None)
        results.append(result)

    directory_rows = query(
        "az4n-8mr2",
        "phy_state='TX' AND carrier_operation='A' AND fleetsize>='A'",
        limit=2,
        order="fleetsize DESC, dot_number DESC",
    )
    if not directory_rows:
        raise RuntimeError("Carrier directory fleet-size filter returned no representative Texas interstate carriers")
    directory_sample = directory_rows[0]
    if not str(directory_sample.get("dot_number") or "").strip() or not str(directory_sample.get("legal_name") or "").strip():
        raise RuntimeError("Carrier directory query returned a row without USDOT/legal name identity")

    print(json.dumps({
        "status": "ok",
        "dot_number": dot_number,
        "inspection_id": inspection_id,
        "directory_query": {
            "rows": len(directory_rows),
            "sample_dot_number": directory_sample.get("dot_number"),
            "sample_legal_name": directory_sample.get("legal_name"),
            "sample_power_units": directory_sample.get("power_units"),
            "sample_fleet_size_code": directory_sample.get("fleetsize"),
        },
        "queries": results,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
