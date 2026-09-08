#!/usr/bin/env python3
"""Apply the live-verified legacy Insur join alias after docket-lineage migration.

FMCSA ypjt-5ydn exposes PREFIX_DOCKET_NUMBER. A 25-row live probe on 2026-09-08
confirmed those values match 6eyk-hxee DOCKET_NUMBER verbatim (25/25), so no
normalization or prefix transformation is permitted here.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace(path: str, old: str, new: str, expected: int = 1) -> None:
    target = ROOT / path
    text = target.read_text(encoding='utf-8')
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f'{path}: expected {expected} occurrences, found {count}')
    target.write_text(text.replace(old, new), encoding='utf-8')


replace(
    'src/datahub.ts',
    "const DOCKET_ALIASES = ['DOCKET_NUMBER', 'DOCKET_NO'];",
    "const DOCKET_ALIASES = ['PREFIX_DOCKET_NUMBER', 'DOCKET_NUMBER', 'DOCKET_NO'];",
)
replace(
    'scripts/validate_fmcsa_data_contract.py',
    'DOCKET_ALIASES = {"DOCKET_NUMBER", "DOCKET_NO"}',
    'DOCKET_ALIASES = {"PREFIX_DOCKET_NUMBER", "DOCKET_NUMBER", "DOCKET_NO"}',
)
replace(
    'scripts/smoke_carrier_queries.py',
    'DOCKET_ALIASES = {"DOCKET_NUMBER", "DOCKET_NO"}',
    'DOCKET_ALIASES = {"PREFIX_DOCKET_NUMBER", "DOCKET_NUMBER", "DOCKET_NO"}',
)

print('verified PREFIX_DOCKET_NUMBER alias applied')
