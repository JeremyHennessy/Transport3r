#!/usr/bin/env python3
"""One-time branch migration for the September 2026 FMCSA source-contract audit.

Every replacement is assertion-guarded so the migration fails instead of silently
editing an unexpected code shape. The durable validation lives in
scripts/validate_source_contract.py and CI; this helper is removed after use.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, count: int | None = None) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    found = text.count(old)
    expected = count if count is not None else 1
    if found != expected:
        raise RuntimeError(f"{path}: expected {expected} occurrences, found {found}: {old[:100]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


# 1) Correct the documented Company Census FLEETSIZE bands.
replace(
    "src/FleetRouteApp.tsx",
    "const FLEET_BANDS:Record<string,string>={'0':'0 power units',A:'1 power unit',B:'2 power units',C:'3–6 power units',D:'7–8 power units',E:'9–10 power units',F:'11–13 power units',G:'14–15 power units',H:'16–18 power units',I:'19–20 power units',J:'21–23 power units',K:'24–26 power units',L:'27–31 power units',M:'32–35 power units',N:'36–44 power units',O:'45–54 power units',P:'55–74 power units',Q:'75–99 power units',R:'100–199 power units',S:'200–299 power units',T:'300–499 power units',U:'500–999 power units',V:'1,000–1,999 power units',W:'2,000–4,999 power units',Z:'5,000+ power units'};",
    "const FLEET_BANDS:Record<string,string>={A:'1 power unit',B:'2–3 power units',C:'4–6 power units',D:'7–8 power units',E:'9–11 power units',F:'12–14 power units',G:'15–17 power units',H:'18–19 power units',I:'20–23 power units',J:'24–28 power units',K:'29–32 power units',L:'33–38 power units',M:'39–44 power units',N:'45–55 power units',O:'56–75 power units',P:'76–100 power units',Q:'101–200 power units',R:'201–300 power units',S:'301–400 power units',T:'401–550 power units',U:'551–999 power units',V:'1,000–2,000 power units',W:'2,001–3,000 power units',X:'3,001–4,000 power units',Y:'4,001–5,000 power units',Z:'Over 5,000 power units'};",
)

# 2) Expand the runtime source map to every current modern feed plus the official
# frozen legacy operating-authority archives. Archives are evidence-only and never
# substitute for modern MOTUS current state.
replace(
    "src/carrierEvidence.ts",
    "  motusAuthDelta: 'dm5j-zc6c',\n  motusInsuranceDelta: 'x96h-evps',",
    "  motusAuthDelta: 'dm5j-zc6c',\n  motusBoc3Delta: 'mhr5-hjyc',\n  motusInsuranceDelta: 'x96h-evps',",
)
replace(
    "src/carrierEvidence.ts",
    "  motusRevokeSuspendDelta: 'e67p-xyd5',\n  smsCensus: 'kjg3-diqy',",
    "  motusRevokeSuspendDelta: 'e67p-xyd5',\n  legacyCarrier: '6eyk-hxee',\n  legacyInsurance: 'ypjt-5ydn',\n  legacyActivePendingInsurance: 'qh9u-swkp',\n  legacyAuthHistory: '9mw4-x3tu',\n  legacyBoc3: '2emp-mxtb',\n  legacyInsuranceHistory: '6sqe-dvqs',\n  legacyRejected: '96tg-4mhf',\n  legacyRevocation: 'sa6p-acbp',\n  smsCensus: 'kjg3-diqy',",
)
replace(
    "src/carrierEvidence.ts",
    "    'motusCarrierDelta', 'motusAuthDelta', 'motusRevokeSuspendDelta', 'newEntrantOos',",
    "    'motusCarrierDelta', 'motusAuthDelta', 'motusBoc3Delta', 'motusRevokeSuspendDelta', 'newEntrantOos',",
)
replace(
    "src/carrierEvidence.ts",
    "    motusAuthDelta: 50,\n    motusInsuranceDelta: 50,",
    "    motusAuthDelta: 50,\n    motusBoc3Delta: 50,\n    motusInsuranceDelta: 50,",
)
replace(
    "src/carrierEvidence.ts",
    "    motusRevokeSuspendDelta: 50,\n    smsCensus: 5,",
    "    motusRevokeSuspendDelta: 50,\n    legacyCarrier: 100,\n    legacyInsurance: 250,\n    legacyActivePendingInsurance: 250,\n    legacyAuthHistory: 300,\n    legacyBoc3: 100,\n    legacyInsuranceHistory: 500,\n    legacyRejected: 200,\n    legacyRevocation: 300,\n    smsCensus: 5,",
)
replace(
    "src/carrierEvidence.ts",
    "    evidence?.slices.motusAuthDelta,\n    evidence?.slices.motusInsuranceDelta,",
    "    evidence?.slices.motusAuthDelta,\n    evidence?.slices.motusBoc3Delta,\n    evidence?.slices.motusInsuranceDelta,",
)

# 3) Current MOTUS insurance uses INS_TYPE_CODE. Also include BOC-3 deltas in
# the Authority change count and card set.
replace(
    "src/CarrierRouteApp.tsx",
    "const recent = rowCount(evidence.slices.motusCarrierDelta) + rowCount(evidence.slices.motusAuthDelta) + rowCount(evidence.slices.motusRevokeSuspendDelta);",
    "const recent = rowCount(evidence.slices.motusCarrierDelta) + rowCount(evidence.slices.motusAuthDelta) + rowCount(evidence.slices.motusBoc3Delta) + rowCount(evidence.slices.motusRevokeSuspendDelta);",
)
replace(
    "src/CarrierRouteApp.tsx",
    "['INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']",
    "['INS_TYPE_CODE', 'INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']",
    count=2,
)
replace(
    "src/CarrierRouteApp.tsx",
    "</article><article><span>Revoke/suspend delta</span><strong>{rowCountLabel(evidence.slices.motusRevokeSuspendDelta)}</strong>",
    "</article><article><span>BOC-3 delta</span><strong>{rowCountLabel(evidence.slices.motusBoc3Delta)}</strong><p>Process-agent changes from the latest daily difference feed.</p></article><article><span>Revoke/suspend delta</span><strong>{rowCountLabel(evidence.slices.motusRevokeSuspendDelta)}</strong>",
)

# 4) Keep the workspace source-purpose map aligned with the catalog.
replace(
    "src/WorkspaceApp.tsx",
    "sources: ['nakq-58th', 'dm5j-zc6c', 'x96h-evps', 'xe5s-wca7', 'e67p-xyd5'],",
    "sources: ['nakq-58th', 'dm5j-zc6c', 'mhr5-hjyc', 'x96h-evps', 'xe5s-wca7', 'e67p-xyd5'],",
)
needle = """  {\n    title: 'Change detection',\n    eyebrow: '24-hour MOTUS deltas',"""
legacy_block = """  {\n    title: 'Legacy authority archive',\n    eyebrow: 'Frozen pre-MOTUS baseline',\n    description: 'Preserve the eight official legacy operating-authority files for historical continuity only. They never override modern MOTUS current status.',\n    sources: ['6eyk-hxee', 'ypjt-5ydn', 'qh9u-swkp', '9mw4-x3tu', '2emp-mxtb', '6sqe-dvqs', '96tg-4mhf', 'sa6p-acbp'],\n    action: 'Historical lineage only',\n  },\n""" + needle
replace("src/WorkspaceApp.tsx", needle, legacy_block)

# 5) Correct SMS v3.21 data-sufficiency metadata. For HOS, vehicle maintenance,
# HM and driver fitness, FMCSA requires N relevant inspections AND at least one
# inspection with a BASIC violation; it does not require N violation inspections.
for basic, old in [
    ("hosCompliance", "sufficientViolationInspections: 3"),
    ("driverFitness", "sufficientViolationInspections: 5"),
    ("vehicleMaintenance", "sufficientViolationInspections: 5"),
    ("hmCompliance", "sufficientViolationInspections: 5"),
]:
    # Scope the replacement through a nearby BASIC key to avoid changing Unsafe Driving's correct 3.
    path = ROOT / "src/smsRules.ts"
    text = path.read_text(encoding="utf-8")
    marker = f"{basic}: {{"
    start = text.index(marker)
    end = text.find("\n  },", start)
    block = text[start:end]
    if old not in block:
        raise RuntimeError(f"smsRules.ts: {basic} missing expected {old}")
    block = block.replace(old, "sufficientViolationInspections: 1")
    text = text[:start] + block + text[end:]
    path.write_text(text, encoding="utf-8")

# Controlled Substances/Alcohol does not receive the extra +2 OOS severity treatment.
replace(
    "src/smsReplay.ts",
    "      const severity = readNumber(row, ['TOTAL_SEVERITY_WGHT', 'TOTAL_SEVERITY_WEIGHT'])\n        ?? ((readNumber(row, ['SEVERITY_WEIGHT', 'SEVERITY_WGHT', 'SEVERITY']) ?? 0)\n          + (readNumber(row, ['OOS_WEIGHT', 'OUT_OF_SERVICE_WEIGHT']) ?? 0));",
    "      const publishedTotal = readNumber(row, ['TOTAL_SEVERITY_WGHT', 'TOTAL_SEVERITY_WEIGHT']);\n      const baseSeverity = readNumber(row, ['SEVERITY_WEIGHT', 'SEVERITY_WGHT', 'SEVERITY']) ?? 0;\n      const oosWeight = basic === 'controlledSubstances' ? 0 : (readNumber(row, ['OOS_WEIGHT', 'OUT_OF_SERVICE_WEIGHT']) ?? 0);\n      const severity = publishedTotal ?? (baseSeverity + oosWeight);",
)

# 6) Expand the catalog with the eight FMCSA-designated legacy archives.
catalog_path = ROOT / "data/fmcsa_sources.json"
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
legacy = [
    {"id":"6eyk-hxee","name":"Carrier - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS carrier/authority baseline; last operational refresh May 14 2026","role":"historical continuity and backward-reference only; never current authority state","tier":"archive","history":"legacy all-with-history"},
    {"id":"ypjt-5ydn","name":"Insur - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS active/pending insurance baseline","role":"historical insurance reference only; modern MOTUS governs current filings","tier":"archive","history":"legacy all-with-history"},
    {"id":"qh9u-swkp","name":"ActPendInsur - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS active/pending policy implementation records","role":"historical posted/effective/cancellation reference only","tier":"archive","history":"legacy all-with-history"},
    {"id":"9mw4-x3tu","name":"AuthHist - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS operating-authority lifecycle history","role":"historical granted/revoked authority actions; not current state","tier":"archive","history":"legacy all-with-history"},
    {"id":"2emp-mxtb","name":"BOC3 - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS process-agent assignments","role":"historical BOC-3 roster reference only","tier":"archive","history":"legacy all-with-history"},
    {"id":"6sqe-dvqs","name":"InsHist - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS insurance filing history","role":"historical cancellation/replacement/change reference only","tier":"archive","history":"legacy all-with-history"},
    {"id":"96tg-4mhf","name":"Rejected - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS rejected operating-authority actions","role":"historical rejected-action evidence only","tier":"archive","history":"legacy all-with-history"},
    {"id":"sa6p-acbp","name":"Revocation - All With History (Legacy Archive)","family":"MOTUS Legacy Archive","cadence":"frozen","scope":"pre-MOTUS revocation history","role":"historical revoked-authority evidence only; modern RevokeSuspend governs current architecture","tier":"archive","history":"legacy all-with-history"},
]
existing = {row['id'] for row in catalog}
for row in legacy:
    if row['id'] not in existing:
        catalog.append(row)
catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")

# 7) Smoke test must cover the entire catalog, not a hand-maintained count.
replace(
    "scripts/smoke_carrier_queries.py",
    "SCHEMA_PATH = ROOT / \"public\" / \"data\" / \"source-schemas.json\"\nBASE =",
    "SCHEMA_PATH = ROOT / \"public\" / \"data\" / \"source-schemas.json\"\nCATALOG_PATH = ROOT / \"data\" / \"fmcsa_sources.json\"\nBASE =",
)
replace(
    "scripts/smoke_carrier_queries.py",
    '    "dm5j-zc6c": "MOTUS AuthHist Daily Difference",\n    "x96h-evps": "MOTUS Insurance Daily Difference",',
    '    "dm5j-zc6c": "MOTUS AuthHist Daily Difference",\n    "mhr5-hjyc": "MOTUS BOC3 Daily Difference",\n    "x96h-evps": "MOTUS Insurance Daily Difference",',
)
replace(
    "scripts/smoke_carrier_queries.py",
    '    "p2mt-9ige": "New Entrant OOS",\n}',
    '    "p2mt-9ige": "New Entrant OOS",\n    "6eyk-hxee": "Legacy Carrier",\n    "ypjt-5ydn": "Legacy Insurance",\n    "qh9u-swkp": "Legacy Active/Pending Insurance",\n    "9mw4-x3tu": "Legacy Authority History",\n    "2emp-mxtb": "Legacy BOC3",\n    "6sqe-dvqs": "Legacy Insurance History",\n    "96tg-4mhf": "Legacy Rejected",\n    "sa6p-acbp": "Legacy Revocation",\n}',
)
replace(
    "scripts/smoke_carrier_queries.py",
    "    expected_sources = set(DIRECT_DOT_SOURCES) | set(INSPECTION_CHILD_SOURCES)\n    missing_schemas = sorted(expected_sources - set(schemas))\n    if missing_schemas:\n        raise RuntimeError(f\"Missing schema registry entries: {', '.join(missing_schemas)}\")\n    if len(expected_sources) != 27:\n        raise RuntimeError(f\"Smoke source registry expected 27 configured datasets, found {len(expected_sources)}\")",
    "    catalog_ids = {row['id'] for row in json.loads(CATALOG_PATH.read_text(encoding='utf-8'))}\n    expected_sources = set(DIRECT_DOT_SOURCES) | set(INSPECTION_CHILD_SOURCES)\n    if expected_sources != catalog_ids:\n        missing_runtime = sorted(catalog_ids - expected_sources)\n        extra_runtime = sorted(expected_sources - catalog_ids)\n        raise RuntimeError(f\"Runtime/catalog source drift: missing={missing_runtime}, extra={extra_runtime}\")\n    missing_schemas = sorted(expected_sources - set(schemas))\n    if missing_schemas:\n        raise RuntimeError(f\"Missing schema registry entries: {', '.join(missing_schemas)}\")",
)
replace(
    "scripts/smoke_carrier_queries.py",
    "All 27 configured source families are covered:",
    "Every configured source in data/fmcsa_sources.json is covered:",
)

# 8) CI regenerates schema/health from the official portal before building/testing,
# so source additions cannot race a stale checked-in registry.
ci = """name: CI\n\non:\n  pull_request:\n    branches: [main]\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 22\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n      - name: Refresh official FMCSA source contract\n        run: python scripts/refresh_fmcsa.py --workers 6\n      - name: Validate source registry alignment\n        run: python scripts/validate_source_contract.py\n      - run: npm install --no-audit --no-fund\n      - run: npm run typecheck\n      - run: npm run build\n      - name: Validate Python entrypoints compile\n        run: python -m py_compile scripts/refresh_fmcsa.py scripts/download_fmcsa.py scripts/smoke_carrier_queries.py scripts/validate_sms_v321_replay.py scripts/validate_source_contract.py\n      - name: Smoke live FMCSA Carrier 360 query joins\n        run: python scripts/smoke_carrier_queries.py\n      - name: Validate SMS v3.21 measure replay against FMCSA\n        run: python scripts/validate_sms_v321_replay.py\n"""
(ROOT / ".github/workflows/ci.yml").write_text(ci, encoding="utf-8")

# Pages also refreshes before Vite copies public/ into dist, and the hosted gate
# verifies the official 36-source contract rather than the obsolete 27-source count.
replace(
    ".github/workflows/pages.yml",
    "      - name: Install dependencies\n        run: npm install --no-audit --no-fund",
    "      - name: Set up Python\n        uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n\n      - name: Refresh official FMCSA source contract\n        run: python scripts/refresh_fmcsa.py --workers 6\n\n      - name: Validate source registry alignment\n        run: python scripts/validate_source_contract.py\n\n      - name: Install dependencies\n        run: npm install --no-audit --no-fund",
)
replace(
    ".github/workflows/pages.yml",
    "          assert len(health.get('sources', [])) == 27, health\n          assert schemas.get('source_count') == 27, schemas.get('source_count')",
    "          assert len(health.get('sources', [])) == 36, health\n          assert schemas.get('source_count') == 36, schemas.get('source_count')",
)
replace(
    ".github/workflows/pages.yml",
    "          render_route fleet '#/carrier/3938496/fleet' 'Fleet evidence'",
    "          render_route fleet '#/carrier/3938496/fleet' 'Reported fleet exposure'",
)
replace(
    ".github/workflows/pages.yml",
    "          render_route sources '#/sources' 'All 27 configured FMCSA/DOT datasets'",
    "          render_route sources '#/sources' 'All 36 configured FMCSA/DOT datasets'",
)

print("FMCSA source audit fixes applied")
