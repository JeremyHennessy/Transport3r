#!/usr/bin/env python3
"""Diagnostic-only probe for legacy FMCSA authority archive join semantics.

No runtime or scoring logic is changed. The probe inspects each official legacy archive's
live schema and demonstrates whether a carrier can be reached directly by USDOT or must
be reached through another documented archive key.
"""
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
    url = f"{BASE}/resource/{source_id}.json?{urllib.parse.urlencode(params)}"
    payload = fetch(url)
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


def likely_key_columns(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needles = ("DOT", "DOCKET", "MC", "MX", "FF", "CASE", "FILE", "PREFIX", "NUMBER", "ID")
    out = []
    for column in columns:
        normalized = norm(column.get("name"))
        if any(token in normalized for token in needles):
            out.append({
                "name": column.get("name"),
                "field_name": column.get("fieldName"),
                "type": column.get("dataTypeName"),
                "description": column.get("description"),
            })
    return out


def main() -> int:
    report: dict[str, Any] = {"status": "probe", "sources": {}}
    schemas: dict[str, dict[str, Any]] = {}
    for source_id, label in LEGACY.items():
        meta = metadata(source_id)
        columns = list(meta.get("columns") or [])
        dot = find_field(columns, DOT_ALIASES)
        docket = find_field(columns, DOCKET_ALIASES)
        schemas[source_id] = {"dot": dot, "docket": docket}
        report["sources"][source_id] = {
            "name": label,
            "rows_updated_at": meta.get("rowsUpdatedAt"),
            "dot_field": dot.get("fieldName") if dot else None,
            "dot_type": dot.get("dataTypeName") if dot else None,
            "docket_field": docket.get("fieldName") if docket else None,
            "docket_type": docket.get("dataTypeName") if docket else None,
            "field_count": len(columns),
            "likely_key_columns": likely_key_columns(columns),
        }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
