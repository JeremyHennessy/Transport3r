#!/usr/bin/env python3
"""Probe all configured FMCSA/DOT DataHub datasets and publish source health.

This script intentionally performs lightweight metadata + one-row checks. It does not
commit nationwide raw datasets into Git. Full extraction is handled separately by
scripts/download_fmcsa.py.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "fmcsa_sources.json"
OUTPUT_PATH = ROOT / "public" / "data" / "source-health.json"
BASE = "https://data.transportation.gov"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"


def fetch_json(url: str, timeout: int = 30) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def epoch_to_iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return str(value)
    if numeric > 10_000_000_000:
        numeric /= 1000
    return dt.datetime.fromtimestamp(numeric, tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")


def probe(source: dict[str, Any]) -> dict[str, Any]:
    dataset_id = source["id"]
    result: dict[str, Any] = {
        "id": dataset_id,
        "name": source["name"],
        "family": source["family"],
        "cadence": source["cadence"],
        "status": "pending",
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "rows_updated_at": None,
        "schema_fields": None,
        "sample_rows": None,
        "error": None,
    }

    metadata_ok = False
    sample_ok = False
    errors: list[str] = []

    try:
        metadata = fetch_json(f"{BASE}/api/views/{dataset_id}")
        metadata_ok = True
        result["rows_updated_at"] = epoch_to_iso(metadata.get("rowsUpdatedAt") or metadata.get("rowsUpdatedAtMillis"))
        columns = metadata.get("columns") or []
        result["schema_fields"] = len(columns)
    except Exception as exc:  # noqa: BLE001 - probe records exact failure instead of aborting the run
        errors.append(f"metadata: {type(exc).__name__}: {exc}")

    try:
        query = urllib.parse.urlencode({"$limit": "1"})
        sample = fetch_json(f"{BASE}/resource/{dataset_id}.json?{query}")
        sample_ok = isinstance(sample, list)
        result["sample_rows"] = len(sample) if isinstance(sample, list) else None
    except Exception as exc:  # noqa: BLE001
        errors.append(f"row probe: {type(exc).__name__}: {exc}")

    if metadata_ok and sample_ok:
        result["status"] = "healthy"
    elif metadata_ok or sample_ok:
        result["status"] = "degraded"
    else:
        result["status"] = "failed"

    if errors:
        result["error"] = " | ".join(errors)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=6, help="Concurrent source probes")
    parser.add_argument("--probe-only", action="store_true", help="Compatibility flag; probing is the default behavior")
    args = parser.parse_args()

    sources = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(probe, sources))

    results.sort(key=lambda row: (row["family"], row["name"]))
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_count": len(results),
        "healthy_count": sum(row["status"] == "healthy" for row in results),
        "degraded_count": sum(row["status"] == "degraded" for row in results),
        "failed_count": sum(row["status"] == "failed" for row in results),
        "sources": results,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({key: payload[key] for key in ("generated_at", "source_count", "healthy_count", "degraded_count", "failed_count")}, indent=2))
    return 0 if payload["failed_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
