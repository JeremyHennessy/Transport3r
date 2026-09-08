#!/usr/bin/env python3
"""Diagnostic-only probe for legacy FMCSA authority archive join semantics.

No runtime or scoring logic is changed. The probe inspects each official legacy archive's
live schema and demonstrates whether a carrier can be reached directly by USDOT or must
be reached through a docket bridge from Carrier - All With History.
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
DOCKET_ALIASES = {"DOCKET_NUMBER", "DOCKET_NO", "DOCKET_NUM", "DOCKET"}


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


def main() -> int:
    report: dict[str, Any] = {"status": "ok", "sources": {}}
    schemas: dict[str, dict[str, Any]] = {}
    for source_id, label in LEGACY.items():
        meta = metadata(source_id)
        columns = list(meta.get("columns") or [])
        dot = find_field(columns, DOT_ALIASES)
        docket = find_field(columns, DOCKET_ALIASES)
        if not docket:
            raise RuntimeError(f"{source_id}: expected legacy docket field is missing")
        schemas[source_id] = {"dot": dot, "docket": docket}
        report["sources"][source_id] = {
            "name": label,
            "rows_updated_at": meta.get("rowsUpdatedAt"),
            "dot_field": dot.get("fieldName") if dot else None,
            "dot_type": dot.get("dataTypeName") if dot else None,
            "docket_field": docket.get("fieldName"),
            "docket_type": docket.get("dataTypeName"),
            "field_count": len(columns),
            "join_strategy": "direct_usdot" if dot else "docket_bridge",
        }

    carrier = schemas["6eyk-hxee"]
    if not carrier["dot"] or not carrier["docket"]:
        raise RuntimeError("6eyk-hxee must expose both USDOT and docket for archive bridging")
    dot_field = str(carrier["dot"]["fieldName"])
    docket_field = str(carrier["docket"]["fieldName"])
    seed = resource("6eyk-hxee", {
        "$select": f"{dot_field},{docket_field}",
        "$where": f"{dot_field} is not null and {docket_field} is not null",
        "$limit": "1",
    })
    if not seed:
        raise RuntimeError("6eyk-hxee: no USDOT+docket bridge seed")
    seed_dot = seed[0][dot_field]
    seed_docket = seed[0][docket_field]
    report["bridge_seed"] = {"dot_number": str(seed_dot), "docket_number": str(seed_docket)}

    for source_id, shape in schemas.items():
        dot = shape["dot"]
        docket = shape["docket"]
        if dot:
            field = str(dot["fieldName"])
            where = f"{field}={literal(dot, seed_dot)}"
            strategy = "direct_usdot"
        else:
            field = str(docket["fieldName"])
            where = f"{field}={literal(docket, seed_docket)}"
            strategy = "docket_bridge"
        rows = resource(source_id, {"$select": field, "$where": where, "$limit": "5"})
        report["sources"][source_id]["bridge_test"] = {
            "strategy": strategy,
            "query_field": field,
            "rows": len(rows),
            "matched_seed": len(rows) > 0,
        }

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
