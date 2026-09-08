#!/usr/bin/env python3
"""Probe configured FMCSA/DOT DataHub datasets and publish health + schema lineage.

This job performs lightweight metadata and one-row checks. It does not commit
nationwide raw datasets into Git; full extraction is handled separately by
scripts/download_fmcsa.py.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import pathlib
import time
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "fmcsa_sources.json"
HEALTH_PATH = ROOT / "public" / "data" / "source-health.json"
SCHEMA_PATH = ROOT / "public" / "data" / "source-schemas.json"
BASE = "https://data.transportation.gov"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"


def fetch_json(url: str, timeout: int = 30, attempts: int = 3) -> Any:
    """Fetch JSON with bounded retries for transient network/TLS failures."""
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except Exception as exc:  # noqa: BLE001 - caller needs the exact upstream error
            last_error = exc
            if attempt < attempts:
                time.sleep(min(4.0, 0.75 * (2 ** (attempt - 1))))
    assert last_error is not None
    raise last_error


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


def compact_column(column: dict[str, Any]) -> dict[str, Any]:
    """Retain the stable Socrata field contract without volatile presentation metadata."""
    return {
        "position": column.get("position"),
        "name": column.get("name"),
        "field_name": column.get("fieldName"),
        "data_type": column.get("dataTypeName"),
        "description": column.get("description"),
    }


def probe(source: dict[str, Any]) -> dict[str, Any]:
    dataset_id = source["id"]
    checked_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    result: dict[str, Any] = {
        "id": dataset_id,
        "name": source["name"],
        "family": source["family"],
        "cadence": source["cadence"],
        "status": "pending",
        "checked_at": checked_at,
        "rows_updated_at": None,
        "schema_fields": None,
        "sample_rows": None,
        "error": None,
        "schema": None,
    }

    metadata_ok = False
    sample_ok = False
    errors: list[str] = []

    try:
        metadata = fetch_json(f"{BASE}/api/views/{dataset_id}")
        metadata_ok = True
        result["rows_updated_at"] = epoch_to_iso(
            metadata.get("rowsUpdatedAt") or metadata.get("rowsUpdatedAtMillis")
        )
        columns = metadata.get("columns") or []
        result["schema_fields"] = len(columns)
        result["schema"] = {
            "id": dataset_id,
            "name": source["name"],
            "family": source["family"],
            "rows_updated_at": result["rows_updated_at"],
            "metadata_url": f"{BASE}/api/views/{dataset_id}",
            "resource_url": f"{BASE}/resource/{dataset_id}.json",
            "download_url": f"{BASE}/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD",
            "columns": [compact_column(column) for column in columns],
        }
    except Exception as exc:  # noqa: BLE001
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
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    health_rows = [{key: value for key, value in row.items() if key != "schema"} for row in results]
    schemas = [row["schema"] for row in results if row.get("schema")]

    health_payload = {
        "generated_at": generated_at,
        "source_count": len(results),
        "healthy_count": sum(row["status"] == "healthy" for row in results),
        "degraded_count": sum(row["status"] == "degraded" for row in results),
        "failed_count": sum(row["status"] == "failed" for row in results),
        "sources": health_rows,
    }
    schema_payload = {
        "generated_at": generated_at,
        "source_count": len(schemas),
        "field_count": sum(len(schema["columns"]) for schema in schemas),
        "sources": schemas,
    }

    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    HEALTH_PATH.write_text(json.dumps(health_payload, indent=2) + "\n", encoding="utf-8")
    SCHEMA_PATH.write_text(json.dumps(schema_payload, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "generated_at": health_payload["generated_at"],
                "source_count": health_payload["source_count"],
                "healthy_count": health_payload["healthy_count"],
                "degraded_count": health_payload["degraded_count"],
                "failed_count": health_payload["failed_count"],
                "schema_source_count": schema_payload["source_count"],
                "schema_field_count": schema_payload["field_count"],
            },
            indent=2,
        )
    )
    return 0 if health_payload["failed_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
