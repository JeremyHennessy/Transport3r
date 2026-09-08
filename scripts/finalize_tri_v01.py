from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected one match, found {count}: {old[:120]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


directory = ROOT / 'src/CarrierDirectoryApp.tsx'
replace_once(
    directory,
    "                      <a href={`#/carrier/${carrier.dotNumber}/summary`}>Summary</a>\n                      <a href={`#/carrier/${carrier.dotNumber}/safety`}>Safety</a>",
    "                      <a href={`#/carrier/${carrier.dotNumber}/summary`}>Summary</a>\n                      <a href={`#/carrier/${carrier.dotNumber}/score`}>Score</a>\n                      <a href={`#/carrier/${carrier.dotNumber}/safety`}>Safety</a>",
)

ci = ROOT / '.github/workflows/ci.yml'
replace_once(
    ci,
    "      - name: Validate live FMCSA joins and normalization\n        run: python scripts/validate_fmcsa_data_contract.py\n      - run: npm install --no-audit --no-fund",
    "      - name: Validate live FMCSA joins and normalization\n        run: python scripts/validate_fmcsa_data_contract.py\n      - name: Audit Company Census fleet-band consistency\n        run: python scripts/audit_fleet_consistency.py\n      - run: npm install --no-audit --no-fund",
)
replace_once(
    ci,
    "scripts/refresh_fmcsa.py scripts/download_fmcsa.py scripts/smoke_carrier_queries.py scripts/validate_sms_v321_replay.py scripts/validate_source_contract.py scripts/validate_fmcsa_data_contract.py",
    "scripts/refresh_fmcsa.py scripts/download_fmcsa.py scripts/smoke_carrier_queries.py scripts/validate_sms_v321_replay.py scripts/validate_source_contract.py scripts/validate_fmcsa_data_contract.py scripts/audit_fleet_consistency.py",
)

pages = ROOT / '.github/workflows/pages.yml'
replace_once(
    pages,
    "      - name: Validate source registry alignment\n        run: python scripts/validate_source_contract.py\n\n      - name: Install dependencies",
    "      - name: Validate source registry alignment\n        run: python scripts/validate_source_contract.py\n\n      - name: Audit Company Census fleet-band consistency\n        run: python scripts/audit_fleet_consistency.py\n\n      - name: Install dependencies",
)
replace_once(
    pages,
    "          grep -q 'Runtime recovery' /tmp/transport3r-app.js",
    "          grep -q 'Runtime recovery' /tmp/transport3r-app.js\n          grep -q 'TRI_0_1_RESEARCH' /tmp/transport3r-app.js",
)
replace_once(
    pages,
    "          render_route summary '#/carrier/3938496/summary' 'Underwriting evidence at a glance'\n          render_route fleet '#/carrier/3938496/fleet' 'Reported fleet exposure'",
    "          render_route summary '#/carrier/3938496/summary' 'Underwriting evidence at a glance'\n          render_route score '#/carrier/3938496/score' 'Transport Risk Index'\n          grep -Fq 'Research use only' /tmp/transport3r-ui/score.html\n          render_route fleet '#/carrier/3938496/fleet' 'Reported fleet exposure'",
)
replace_once(
    pages,
    '          echo "Rendered route smoke passed for overview, carriers, carrier summary, fleet, insurance, SMS and data sources."',
    '          echo "Rendered route smoke passed for overview, carriers, carrier summary, TRI score, fleet, insurance, SMS and data sources."',
)

print('TRI v0.1 release gates finalized')
