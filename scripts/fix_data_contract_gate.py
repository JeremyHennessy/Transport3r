#!/usr/bin/env python3
"""One-time guarded repair for the FMCSA data-contract audit gate."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected exactly one occurrence, found {count}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "scripts/validate_fmcsa_data_contract.py",
    'formats = ["%Y%m%d", "%m%d%Y", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]',
    'formats = ["%Y%m%d", "%m%d%Y", "%d-%b-%y", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]',
)

replace_once(
    ".github/workflows/probe-fmcsa-branch.yml",
    "      - name: Validate source joins, lineage and normalization\n        run: python scripts/validate_fmcsa_data_contract.py | tee public/data/fmcsa-data-contract-audit.json",
    "      - name: Validate source joins, lineage and normalization\n        run: |\n          set -o pipefail\n          python scripts/validate_fmcsa_data_contract.py | tee public/data/fmcsa-data-contract-audit.json",
)

print("FMCSA data-contract gate repair applied")
