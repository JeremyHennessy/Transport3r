#!/usr/bin/env python3
"""Fail when Transport3r's FMCSA catalog, runtime map and generated lineage drift."""
from __future__ import annotations

import json
import pathlib
import re
from temporal_policy import load_policy, sms_binding

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "fmcsa_sources.json"
SCHEMAS = ROOT / "public" / "data" / "source-schemas.json"
HEALTH = ROOT / "public" / "data" / "source-health.json"
RUNTIME = ROOT / "src" / "carrierEvidence.ts"
SOURCE_CONTRACT = ROOT / "data" / "fmcsa_source_contract.json"
GOLDEN = ROOT / "data" / "golden_carriers.json"
NATIONWIDE_ACCEPTANCE = ROOT / "data" / "nationwide_acceptance_20261023.json"
GOLDEN_VERIFICATION = ROOT / "data" / "golden_verification_20261023.json"

# Official FMCSA Open Data Program contract audited 2026-09-08:
# USDOT entity data (7), modern MOTUS baselines/deltas (12), legacy OA archives (8),
# SMS input/output (8), and New Entrant OOS (1).
REQUIRED_IDS = {
    "az4n-8mr2", "aayw-vxb3", "fx4q-ay7w", "wt8s-2hbx", "876r-jsdb", "5qik-smay", "qbt8-7vic",
    "inys-ebih", "yu5v-wbh6", "c5y8-a4uz", "3uet-3z4i", "6snj-ed7q", "wb4f-neki",
    "nakq-58th", "dm5j-zc6c", "mhr5-hjyc", "x96h-evps", "xe5s-wca7", "e67p-xyd5",
    "6eyk-hxee", "ypjt-5ydn", "qh9u-swkp", "9mw4-x3tu", "2emp-mxtb", "6sqe-dvqs", "96tg-4mhf", "sa6p-acbp",
    "kjg3-diqy", "rbkj-cgst", "4wxs-vbns", "8mt8-2mdr", "m3ry-qcip", "h3zn-uid9", "4y6x-dmck", "h9zy-gjn8",
    "p2mt-9ige",
}


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_retained_receipts(catalog_set: set[str], golden: dict) -> tuple[dict, dict]:
    nationwide = load(NATIONWIDE_ACCEPTANCE)
    expected_gates = {
        "source_coverage", "published_acquired_warehouse_counts", "row_mapping_accounting",
        "unresolved_reason_accounting", "arbitrary_assignment_prevention",
    }
    if (nationwide.get("version") != 1 or nationwide.get("status") != "VERIFIED"
            or nationwide.get("identity_contract") != "FMCSA_CARRIER_IDENTITY_1"
            or nationwide.get("scope") != "ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES"
            or nationwide.get("sources") != len(catalog_set)
            or set(nationwide.get("acceptance_gates", {})) != expected_gates
            or any(value != "PASS" for value in nationwide["acceptance_gates"].values())):
        raise RuntimeError("Retained nationwide acceptance contract is invalid")
    source_acceptance = nationwide.get("source_acceptance", [])
    if len(source_acceptance) != len(catalog_set) or {item.get("source") for item in source_acceptance} != catalog_set:
        raise RuntimeError("Retained nationwide source coverage is invalid")
    rows = 0
    mapping = {"resolved": 0, "identified_only": 0, "unresolved": 0}
    for item in source_acceptance:
        counts = [item.get(key) for key in ("published_rows", "acquired_rows", "warehouse_rows")]
        statuses, reasons = item.get("mapping_status"), item.get("mapping_reasons")
        if (not all(isinstance(value, int) and value >= 0 for value in counts) or len(set(counts)) != 1
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
                or not isinstance(item.get("rows_updated_at"), int)
                or not isinstance(statuses, dict) or set(statuses) - {"RESOLVED", "IDENTIFIED_ONLY", "UNRESOLVED"}
                or not all(isinstance(value, int) and value >= 0 for value in statuses.values())
                or sum(statuses.values()) != counts[2]
                or not isinstance(reasons, dict) or not reasons
                or not all(isinstance(key, str) and key and isinstance(value, int) and value >= 0 for key, value in reasons.items())
                or sum(reasons.values()) != counts[2]
                or item.get("count_gate") != "PASS" or item.get("reason_gate") != "PASS"):
            raise RuntimeError(f"Retained nationwide source acceptance is invalid: {item.get('source')}")
        rows += counts[2]
        for key in mapping:
            mapping[key] += statuses.get(key.upper(), 0)
    raw = nationwide.get("raw_verification", {})
    warehouse = nationwide.get("warehouse", {})
    if (rows != nationwide.get("rows") or mapping != nationwide.get("mapping_totals")
            or sum(mapping.values()) != rows or raw.get("status") != "PASS"
            or raw.get("sources") != len(catalog_set) or raw.get("rows") != rows
            or not all(isinstance(raw.get(key), int) and raw[key] > 0 for key in ("compressed_bytes", "source_bytes"))
            or not re.fullmatch(r"[0-9a-f]{64}", str(warehouse.get("sha256", "")))
            or not isinstance(warehouse.get("bytes"), int) or warehouse["bytes"] <= 0):
        raise RuntimeError("Retained nationwide aggregate acceptance is invalid")

    verification = load(GOLDEN_VERIFICATION)
    expected_checks = len(golden["census_carriers"]) + 4 * len(golden["detailed_carriers"])
    live = verification.get("live_observation", {})
    publications = verification.get("same_publication_sources", [])
    if (verification.get("version") != 1 or verification.get("status") != "PASS"
            or verification.get("selection") != "FROZEN_GOLDEN_V1"
            or verification.get("census_carriers") != len(golden["census_carriers"])
            or verification.get("detailed_carriers") != len(golden["detailed_carriers"])
            or verification.get("checks") != expected_checks or verification.get("failures") != []
            or live.get("status") != "PASS"
            or any(live.get(key) != [] for key in ("changed_sources", "acquisition_errors", "mapping_discrepancies"))
            or not re.fullmatch(r"[0-9a-f]{64}", str(live.get("observations_sha256", "")))
            or {item.get("source") for item in publications} != {"az4n-8mr2", "fx4q-ay7w", "aayw-vxb3", "rbkj-cgst", "kjg3-diqy"}
            or not all(item.get("match") is True and item.get("golden_rows_updated_at") == item.get("warehouse_rows_updated_at") for item in publications)):
        raise RuntimeError("Retained golden verification contract is invalid")
    verified_warehouse = verification.get("warehouse", {})
    if (verified_warehouse.get("cut_id") != nationwide.get("cut_id")
            or verified_warehouse.get("sha256") != warehouse.get("sha256")
            or verified_warehouse.get("scope") != nationwide.get("scope")
            or verified_warehouse.get("identity_contract") != nationwide.get("identity_contract")):
        raise RuntimeError("Golden verification is not bound to the retained nationwide warehouse")
    return nationwide, verification


def main() -> int:
    catalog = load(CATALOG)
    catalog_ids = [row["id"] for row in catalog]
    if len(catalog_ids) != len(set(catalog_ids)):
        raise RuntimeError("Duplicate FMCSA source IDs in catalog")
    catalog_set = set(catalog_ids)
    if catalog_set != REQUIRED_IDS:
        raise RuntimeError(
            f"Official source contract drift: missing={sorted(REQUIRED_IDS-catalog_set)}, extra={sorted(catalog_set-REQUIRED_IDS)}"
        )

    contract = load(SOURCE_CONTRACT)
    if contract.get('version') != 1 or contract.get('identity_contract') != 'FMCSA_CARRIER_IDENTITY_1':
        raise RuntimeError('Unsupported FMCSA identity contract')
    contracts = contract.get('sources', {})
    if set(contracts) != catalog_set:
        raise RuntimeError(
            f"Identity contract drift: catalog-only={sorted(catalog_set-set(contracts))}, contract-only={sorted(set(contracts)-catalog_set)}"
        )

    schemas = load(SCHEMAS)
    schema_set = {row["id"] for row in schemas.get("sources", [])}
    if schema_set != catalog_set or schemas.get("source_count") != len(catalog_set):
        raise RuntimeError(
            f"Schema registry drift: catalog={len(catalog_set)} schemas={len(schema_set)} missing={sorted(catalog_set-schema_set)} extra={sorted(schema_set-catalog_set)}"
        )
    schema_by_id = {row['id']:row for row in schemas.get('sources',[])}
    allowed = {'direct_usdot','direct_usdot_legacy','inspection_parent','legacy_docket'}
    for source_id,item in contracts.items():
        identity=item.get('identity',{})
        strategy,field=identity.get('strategy'),identity.get('field')
        fields={column.get('field_name') for column in schema_by_id[source_id].get('columns',[])}
        if strategy not in allowed or field not in fields:
            raise RuntimeError(f'{source_id}: invalid identity strategy/field {strategy}/{field}')
        if not item.get('grain') or not item.get('release_group') or not isinstance(item.get('event_date_fields'),list):
            raise RuntimeError(f'{source_id}: incomplete source semantics')
        missing_dates=set(item['event_date_fields'])-fields
        if missing_dates:
            raise RuntimeError(f'{source_id}: missing contracted date fields {sorted(missing_dates)}')
        date_like={field for field in fields if re.search(r'(^|_)date(_|$)',field) or field=='mcsipdate'}
        uncontracted_dates=date_like-set(item['event_date_fields'])
        if uncontracted_dates:
            raise RuntimeError(f'{source_id}: uncontracted source date fields {sorted(uncontracted_dates)}')
        if strategy=='inspection_parent' and (identity.get('parent_source'),identity.get('parent_field'))!=('fx4q-ay7w','inspection_id'):
            raise RuntimeError(f'{source_id}: invalid inspection parent contract')
        if strategy=='legacy_docket' and (identity.get('bridge_source'),identity.get('bridge_field'))!=('6eyk-hxee','docket_number'):
            raise RuntimeError(f'{source_id}: invalid docket bridge contract')

    health = load(HEALTH)
    health_set = {row["id"] for row in health.get("sources", [])}
    if health_set != catalog_set or health.get("source_count") != len(catalog_set):
        raise RuntimeError(
            f"Health registry drift: catalog={len(catalog_set)} health={len(health_set)} missing={sorted(catalog_set-health_set)} extra={sorted(health_set-catalog_set)}"
        )

    runtime_text = RUNTIME.read_text(encoding="utf-8")
    source_block = runtime_text.split("export const SOURCE_IDS = {", 1)[1].split("} as const;", 1)[0]
    runtime_set = set(re.findall(r"'([a-z0-9]{4}-[a-z0-9]{4})'", source_block))
    if runtime_set != catalog_set:
        raise RuntimeError(
            f"Runtime source map drift: catalog={len(catalog_set)} runtime={len(runtime_set)} missing={sorted(catalog_set-runtime_set)} extra={sorted(runtime_set-catalog_set)}"
        )

    archived = {row["id"] for row in catalog if row.get("tier") == "archive"}
    expected_archives = {"6eyk-hxee", "ypjt-5ydn", "qh9u-swkp", "9mw4-x3tu", "2emp-mxtb", "6sqe-dvqs", "96tg-4mhf", "sa6p-acbp"}
    if archived != expected_archives:
        raise RuntimeError(f"Legacy archive classification drift: {sorted(archived)}")

    golden = load(GOLDEN)
    census = golden.get('census_carriers', [])
    detailed = golden.get('detailed_carriers', [])
    regressions = golden.get('prior_regression_carriers', [])
    for label, values in [('census', census), ('detailed', detailed), ('prior regression', regressions)]:
        if not values or len(values) != len(set(values)) or any(not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]*', value) for value in values):
            raise RuntimeError(f'Invalid {label} golden carriers')
    if golden.get('version') != 1 or len(census) != 97 or len(detailed) != 25:
        raise RuntimeError('Golden carrier contract size/version drift')
    if not set(detailed).issubset(census) or not set(regressions).issubset(detailed):
        raise RuntimeError('Golden carrier subset contract drift')
    acceptance = golden.get('acceptance', {})
    if acceptance.get('source_result') != 'PASS' or acceptance.get('mapping_discrepancies') != 0 or acceptance.get('acquisition_errors') != 0:
        raise RuntimeError('Golden carrier seed was not sourced from a passing retained run')
    nationwide, verification = validate_retained_receipts(catalog_set, golden)
    temporal = load_policy()
    binding = sms_binding()

    print({
        "status": "ok",
        "source_count": len(catalog_set),
        "schema_field_count": schemas.get("field_count"),
        "legacy_archive_count": len(archived),
        "identity_contract": contract['identity_contract'],
        "golden_census_carriers": len(census),
        "golden_detailed_carriers": len(detailed),
        "nationwide_rows": nationwide["rows"],
        "golden_checks": verification["checks"],
        "temporal_contract": temporal['contract'],
        "sms_release_binding": binding['status'],
        "tri_v0_1": temporal['model_release']['tri_v0_1'],
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
