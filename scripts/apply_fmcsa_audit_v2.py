#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sub(path: str, pattern: str, replacement: str, count: int = 1) -> None:
    p = ROOT / path
    text = p.read_text(encoding='utf-8')
    new, n = re.subn(pattern, replacement, text, count=count, flags=re.S)
    if n != count:
        raise RuntimeError(f'{path}: expected {count} replacement(s), got {n}: {pattern[:100]}')
    p.write_text(new, encoding='utf-8')


# Company Census FLEETSIZE code bands: correct the display mapping to the current
# MCMIS/Company Census code ranges. Do not infer fleet from inspection observations.
sub(
    'src/FleetRouteApp.tsx',
    r"const FLEET_BANDS:Record<string,string>=\{.*?\};",
    "const FLEET_BANDS:Record<string,string>={A:'1 power unit',B:'2–3 power units',C:'4–6 power units',D:'7–8 power units',E:'9–11 power units',F:'12–14 power units',G:'15–17 power units',H:'18–19 power units',I:'20–23 power units',J:'24–28 power units',K:'29–32 power units',L:'33–38 power units',M:'39–44 power units',N:'45–55 power units',O:'56–75 power units',P:'76–100 power units',Q:'101–200 power units',R:'201–300 power units',S:'301–400 power units',T:'401–550 power units',U:'551–999 power units',V:'1,000–2,000 power units',W:'2,001–3,000 power units',X:'3,001–4,000 power units',Y:'4,001–5,000 power units',Z:'Over 5,000 power units'};",
)

# Carrier 360 field and delta corrections.
sub(
    'src/CarrierRouteApp.tsx',
    r"const recent = rowCount\(evidence\.slices\.motusCarrierDelta\) \+ rowCount\(evidence\.slices\.motusAuthDelta\) \+ rowCount\(evidence\.slices\.motusRevokeSuspendDelta\);",
    "const recent = rowCount(evidence.slices.motusCarrierDelta) + rowCount(evidence.slices.motusAuthDelta) + rowCount(evidence.slices.motusBoc3Delta) + rowCount(evidence.slices.motusRevokeSuspendDelta);",
)
sub(
    'src/CarrierRouteApp.tsx',
    r"\['INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE'\]",
    "['INS_TYPE_CODE', 'INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']",
    count=2,
)
sub(
    'src/CarrierRouteApp.tsx',
    r"(<article><span>Authority history delta</span><strong>\{rowCountLabel\(evidence\.slices\.motusAuthDelta\)\}</strong><p>New lifecycle-history rows in the daily difference feed\.</p></article>)(<article><span>Revoke/suspend delta</span>)",
    r"\1<article><span>BOC-3 delta</span><strong>{rowCountLabel(evidence.slices.motusBoc3Delta)}</strong><p>Process-agent changes from the latest daily difference feed.</p></article>\2",
)

# SMS v3.21 data sufficiency: HOS requires 3 relevant + >=1 BASIC violation;
# Driver Fitness, Vehicle Maintenance and HM require 5 relevant + >=1 BASIC violation.
for key in ('hos', 'driverFitness', 'vehicleMaintenance', 'hazmat'):
    p = ROOT / 'src/smsRules.ts'
    text = p.read_text(encoding='utf-8')
    start = text.index(f'  {key}: {{')
    end = text.index('\n  },', start)
    block = text[start:end]
    block2, n = re.subn(r'sufficientViolationInspections: \d+', 'sufficientViolationInspections: 1', block, count=1)
    if n != 1:
        raise RuntimeError(f'src/smsRules.ts: could not correct {key} violation sufficiency')
    p.write_text(text[:start] + block2 + text[end:], encoding='utf-8')

# Controlled Substances/Alcohol receives no OOS severity increment under SMS v3.21.
sub(
    'src/smsReplay.ts',
    r"const totalSeverity = readNumber\(row, \['TOTAL_SEVERITY_WGHT'\]\);\n    const severity = totalSeverity \?\? \(\n      numeric\(readValue\(row, \['SEVERITY_WEIGHT'\]\)\) \+ numeric\(readValue\(row, \['OOS_WEIGHT'\]\)\)\n    \);",
    "const totalSeverity = readNumber(row, ['TOTAL_SEVERITY_WGHT']);\n    const baseSeverity = numeric(readValue(row, ['SEVERITY_WEIGHT']));\n    const oosWeight = basic === 'controlledSubstances' ? 0 : numeric(readValue(row, ['OOS_WEIGHT']));\n    const severity = totalSeverity ?? (baseSeverity + oosWeight);",
)

# Workspace: include the already-configured modern BOC3 delta.
sub(
    'src/WorkspaceApp.tsx',
    r"sources: \['nakq-58th', 'dm5j-zc6c', 'x96h-evps', 'xe5s-wca7', 'e67p-xyd5'\]",
    "sources: ['nakq-58th', 'dm5j-zc6c', 'mhr5-hjyc', 'x96h-evps', 'xe5s-wca7', 'e67p-xyd5']",
)

# Add FMCSA's eight frozen legacy operating-authority archives as historical evidence.
# They are evidence-only and must never override modern MOTUS current status.
catalog_path = ROOT / 'data/fmcsa_sources.json'
catalog = json.loads(catalog_path.read_text(encoding='utf-8'))
archives = [
    ('6eyk-hxee','Carrier - All With History (Legacy Archive)','carrier/authority baseline'),
    ('ypjt-5ydn','Insur - All With History (Legacy Archive)','active/pending insurance baseline'),
    ('qh9u-swkp','ActPendInsur - All With History (Legacy Archive)','insurance implementation dates'),
    ('9mw4-x3tu','AuthHist - All With History (Legacy Archive)','authority lifecycle history'),
    ('2emp-mxtb','BOC3 - All With History (Legacy Archive)','process-agent assignments'),
    ('6sqe-dvqs','InsHist - All With History (Legacy Archive)','insurance filing history'),
    ('96tg-4mhf','Rejected - All With History (Legacy Archive)','rejected insurance forms'),
    ('sa6p-acbp','Revocation - All With History (Legacy Archive)','revocation history'),
]
existing = {r['id'] for r in catalog}
for sid, name, scope in archives:
    if sid not in existing:
        catalog.append({
            'id': sid,
            'name': name,
            'family': 'MOTUS Legacy Archive',
            'cadence': 'frozen',
            'scope': f'Pre-MOTUS {scope}; retained by FMCSA for historical continuity',
            'role': 'Historical lineage only; never substitute for modern MOTUS current authority or insurance state',
            'tier': 'archive',
            'history': 'legacy frozen baseline',
        })
catalog_path.write_text(json.dumps(catalog, indent=2) + '\n', encoding='utf-8')

# Runtime source map: legacy files load only on the Evidence sweep because no normal
# decision tab lists them in MODE_KEYS.
p = ROOT / 'src/carrierEvidence.ts'
text = p.read_text(encoding='utf-8')
anchor = "  motusRevokeSuspendDelta: 'e67p-xyd5',\n"
if "legacyCarrier: '6eyk-hxee'" not in text:
    legacy_ids = (
        "  legacyCarrier: '6eyk-hxee',\n"
        "  legacyInsurance: 'ypjt-5ydn',\n"
        "  legacyActivePendingInsurance: 'qh9u-swkp',\n"
        "  legacyAuthHistory: '9mw4-x3tu',\n"
        "  legacyBoc3: '2emp-mxtb',\n"
        "  legacyInsuranceHistory: '6sqe-dvqs',\n"
        "  legacyRejected: '96tg-4mhf',\n"
        "  legacyRevocation: 'sa6p-acbp',\n"
    )
    if anchor not in text:
        raise RuntimeError('carrierEvidence.ts: legacy insertion anchor missing')
    text = text.replace(anchor, anchor + legacy_ids, 1)
p.write_text(text, encoding='utf-8')

# Workspace gets a separate archive family to prevent modern/legacy semantic mixing.
p = ROOT / 'src/WorkspaceApp.tsx'
text = p.read_text(encoding='utf-8')
if "title: 'Legacy authority archive'" not in text:
    marker = "  {\n    title: 'Change detection',"
    block = "  {\n    title: 'Legacy authority archive',\n    eyebrow: 'Frozen pre-MOTUS baseline',\n    description: 'Eight official legacy authority files retained for historical continuity. They never override modern MOTUS current state.',\n    sources: ['6eyk-hxee', 'ypjt-5ydn', 'qh9u-swkp', '9mw4-x3tu', '2emp-mxtb', '6sqe-dvqs', '96tg-4mhf', 'sa6p-acbp'],\n    action: 'Historical lineage only',\n  },\n"
    if marker not in text:
        raise RuntimeError('WorkspaceApp.tsx: DATA_FAMILIES insertion anchor missing')
    text = text.replace(marker, block + marker, 1)
p.write_text(text, encoding='utf-8')

# Smoke test follows the catalog dynamically and includes all 36 source joins.
p = ROOT / 'scripts/smoke_carrier_queries.py'
text = p.read_text(encoding='utf-8')
text = text.replace('All 27 configured source families are covered:', 'Every configured source in data/fmcsa_sources.json is covered:')
text = text.replace("SCHEMA_PATH = ROOT / \"public\" / \"data\" / \"source-schemas.json\"\n", "SCHEMA_PATH = ROOT / \"public\" / \"data\" / \"source-schemas.json\"\nCATALOG_PATH = ROOT / \"data\" / \"fmcsa_sources.json\"\n")
if '"mhr5-hjyc"' not in text:
    text = text.replace('    "dm5j-zc6c": "MOTUS AuthHist Daily Difference",\n', '    "dm5j-zc6c": "MOTUS AuthHist Daily Difference",\n    "mhr5-hjyc": "MOTUS BOC3 Daily Difference",\n')
for sid, label in [
    ('6eyk-hxee','Legacy Carrier'),('ypjt-5ydn','Legacy Insurance'),('qh9u-swkp','Legacy Active/Pending Insurance'),
    ('9mw4-x3tu','Legacy Authority History'),('2emp-mxtb','Legacy BOC3'),('6sqe-dvqs','Legacy Insurance History'),
    ('96tg-4mhf','Legacy Rejected'),('sa6p-acbp','Legacy Revocation')]:
    if f'"{sid}"' not in text:
        text = text.replace('    "p2mt-9ige": "New Entrant OOS",\n', f'    "{sid}": "{label}",\n    "p2mt-9ige": "New Entrant OOS",\n', 1)
old = '''    expected_sources = set(DIRECT_DOT_SOURCES) | set(INSPECTION_CHILD_SOURCES)\n    missing_schemas = sorted(expected_sources - set(schemas))\n    if missing_schemas:\n        raise RuntimeError(f"Missing schema registry entries: {', '.join(missing_schemas)}")\n    if len(expected_sources) != 27:\n        raise RuntimeError(f"Smoke source registry expected 27 configured datasets, found {len(expected_sources)}")'''
new = '''    catalog_ids = {row["id"] for row in json.loads(CATALOG_PATH.read_text(encoding="utf-8"))}\n    expected_sources = set(DIRECT_DOT_SOURCES) | set(INSPECTION_CHILD_SOURCES)\n    if expected_sources != catalog_ids:\n        raise RuntimeError(f"Runtime/catalog source drift: missing={sorted(catalog_ids-expected_sources)}, extra={sorted(expected_sources-catalog_ids)}")\n    missing_schemas = sorted(expected_sources - set(schemas))\n    if missing_schemas:\n        raise RuntimeError(f"Missing schema registry entries: {', '.join(missing_schemas)}")'''
if old not in text:
    raise RuntimeError('smoke_carrier_queries.py: source-count block changed unexpectedly')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')

# CI regenerates the official schema/health snapshots before semantic validation.
(ROOT / '.github/workflows/ci.yml').write_text('''name: CI\n\non:\n  pull_request:\n    branches: [main]\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\njobs:\n  validate:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-node@v4\n        with:\n          node-version: 22\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n      - name: Refresh official FMCSA source contract\n        run: python scripts/refresh_fmcsa.py --workers 6\n      - name: Validate source registry alignment\n        run: python scripts/validate_source_contract.py\n      - name: Validate live FMCSA joins and normalization\n        run: python scripts/validate_fmcsa_data_contract.py\n      - run: npm install --no-audit --no-fund\n      - run: npm run typecheck\n      - run: npm run build\n      - name: Validate Python entrypoints compile\n        run: python -m py_compile scripts/refresh_fmcsa.py scripts/download_fmcsa.py scripts/smoke_carrier_queries.py scripts/validate_sms_v321_replay.py scripts/validate_source_contract.py scripts/validate_fmcsa_data_contract.py\n      - name: Smoke live FMCSA Carrier 360 query joins\n        run: python scripts/smoke_carrier_queries.py\n      - name: Validate SMS v3.21 measure replay against FMCSA\n        run: python scripts/validate_sms_v321_replay.py\n''', encoding='utf-8')

# Pages must build from a freshly regenerated registry; never deploy stale source snapshots.
p = ROOT / '.github/workflows/pages.yml'
text = p.read_text(encoding='utf-8')
text = text.replace("      - name: Install dependencies\n        run: npm install --no-audit --no-fund\n", "      - name: Set up Python\n        uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n\n      - name: Refresh official FMCSA source contract\n        run: python scripts/refresh_fmcsa.py --workers 6\n\n      - name: Validate source registry alignment\n        run: python scripts/validate_source_contract.py\n\n      - name: Install dependencies\n        run: npm install --no-audit --no-fund\n", 1)
text = text.replace("assert len(health.get('sources', [])) == 27, health", "assert len(health.get('sources', [])) == 36, health")
text = text.replace("assert schemas.get('source_count') == 27, schemas.get('source_count')", "assert schemas.get('source_count') == 36, schemas.get('source_count')")
text = text.replace("render_route fleet '#/carrier/3938496/fleet' 'Fleet evidence'", "render_route fleet '#/carrier/3938496/fleet' 'Reported fleet exposure'")
text = text.replace("render_route sources '#/sources' 'All 27 configured FMCSA/DOT datasets'", "render_route sources '#/sources' 'All 36 configured FMCSA/DOT datasets'")
p.write_text(text, encoding='utf-8')

print('reconciled FMCSA audit corrections applied')
