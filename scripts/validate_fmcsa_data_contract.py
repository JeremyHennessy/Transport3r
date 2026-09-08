#!/usr/bin/env python3
"""Validate Transport3r's FMCSA source, join, and normalization contract.

This is deliberately upstream of scoring. It verifies that every configured DOT DataHub
source is represented in the frontend evidence contract, that its documented join key
exists with a supported type, and that live round-trip queries preserve the requested
carrier/inspection identity. It also validates the two cross-source joins that matter
most for downstream calculations:

* Inspection child records -> Vehicle Inspection via INSPECTION_ID.
* SMS Input Violation -> SMS Input Inspection via UNIQUE_ID + DOT_NUMBER.

Raw evidence remains raw. The normalization functions here only test whether identifiers,
numeric text, flags, and FMCSA date encodings can be converted deterministically before
model logic consumes them.
"""

from __future__ import annotations

import concurrent.futures
import datetime as dt
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "data" / "fmcsa_sources.json"
SCHEMA_PATH = ROOT / "public" / "data" / "source-schemas.json"
EVIDENCE_PATH = ROOT / "src" / "carrierEvidence.ts"
BASE = "https://data.transportation.gov/resource"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"

USDOT_ALIASES = {"DOT_NUMBER", "USDOT_NUMBER", "USDOT_NUM", "USDOT_NO", "DOT_NO", "US_DOT_NUMBER"}
INSPECTION_ID_ALIASES = {"INSPECTION_ID", "INSP_ID"}
DOCKET_ALIASES = {"PREFIX_DOCKET_NUMBER", "DOCKET_NUMBER", "DOCKET_NO"}
DOCKET_ONLY_SOURCE_IDS = {"ypjt-5ydn"}
LEGACY_CARRIER_ID = "6eyk-hxee"
CHILD_SOURCE_IDS = {"wt8s-2hbx", "876r-jsdb", "5qik-smay", "qbt8-7vic"}
PARENT_INSPECTION_ID = "fx4q-ay7w"
SMS_INSPECTION_ID = "rbkj-cgst"
SMS_VIOLATION_ID = "8mt8-2mdr"

# Fields whose semantics are relied upon by the current underwriting UI or validated SMS replay.
REQUIRED_FIELDS: dict[str, set[str]] = {
    "az4n-8mr2": {"dot_number", "legal_name", "status_code", "carrier_operation", "power_units", "truck_units", "bus_units", "fleetsize", "total_drivers", "avg_drivers_leased_per_month", "mcs150_mileage", "mcs150_mileage_year", "mcs150_date"},
    "aayw-vxb3": {"dot_number", "report_date"},
    "fx4q-ay7w": {"dot_number", "inspection_id", "insp_date"},
    "wt8s-2hbx": {"inspection_id", "insp_unit_vehicle_id_number", "insp_unit_make", "insp_unit_type_id", "insp_unit_license", "insp_unit_license_state", "insp_unit_number"},
    "876r-jsdb": {"inspection_id", "out_of_service_indicator", "viol_desc", "insp_viol_unit"},
    "5qik-smay": {"inspection_id"},
    "qbt8-7vic": {"inspection_id"},
    "inys-ebih": {"usdot_number", "docket_number", "op_auth_type", "op_auth_status"},
    "yu5v-wbh6": {"usdot_number", "docket_number", "op_auth_type", "op_auth_status", "status_change_date"},
    "6snj-ed7q": {"usdot_number", "docket_number", "co_name"},
    "wb4f-neki": {"usdot_number", "docket_number", "op_auth_type", "order1_serve_date", "order1_effective_date"},
    "c5y8-a4uz": {"usdot_number", "docket_number", "policy_no", "effective_date", "insurance_company_name", "max_cov_amount"},
    "3uet-3z4i": {"usdot_number", "docket_number", "policy_no", "effective_date", "cancl_effective_date", "insurance_company_name", "max_cov_amount"},
    "nakq-58th": {"usdot_number", "docket_number", "op_auth_type", "op_auth_status"},
    "dm5j-zc6c": {"usdot_number", "docket_number", "op_auth_type", "op_auth_status", "status_change_date"},
    "mhr5-hjyc": {"usdot_number", "docket_number", "co_name"},
    "x96h-evps": {"usdot_number", "docket_number", "policy_no", "effective_date", "insurance_company_name", "max_cov_amount"},
    "xe5s-wca7": {"usdot_number", "docket_number", "policy_no", "effective_date", "cancl_effective_date", "insurance_company_name", "max_cov_amount"},
    "e67p-xyd5": {"usdot_number", "docket_number", "op_auth_type", "order1_serve_date", "order1_effective_date"},
    "kjg3-diqy": {"dot_number", "mcs150_date", "mcs150_mileage", "mcs150_mileage_year", "nbr_power_unit", "driver_total"},
    "rbkj-cgst": {"unique_id", "dot_number", "insp_date", "time_weight", "unsafe_insp", "fatigued_insp", "dr_fitness_insp", "subt_alcohol_insp", "vh_maint_insp", "hm_insp"},
    "4wxs-vbns": {"dot_number", "report_date", "time_weight"},
    "8mt8-2mdr": {"unique_id", "dot_number", "insp_date", "basic_desc", "oos_indicator", "severity_weight", "time_weight", "total_severity_wght"},
    "m3ry-qcip": {"dot_number", "driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "h3zn-uid9": {"dot_number", "driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "4y6x-dmck": {"dot_number", "driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "h9zy-gjn8": {"dot_number", "driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "p2mt-9ige": {"dot_number", "oos_date", "oos_reason", "status", "rescind_date"},
}

NUMERIC_TEXT_FIELDS: dict[str, set[str]] = {
    "az4n-8mr2": {"power_units", "truck_units", "bus_units", "total_drivers", "avg_drivers_leased_per_month", "mcs150_mileage", "mcs150_mileage_year"},
    "kjg3-diqy": {"mcs150_mileage", "mcs150_mileage_year", "nbr_power_unit", "driver_total"},
    "rbkj-cgst": {"time_weight", "driver_oos_total", "vehicle_oos_total", "oos_total", "hazmat_oos_total"},
    "4wxs-vbns": {"time_weight"},
    "8mt8-2mdr": {"oos_weight", "severity_weight", "time_weight", "total_severity_wght"},
    "m3ry-qcip": {"driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "h3zn-uid9": {"driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "4y6x-dmck": {"driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
    "h9zy-gjn8": {"driver_insp_total", "vehicle_insp_total", "hos_driv_measure", "driv_fit_measure", "contr_subst_measure", "veh_maint_measure"},
}

DATE_FIELDS: dict[str, set[str]] = {
    "az4n-8mr2": {"mcs150_date"},
    "aayw-vxb3": {"report_date"},
    "fx4q-ay7w": {"insp_date"},
    "yu5v-wbh6": {"status_change_date"},
    "wb4f-neki": {"order1_serve_date", "order1_effective_date"},
    "c5y8-a4uz": {"effective_date", "trans_date"},
    "3uet-3z4i": {"effective_date", "cancl_effective_date"},
    "dm5j-zc6c": {"status_change_date"},
    "x96h-evps": {"effective_date", "trans_date"},
    "xe5s-wca7": {"effective_date", "cancl_effective_date"},
    "e67p-xyd5": {"order1_serve_date", "order1_effective_date"},
    "kjg3-diqy": {"mcs150_date"},
    "rbkj-cgst": {"insp_date"},
    "4wxs-vbns": {"report_date"},
    "8mt8-2mdr": {"insp_date"},
    "p2mt-9ige": {"oos_date", "rescind_date"},
}


def normalize_name(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def canonical_identifier(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return str(int(Decimal(text)))
    return text.upper()


def parse_decimal(value: Any) -> Decimal | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def parse_fmcsa_date(value: Any) -> dt.date | None:
    text = str(value or "").strip()
    if not text or text in {"0", "00000000", "0000-00-00"}:
        return None
    formats = ["%Y%m%d", "%m%d%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]
    clean = text.rstrip("Z")
    for fmt in formats:
        try:
            return dt.datetime.strptime(clean, fmt).date()
        except ValueError:
            pass
    try:
        return dt.datetime.fromisoformat(clean).date()
    except ValueError:
        return None


def fetch_json(url: str, timeout: int = 30, attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(min(3.0, 0.5 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


def fields(schema: dict[str, Any]) -> set[str]:
    return {str(column.get("field_name") or "") for column in schema.get("columns", []) if column.get("field_name")}


def find_column(schema: dict[str, Any], aliases: set[str]) -> dict[str, Any] | None:
    for column in schema.get("columns", []):
        if normalize_name(column.get("name")) in aliases or normalize_name(column.get("field_name")) in aliases:
            return column
    return None


def literal(column: dict[str, Any], value: str) -> str:
    if column.get("data_type") == "number":
        parsed = parse_decimal(value)
        if parsed is None:
            raise RuntimeError(f"Cannot express {value!r} as numeric literal for {column.get('field_name')}")
        return format(parsed, "f")
    return "'" + value.replace("'", "''") + "'"


def query(source_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
    payload = fetch_json(f"{BASE}/{source_id}.json?{urllib.parse.urlencode(params)}")
    if not isinstance(payload, list):
        raise RuntimeError(f"{source_id} returned non-array JSON")
    return payload


def live_roundtrip(source_id: str, schema: dict[str, Any], aliases: set[str]) -> dict[str, Any]:
    column = find_column(schema, aliases)
    if not column or not column.get("field_name"):
        raise RuntimeError(f"{source_id}: join field missing")
    field = str(column["field_name"])
    seed = query(source_id, {"$select": field, "$where": f"{field} is not null", "$limit": "1"})
    if not seed:
        raise RuntimeError(f"{source_id}: no non-null {field} row available")
    raw = seed[0].get(field)
    canonical = canonical_identifier(raw)
    if canonical is None:
        raise RuntimeError(f"{source_id}: empty {field} seed")
    rows = query(source_id, {"$select": field, "$where": f"{field}={literal(column, str(raw))}", "$limit": "5"})
    if not rows:
        raise RuntimeError(f"{source_id}: exact join round-trip returned zero rows for {raw!r}")
    returned = {canonical_identifier(row.get(field)) for row in rows}
    if returned != {canonical}:
        raise RuntimeError(f"{source_id}: join round-trip leaked identities: requested={canonical} returned={sorted(x for x in returned if x)}")
    return {"source": source_id, "field": field, "type": column.get("data_type"), "sample": canonical, "rows": len(rows)}


def validate_child_parent(source_id: str, schema: dict[str, Any], parent_schema: dict[str, Any]) -> dict[str, Any]:
    child = find_column(schema, INSPECTION_ID_ALIASES)
    parent = find_column(parent_schema, INSPECTION_ID_ALIASES)
    if not child or not child.get("field_name") or not parent or not parent.get("field_name"):
        raise RuntimeError(f"{source_id}: inspection lineage column missing")
    child_field = str(child["field_name"])
    parent_field = str(parent["field_name"])
    rows = query(source_id, {"$select": child_field, "$where": f"{child_field} is not null", "$limit": "1"})
    if not rows:
        raise RuntimeError(f"{source_id}: no inspection ID available for lineage check")
    raw = str(rows[0][child_field])
    parent_rows = query(PARENT_INSPECTION_ID, {"$select": parent_field, "$where": f"{parent_field}={literal(parent, raw)}", "$limit": "2"})
    if not parent_rows:
        raise RuntimeError(f"{source_id}: child inspection {raw} has no Vehicle Inspection parent")
    requested = canonical_identifier(raw)
    returned = {canonical_identifier(row.get(parent_field)) for row in parent_rows}
    if returned != {requested}:
        raise RuntimeError(f"{source_id}: parent lineage mismatch for inspection {raw}")
    return {"source": source_id, "inspection_id": requested, "parent": PARENT_INSPECTION_ID}


def validate_sms_lineage(schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    violation_schema = schemas[SMS_VIOLATION_ID]
    inspection_schema = schemas[SMS_INSPECTION_ID]
    vfields = fields(violation_schema)
    if not {"unique_id", "dot_number"}.issubset(vfields):
        raise RuntimeError("SMS Violation schema lacks UNIQUE_ID/DOT_NUMBER")
    if not {"unique_id", "dot_number"}.issubset(fields(inspection_schema)):
        raise RuntimeError("SMS Inspection schema lacks UNIQUE_ID/DOT_NUMBER")
    rows = query(SMS_VIOLATION_ID, {"$select": "unique_id,dot_number", "$where": "unique_id is not null and dot_number is not null", "$limit": "1"})
    if not rows:
        raise RuntimeError("SMS Violation has no row for lineage check")
    unique_id = str(rows[0]["unique_id"])
    dot = str(rows[0]["dot_number"])
    params = {
        "$select": "unique_id,dot_number",
        "$where": "unique_id='" + unique_id.replace("'", "''") + "' and dot_number='" + dot.replace("'", "''") + "'",
        "$limit": "5",
    }
    parents = query(SMS_INSPECTION_ID, params)
    if not parents:
        raise RuntimeError(f"SMS violation {unique_id} / USDOT {dot} has no SMS Inspection parent")
    if any(canonical_identifier(row.get("dot_number")) != canonical_identifier(dot) or str(row.get("unique_id")) != unique_id for row in parents):
        raise RuntimeError("SMS inspection/violation lineage returned a mismatched parent")
    return {"unique_id": unique_id, "dot_number": canonical_identifier(dot), "parents": len(parents)}


def validate_sample_normalization(source_id: str, schema: dict[str, Any]) -> dict[str, Any]:
    selected = sorted((NUMERIC_TEXT_FIELDS.get(source_id, set()) | DATE_FIELDS.get(source_id, set())) & fields(schema))
    if not selected:
        return {"source": source_id, "checked_fields": 0, "numeric": {}, "dates": {}}
    where = " or ".join(f"{field} is not null" for field in selected)
    rows = query(source_id, {"$select": ",".join(selected), "$where": where, "$limit": "25"})
    numeric: dict[str, int] = {}
    dates: dict[str, int] = {}
    for field in sorted(NUMERIC_TEXT_FIELDS.get(source_id, set()) & set(selected)):
        values = [row.get(field) for row in rows if str(row.get(field) or "").strip()]
        if values:
            bad = [value for value in values if parse_decimal(value) is None]
            if bad:
                raise RuntimeError(f"{source_id}: numeric normalization failed for {field}: {bad[:3]}")
            numeric[field] = len(values)
    for field in sorted(DATE_FIELDS.get(source_id, set()) & set(selected)):
        values = [row.get(field) for row in rows if str(row.get(field) or "").strip() and str(row.get(field)).strip() not in {"0", "00000000"}]
        if values:
            bad = [value for value in values if parse_fmcsa_date(value) is None]
            if bad:
                raise RuntimeError(f"{source_id}: date normalization failed for {field}: {bad[:3]}")
            dates[field] = len(values)
    return {"source": source_id, "checked_fields": len(selected), "numeric": numeric, "dates": dates}


def validate_legacy_insurance_docket_lineage(schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:
    source_id = "ypjt-5ydn"
    insurance_schema = schemas[source_id]
    carrier_schema = schemas[LEGACY_CARRIER_ID]
    insurance_docket = find_column(insurance_schema, DOCKET_ALIASES)
    carrier_docket = find_column(carrier_schema, DOCKET_ALIASES)
    if not insurance_docket or not insurance_docket.get("field_name"):
        raise RuntimeError(f"{source_id}: documented docket-number join field missing")
    if not carrier_docket or not carrier_docket.get("field_name"):
        raise RuntimeError(f"{LEGACY_CARRIER_ID}: docket-number lineage field missing")
    insurance_field = str(insurance_docket["field_name"])
    carrier_field = str(carrier_docket["field_name"])
    seeds = query(source_id, {"$select": insurance_field, "$where": f"{insurance_field} is not null", "$limit": "10"})
    for seed in seeds:
        raw = str(seed.get(insurance_field) or "").strip()
        if not raw:
            continue
        carrier_rows = query(LEGACY_CARRIER_ID, {
            "$select": carrier_field,
            "$where": f"{carrier_field}={literal(carrier_docket, raw)}",
            "$limit": "5",
        })
        if carrier_rows:
            requested = canonical_identifier(raw)
            returned = {canonical_identifier(row.get(carrier_field)) for row in carrier_rows}
            if requested not in returned:
                raise RuntimeError(f"legacy insurance docket lineage leaked identities for {raw}")
            return {
                "source": source_id,
                "join": insurance_field,
                "docket": requested,
                "parent_source": LEGACY_CARRIER_ID,
                "parent_join": carrier_field,
                "parent_rows": len(carrier_rows),
            }
    raise RuntimeError(f"{source_id}: sampled docket rows did not resolve to {LEGACY_CARRIER_ID}")


def main() -> int:
    configured = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    registry = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    schemas = {str(source["id"]): source for source in registry.get("sources", [])}
    config_ids = [str(row["id"]) for row in configured]
    if len(config_ids) != len(set(config_ids)):
        raise RuntimeError("Configured FMCSA source IDs contain duplicates")
    if set(config_ids) != set(schemas):
        raise RuntimeError(f"Source registry/schema drift: config-only={sorted(set(config_ids)-set(schemas))}, schema-only={sorted(set(schemas)-set(config_ids))}")

    evidence_text = EVIDENCE_PATH.read_text(encoding="utf-8")
    evidence_ids = set(re.findall(r"['\"]([a-z0-9]{4}-[a-z0-9]{4})['\"]", evidence_text))
    if set(config_ids) != evidence_ids:
        raise RuntimeError(f"Source registry/Carrier 360 drift: registry-only={sorted(set(config_ids)-evidence_ids)}, Carrier360-only={sorted(evidence_ids-set(config_ids))}")

    static_rows: list[dict[str, Any]] = []
    for source_id in config_ids:
        schema = schemas[source_id]
        available = fields(schema)
        missing = sorted(REQUIRED_FIELDS.get(source_id, set()) - available)
        if missing:
            raise RuntimeError(f"{source_id}: required semantic fields missing: {', '.join(missing)}")
        if source_id in CHILD_SOURCE_IDS:
            join = find_column(schema, INSPECTION_ID_ALIASES)
            kind = "inspection_child"
        elif source_id in DOCKET_ONLY_SOURCE_IDS:
            join = find_column(schema, DOCKET_ALIASES)
            kind = "docket_linked_archive"
        else:
            join = find_column(schema, USDOT_ALIASES)
            kind = "carrier"
        if not join or not join.get("field_name"):
            raise RuntimeError(f"{source_id}: {kind} join field missing")
        if join.get("data_type") not in {"text", "number"}:
            raise RuntimeError(f"{source_id}: unsupported join type {join.get('data_type')!r}")
        static_rows.append({"source": source_id, "name": schema.get("name"), "family": schema.get("family"), "kind": kind, "join": join.get("field_name"), "join_type": join.get("data_type"), "fields": len(schema.get("columns", []))})

    live_join_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        futures = {}
        for source_id in config_ids:
            aliases = INSPECTION_ID_ALIASES if source_id in CHILD_SOURCE_IDS else DOCKET_ALIASES if source_id in DOCKET_ONLY_SOURCE_IDS else USDOT_ALIASES
            futures[pool.submit(live_roundtrip, source_id, schemas[source_id], aliases)] = source_id
        for future in concurrent.futures.as_completed(futures):
            live_join_results.append(future.result())

    parent_schema = schemas[PARENT_INSPECTION_ID]
    child_lineage = [validate_child_parent(source_id, schemas[source_id], parent_schema) for source_id in sorted(CHILD_SOURCE_IDS)]
    sms_lineage = validate_sms_lineage(schemas)
    legacy_insurance_lineage = validate_legacy_insurance_docket_lineage(schemas)

    normalization_results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(validate_sample_normalization, source_id, schemas[source_id]) for source_id in config_ids]
        for future in concurrent.futures.as_completed(futures):
            normalization_results.append(future.result())

    payload = {
        "status": "ok",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_count": len(config_ids),
        "schema_field_count": registry.get("field_count"),
        "static_contract": sorted(static_rows, key=lambda row: row["source"]),
        "live_join_roundtrips": sorted(live_join_results, key=lambda row: row["source"]),
        "inspection_child_lineage": child_lineage,
        "sms_inspection_violation_lineage": sms_lineage,
        "legacy_insurance_docket_lineage": legacy_insurance_lineage,
        "normalization_samples": sorted(normalization_results, key=lambda row: row["source"]),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
