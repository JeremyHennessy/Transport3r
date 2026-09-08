#!/usr/bin/env python3
"""Patch the one legacy OA archive that is docket-linked rather than USDOT-linked.

FMCSA's frozen Insur - All With History dataset (ypjt-5ydn) explicitly links policy
rows to entities by docket number. The other seven legacy archives expose DOT_NUMBER.
This migration adds a real USDOT -> legacy Carrier docket -> legacy Insur lineage and
makes both runtime and validation honor that documented relationship.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding='utf-8')
    found = text.count(old)
    if found != count:
        raise RuntimeError(f'{path}: expected {count} occurrence(s), found {found}: {old[:100]!r}')
    target.write_text(text.replace(old, new), encoding='utf-8')


# Frontend data access: add a typed docket-number batch query alongside the existing
# USDOT and inspection-ID paths.
replace(
    'src/datahub.ts',
    "const INSPECTION_ID_ALIASES = ['INSPECTION_ID', 'INSP_ID'];\n",
    "const INSPECTION_ID_ALIASES = ['INSPECTION_ID', 'INSP_ID'];\nconst DOCKET_ALIASES = ['DOCKET_NUMBER', 'DOCKET_NO'];\n",
)
insert_before = "export async function queryByDotOrInspectionIds(\n"
query_fn = '''export async function queryByDocketNumbers(\n  registry: SchemaRegistry,\n  sourceId: string,\n  docketNumbers: string[],\n  options: { limitPerChunk?: number; maxDocketNumbers?: number; idsPerChunk?: number } = {},\n): Promise<DataSlice> {\n  const schema = sourceSchema(registry, sourceId);\n  const docketColumn = findColumn(schema, DOCKET_ALIASES);\n  if (!docketColumn?.field_name) throw new Error(`${sourceId} has no registered docket-number field`);\n\n  const unique = [...new Set(docketNumbers.filter(Boolean))].slice(0, options.maxDocketNumbers ?? 100);\n  if (!unique.length) return { sourceId, rows: [], total: 0, truncated: false };\n\n  const limitPerChunk = options.limitPerChunk ?? 2000;\n  const batches = chunks(unique, options.idsPerChunk ?? 50);\n  const responses = await Promise.all(\n    batches.map(async (batch) => {\n      const values = batch.map((id) => literal(docketColumn, id)).join(',');\n      const where = `${docketColumn.field_name} in (${values})`;\n      const params = new URLSearchParams({ '$where': where, '$limit': String(limitPerChunk) });\n      return fetchRows(sourceId, params);\n    }),\n  );\n  const rows = responses.flat();\n  return {\n    sourceId,\n    rows,\n    total: rows.length,\n    truncated: unique.length < docketNumbers.length || responses.some((batch) => batch.length >= limitPerChunk),\n  };\n}\n\n'''
replace('src/datahub.ts', insert_before, query_fn + insert_before)

# Carrier evidence: legacy Insurance cannot be queried by USDOT. Load the frozen
# legacy Carrier archive first, resolve all docket numbers for the USDOT, then retrieve
# Insur rows through those dockets. Keep the legacy material evidence-only.
replace(
    'src/carrierEvidence.ts',
    "  queryByDot,\n  queryByDotOrInspectionIds,\n",
    "  queryByDot,\n  queryByDocketNumbers,\n  queryByDotOrInspectionIds,\n",
)
old_remaining = "  const remaining = requested.filter((key) => key !== 'inspections');\n"
new_remaining = '''  let legacyDockets: string[] = [];\n  if (requested.includes('legacyInsurance')) {\n    const legacyCarrierResult = await capture('legacyCarrier', cachedSourceTask(registry, 'legacyCarrier', dotNumber, []));\n    if (legacyCarrierResult.slice) {\n      slices.legacyCarrier = legacyCarrierResult.slice;\n      legacyDockets = legacyCarrierResult.slice.rows\n        .map((row) => readValue(row, ['DOCKET_NUMBER', 'DOCKET_NO']))\n        .filter((value): value is string => Boolean(value));\n      legacyDockets = [...new Set(legacyDockets)];\n    }\n    if (legacyCarrierResult.error) errors.legacyCarrier = legacyCarrierResult.error;\n  }\n\n  const remaining = requested.filter((key) =>\n    key !== 'inspections' && key !== 'legacyCarrier' && key !== 'legacyInsurance'\n  );\n'''
replace('src/carrierEvidence.ts', old_remaining, new_remaining)
old_after_results = '''  for (const result of results) {\n    if (result.slice) slices[result.key] = result.slice;\n    if (result.error) errors[result.key] = result.error;\n  }\n\n  return {\n'''
new_after_results = '''  for (const result of results) {\n    if (result.slice) slices[result.key] = result.slice;\n    if (result.error) errors[result.key] = result.error;\n  }\n\n  if (requested.includes('legacyInsurance')) {\n    const legacyInsuranceResult = await capture(\n      'legacyInsurance',\n      queryByDocketNumbers(registry, SOURCE_IDS.legacyInsurance, legacyDockets, {\n        limitPerChunk: 2000,\n        maxDocketNumbers: 100,\n      }),\n    );\n    if (legacyInsuranceResult.slice) slices.legacyInsurance = legacyInsuranceResult.slice;\n    if (legacyInsuranceResult.error) errors.legacyInsurance = legacyInsuranceResult.error;\n  }\n\n  return {\n'''
replace('src/carrierEvidence.ts', old_after_results, new_after_results)

# Source-contract validator: model ypjt-5ydn by its documented docket key and prove
# that a sampled policy docket resolves back to the frozen legacy Carrier archive.
replace(
    'scripts/validate_fmcsa_data_contract.py',
    'INSPECTION_ID_ALIASES = {"INSPECTION_ID", "INSP_ID"}\n',
    'INSPECTION_ID_ALIASES = {"INSPECTION_ID", "INSP_ID"}\nDOCKET_ALIASES = {"DOCKET_NUMBER", "DOCKET_NO"}\nDOCKET_ONLY_SOURCE_IDS = {"ypjt-5ydn"}\nLEGACY_CARRIER_ID = "6eyk-hxee"\n',
)
main_marker = '\ndef main() -> int:\n'
lineage_fn = '''\ndef validate_legacy_insurance_docket_lineage(schemas: dict[str, dict[str, Any]]) -> dict[str, Any]:\n    source_id = "ypjt-5ydn"\n    insurance_schema = schemas[source_id]\n    carrier_schema = schemas[LEGACY_CARRIER_ID]\n    insurance_docket = find_column(insurance_schema, DOCKET_ALIASES)\n    carrier_docket = find_column(carrier_schema, DOCKET_ALIASES)\n    if not insurance_docket or not insurance_docket.get("field_name"):\n        raise RuntimeError(f"{source_id}: documented docket-number join field missing")\n    if not carrier_docket or not carrier_docket.get("field_name"):\n        raise RuntimeError(f"{LEGACY_CARRIER_ID}: docket-number lineage field missing")\n    insurance_field = str(insurance_docket["field_name"])\n    carrier_field = str(carrier_docket["field_name"])\n    seeds = query(source_id, {"$select": insurance_field, "$where": f"{insurance_field} is not null", "$limit": "10"})\n    for seed in seeds:\n        raw = str(seed.get(insurance_field) or "").strip()\n        if not raw:\n            continue\n        carrier_rows = query(LEGACY_CARRIER_ID, {\n            "$select": carrier_field,\n            "$where": f"{carrier_field}={literal(carrier_docket, raw)}",\n            "$limit": "5",\n        })\n        if carrier_rows:\n            requested = canonical_identifier(raw)\n            returned = {canonical_identifier(row.get(carrier_field)) for row in carrier_rows}\n            if requested not in returned:\n                raise RuntimeError(f"legacy insurance docket lineage leaked identities for {raw}")\n            return {\n                "source": source_id,\n                "join": insurance_field,\n                "docket": requested,\n                "parent_source": LEGACY_CARRIER_ID,\n                "parent_join": carrier_field,\n                "parent_rows": len(carrier_rows),\n            }\n    raise RuntimeError(f"{source_id}: sampled docket rows did not resolve to {LEGACY_CARRIER_ID}")\n\n'''
replace('scripts/validate_fmcsa_data_contract.py', main_marker, lineage_fn + main_marker)
old_static = '''        if source_id in CHILD_SOURCE_IDS:\n            join = find_column(schema, INSPECTION_ID_ALIASES)\n            kind = "inspection_child"\n        else:\n            join = find_column(schema, USDOT_ALIASES)\n            kind = "carrier"\n'''
new_static = '''        if source_id in CHILD_SOURCE_IDS:\n            join = find_column(schema, INSPECTION_ID_ALIASES)\n            kind = "inspection_child"\n        elif source_id in DOCKET_ONLY_SOURCE_IDS:\n            join = find_column(schema, DOCKET_ALIASES)\n            kind = "docket_linked_archive"\n        else:\n            join = find_column(schema, USDOT_ALIASES)\n            kind = "carrier"\n'''
replace('scripts/validate_fmcsa_data_contract.py', old_static, new_static)
replace(
    'scripts/validate_fmcsa_data_contract.py',
    '            aliases = INSPECTION_ID_ALIASES if source_id in CHILD_SOURCE_IDS else USDOT_ALIASES\n',
    '            aliases = INSPECTION_ID_ALIASES if source_id in CHILD_SOURCE_IDS else DOCKET_ALIASES if source_id in DOCKET_ONLY_SOURCE_IDS else USDOT_ALIASES\n',
)
replace(
    'scripts/validate_fmcsa_data_contract.py',
    '    sms_lineage = validate_sms_lineage(schemas)\n\n    normalization_results:',
    '    sms_lineage = validate_sms_lineage(schemas)\n    legacy_insurance_lineage = validate_legacy_insurance_docket_lineage(schemas)\n\n    normalization_results:',
)
replace(
    'scripts/validate_fmcsa_data_contract.py',
    '        "sms_inspection_violation_lineage": sms_lineage,\n',
    '        "sms_inspection_violation_lineage": sms_lineage,\n        "legacy_insurance_docket_lineage": legacy_insurance_lineage,\n',
)

# Runtime smoke: all sources remain covered, but the legacy Insur archive receives a
# docket round-trip + parent Carrier lineage check rather than a false USDOT query.
p = ROOT / 'scripts/smoke_carrier_queries.py'
text = p.read_text(encoding='utf-8')
legacy_line = '    "ypjt-5ydn": "Legacy Insurance",\n'
if text.count(legacy_line) != 1:
    raise RuntimeError('smoke_carrier_queries.py: expected legacy insurance direct-source entry')
text = text.replace(legacy_line, '', 1)
text = text.replace(
    'INSPECTION_ID_ALIASES = {"INSPECTION_ID", "INSP_ID"}\n',
    'INSPECTION_ID_ALIASES = {"INSPECTION_ID", "INSP_ID"}\nDOCKET_ALIASES = {"DOCKET_NUMBER", "DOCKET_NO"}\n',
    1,
)
marker = 'INSPECTION_CHILD_SOURCES = {\n'
if marker not in text:
    raise RuntimeError('smoke_carrier_queries.py: child-source marker missing')
text = text.replace(marker, 'DOCKET_SOURCES = {"ypjt-5ydn": "Legacy Insurance"}\n\n' + marker, 1)
text = text.replace(
    '    expected_sources = set(DIRECT_DOT_SOURCES) | set(INSPECTION_CHILD_SOURCES)\n',
    '    expected_sources = set(DIRECT_DOT_SOURCES) | set(DOCKET_SOURCES) | set(INSPECTION_CHILD_SOURCES)\n',
    1,
)
direct_loop_end = '''        rows = query(source_id, f"{dot_column['field_name']}={literal(dot_column, dot_number)}", limit=2)\n        results.append({"source": source_id, "name": name, "join": dot_column["field_name"], "rows": len(rows)})\n\n    for source_id, name in INSPECTION_CHILD_SOURCES.items():\n'''
docket_block = '''        rows = query(source_id, f"{dot_column['field_name']}={literal(dot_column, dot_number)}", limit=2)\n        results.append({"source": source_id, "name": name, "join": dot_column["field_name"], "rows": len(rows)})\n\n    legacy_carrier_schema = schemas["6eyk-hxee"]\n    legacy_carrier_docket = find_column(legacy_carrier_schema, DOCKET_ALIASES)\n    if not legacy_carrier_docket:\n        raise RuntimeError("Legacy Carrier archive lost DOCKET_NUMBER lineage field")\n    for source_id, name in DOCKET_SOURCES.items():\n        schema = schemas[source_id]\n        docket_column = find_column(schema, DOCKET_ALIASES)\n        if not docket_column:\n            raise RuntimeError(f"{source_id} {name} has no registered DOCKET_NUMBER field")\n        seed_rows = query(source_id, f"{docket_column['field_name']} is not null", limit=10)\n        linked = None\n        for seed_row in seed_rows:\n            docket = str(seed_row.get(docket_column['field_name']) or '').strip()\n            if not docket:\n                continue\n            parent_rows = query(\n                "6eyk-hxee",\n                f"{legacy_carrier_docket['field_name']}={literal(legacy_carrier_docket, docket)}",\n                limit=2,\n            )\n            if parent_rows:\n                child_rows = query(source_id, f"{docket_column['field_name']}={literal(docket_column, docket)}", limit=2)\n                linked = {"source": source_id, "name": name, "join": docket_column["field_name"], "docket": docket, "rows": len(child_rows), "parent_rows": len(parent_rows)}\n                break\n        if linked is None:\n            raise RuntimeError(f"{source_id} {name} sampled dockets did not resolve to Legacy Carrier")\n        results.append(linked)\n\n    for source_id, name in INSPECTION_CHILD_SOURCES.items():\n'''
if direct_loop_end not in text:
    raise RuntimeError('smoke_carrier_queries.py: direct-source loop anchor missing')
text = text.replace(direct_loop_end, docket_block, 1)
p.write_text(text, encoding='utf-8')

print('legacy docket lineage correction applied')
