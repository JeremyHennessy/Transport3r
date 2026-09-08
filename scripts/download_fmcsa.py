#!/usr/bin/env python3
"""Stream full FMCSA/DOT DataHub datasets to an immutable local raw snapshot.

Raw outputs are intentionally ignored by Git. Use this script on a durable worker or
warehouse host, then load/normalize the files into the data store. It can also be used
inside a one-off GitHub Actions run for validation, but Actions artifacts are not the
intended long-term system of record.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import shutil
import sys
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "fmcsa_sources.json"
BASE = "https://data.transportation.gov"
USER_AGENT = "Transport3r/0.1 (+https://github.com/JeremyHennessy/Transport3r)"


def download(source: dict[str, Any], output_dir: pathlib.Path, max_bytes: int | None) -> dict[str, Any]:
    dataset_id = source["id"]
    target = output_dir / f"{dataset_id}.csv"
    temporary = target.with_suffix(".csv.partial")
    url = f"{BASE}/api/views/{dataset_id}/rows.csv?accessType=DOWNLOAD"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"})
    digest = hashlib.sha256()
    size = 0

    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if max_bytes is not None and size > max_bytes:
                raise RuntimeError(f"{dataset_id} exceeded --max-bytes={max_bytes:,}")
            digest.update(chunk)
            handle.write(chunk)

    temporary.replace(target)
    return {
        "id": dataset_id,
        "name": source["name"],
        "family": source["family"],
        "downloaded_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "bytes": size,
        "sha256": digest.hexdigest(),
        "path": str(target.relative_to(ROOT)) if target.is_relative_to(ROOT) else str(target),
        "source_url": url,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tier", choices=("core", "all"), default="core")
    parser.add_argument("--source", action="append", default=[], help="Explicit DataHub ID; may be repeated")
    parser.add_argument("--output-root", default="warehouse/raw")
    parser.add_argument("--date", default=dt.date.today().isoformat())
    parser.add_argument("--max-bytes", type=int, default=None, help="Optional safety ceiling per dataset")
    parser.add_argument("--clean", action="store_true", help="Delete the target date directory before downloading")
    args = parser.parse_args()

    catalog: list[dict[str, Any]] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    selected_ids = set(args.source)
    if selected_ids:
        sources = [source for source in catalog if source["id"] in selected_ids]
        missing = selected_ids - {source["id"] for source in sources}
        if missing:
            raise SystemExit(f"Unknown dataset IDs: {', '.join(sorted(missing))}")
    elif args.tier == "all":
        sources = catalog
    else:
        sources = [source for source in catalog if source.get("tier") == "core"]

    output_dir = ROOT / args.output_root / args.date
    if args.clean and output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "snapshot_date": args.date,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "datasets": [],
    }
    failures = 0

    for index, source in enumerate(sources, start=1):
        print(f"[{index}/{len(sources)}] {source['id']} {source['name']}", flush=True)
        try:
            manifest["datasets"].append(download(source, output_dir, args.max_bytes))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            manifest["datasets"].append({
                "id": source["id"],
                "name": source["name"],
                "family": source["family"],
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"FAILED {source['id']}: {exc}", file=sys.stderr, flush=True)

    manifest["completed_at"] = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    manifest["failure_count"] = failures
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Manifest: {manifest_path}")
    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
