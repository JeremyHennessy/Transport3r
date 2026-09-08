#!/usr/bin/env python3
"""Diagnostic-only probe for legacy FMCSA authority archive join semantics."""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Any

BASE = "https://data.transportation.gov"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"
LEGACY = {
    "6eyk-hxee": "Carrier - All With History",
    "ypjt-5ydn": "Insur - All With History",
    "qh9u-swkp": "ActPendInsur - All With History",
    "9mw4-x3tu": "AuthHist - All With History",
    "2emp-mxtb": "BOC3 - All With History",
    "6sqe-dvqs": "InsHist - All With History",
    "96tg-4mhf": "Rejected - All With History",
    "sa6p-acbp": "Revocation - All With History",
}
DOT_ALIASES = {"DOT_NUMBER", "USDOT_NUMBER", "USDOT_NUM", "USDOT_NO", "DOT_NO", "US_DOT_NUMBER"}
DOCKET_ALIASES = {"DOCKET_NUMBER", "DOCKET_NO", "DOCKET_NUM", "DOCKET", "DOCKETNUMBER", "DOCKETNUM"}


def norm(value: Any) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", str(value or "").strip().upper()).strip("_")


def fetch(url: str, timeout: int = 30, attempts: int = 3) -> Any:
    error: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001
            error = exc
            if attempt + 1 < attempts:
                time.sleep(0.75 * (2**attempt))
    assert error is not None
    raise error


def metadata(source_id: str) -> dict[str, Any]:
    payload = fetch(f"{BASE}/api/views/{source_id}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"{source_id}: non-object metadata")
    return payload


def resource(source_id: str, params: dict[str, str]) -> list[dict[str, Any]]:
    payload = fetch(f"{BASE}/resource/{source_id}.json?{urllib.parse.urlencode(params)}")
    if not isinstance(payload, list):
        raise RuntimeError(f"{source_id}: non-array resource result")
    return payload


def find_field(columns: list[dict[str, Any]], aliases: set[str]) -> dict[str, Any] | None:
    for column in columns:
        if norm(column.get("name")) in aliases or norm(column.get("fieldName")) in aliases:
            return column
    return None


def literal(column: dict[str, Any], value: Any) -> str:
    text = str(value).strip()
    if column.get("dataTypeName") == "number":
        return text
    return "'" + text.replace("'", "''") + "'"


def main() -> int:
    report: dict[str, Any] = {"status": "probe", "sources": {}}
    metadata_by_id: dict[str, dict[str, Any]] = {}
    for source_id, label in LEGACY.items():
        meta = metadata(source_id)
        metadata_by_id[source_id] = meta
        columns = list(meta.get("columns") or [])
        dot = find_field(columns, DOT_ALIASES)
        docket = find_field(columns, DOCKET_ALIASES)
        report["sources"][source_id] = {
            "name": label,
            "dot_field": dot.get("fieldName") if dot else None,
            "docket_field": docket.get("fieldName") if docket else None,
            "all_columns": [
                {"name": c.get("name"), "field_name": c.get("fieldName"), "type": c.get("dataTypeName"), "description": c.get("description")}
                for c in columns
            ],
        }

    carrier_columns = list(metadata_by_id["6eyk-hxee"].get("columns") or [])
    carrier_docket = find_field(carrier_columns, DOCKET_ALIASES)
    if not carrier_docket:
        raise RuntimeError("legacy Carrier docket field missing")
    carrier_field = str(carrier_docket["fieldName"])

    insurance_columns = list(metadata_by_id["ypjt-5ydn"].get("columns") or [])
    prefix = next((c for c in insurance_columns if c.get("fieldName") == "prefix_docket_number"), None)
    if not prefix:
        raise RuntimeError("legacy Insur prefix_docket_number missing")
    prefix_field = str(prefix["fieldName"])

    seeds = resource("ypjt-5ydn", {
        "$select": prefix_field,
        "$where": f"{prefix_field} is not null",
        "$limit": "25",
    })
    lineage_tests = []
    for seed in seeds:
        raw = str(seed.get(prefix_field) or "").strip()
        if not raw:
            continue
        exact = resource("6eyk-hxee", {
            "$select": carrier_field,
            "$where": f"{carrier_field}={literal(carrier_docket, raw)}",
            "$limit": "3",
        })
        lineage_tests.append({"prefix_docket_number": raw, "exact_carrier_matches": len(exact)})
    report["legacy_insurance_lineage_tests"] = lineage_tests
    report["exact_match_count"] = sum(1 for row in lineage_tests if row["exact_carrier_matches"] > 0)

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
