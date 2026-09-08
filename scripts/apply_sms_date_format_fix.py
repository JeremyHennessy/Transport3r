#!/usr/bin/env python3
"""Teach the FMCSA contract validator the live SMS Census MCS-150 date encoding.

The current SMS Census source (kjg3-diqy) returns MCS150_DATE values such as
20-OCT-23. That is an FMCSA source-format variant, not invalid data. This one-time
migration adds deterministic DD-MMM-YY / DD-MMM-YYYY parsing to the persisted
contract validator before the final audit transaction commits.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "validate_fmcsa_data_contract.py"
text = TARGET.read_text(encoding="utf-8")
old = '    formats = ["%Y%m%d", "%m%d%Y", "%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]\n'
new = '    formats = ["%Y%m%d", "%m%d%Y", "%Y-%m-%d", "%m/%d/%Y", "%d-%b-%y", "%d-%b-%Y", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"]\n'
count = text.count(old)
if count != 1:
    raise RuntimeError(f"expected exactly one FMCSA date-format list, found {count}")
TARGET.write_text(text.replace(old, new, 1), encoding="utf-8")
print("SMS Census DD-MMM-YY date support applied")
