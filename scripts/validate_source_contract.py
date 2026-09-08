#!/usr/bin/env python3
"""Fail when Transport3r's FMCSA catalog, runtime map and generated lineage drift."""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "fmcsa_sources.json"
SCHEMAS = ROOT / "public" / "data" / "source-schemas.json"
HEALTH = ROOT / "public" / "data" / "source-health.json"
RUNTIME = ROOT / "src" / "carrierEvidence.ts"

# Official FMCSA Open Data Program contract audited 2026-09-08:
# USDOT entity data (7), modern MOTUS baselines/deltas (12), legacy OA archives (8),
# SMS input/output (8), and New Entrant OOS (1).
REQUIRED_IDS = {
    "az4n-8mr2", "aayw-vxb3", "fx4q-ay7w", "wt8s-2hbx", "876r-jsdb", "5qik-smay", "qbt8-7vic",
    "inys-ebih", "yu5v-wbh6", "c5y8-a4uz", "3uet-3z4i", "6snj-ed7q", "wb4f-neki",
    "nakq-58th", "dm5j-zc6c", "mhr5-hjyc", "x96h-evps", "xe5s-wca7", "e67p-xyd5",
    "6eyk-hxee", "ypjt-5ydn", "qh9u-swkp", "9mw4-x3tu", "2emp-mxtb", "6sqe-dvqs", "96tg-4mhf", "sa6p-acbp",
    "kjg3-diqy", "rbkj-cgst", "4wxs-vbns", "8mt8-2mdr", "m3ry-qcip", "h3zn-uid9", "4y6x-dmck", "h9zy-gjn8",
    "p2mt-9ige",
}


def load(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    catalog = load(CATALOG)
    catalog_ids = [row["id"] for row in catalog]
    if len(catalog_ids) != len(set(catalog_ids)):
        raise RuntimeError("Duplicate FMCSA source IDs in catalog")
    catalog_set = set(catalog_ids)
    if catalog_set != REQUIRED_IDS:
        raise RuntimeError(
            f"Official source contract drift: missing={sorted(REQUIRED_IDS-catalog_set)}, extra={sorted(catalog_set-REQUIRED_IDS)}"
        )

    schemas = load(SCHEMAS)
    schema_set = {row["id"] for row in schemas.get("sources", [])}
    if schema_set != catalog_set or schemas.get("source_count") != len(catalog_set):
        raise RuntimeError(
            f"Schema registry drift: catalog={len(catalog_set)} schemas={len(schema_set)} missing={sorted(catalog_set-schema_set)} extra={sorted(schema_set-catalog_set)}"
        )

    health = load(HEALTH)
    health_set = {row["id"] for row in health.get("sources", [])}
    if health_set != catalog_set or health.get("source_count") != len(catalog_set):
        raise RuntimeError(
            f"Health registry drift: catalog={len(catalog_set)} health={len(health_set)} missing={sorted(catalog_set-health_set)} extra={sorted(health_set-catalog_set)}"
        )

    runtime_text = RUNTIME.read_text(encoding="utf-8")
    source_block = runtime_text.split("export const SOURCE_IDS = {", 1)[1].split("} as const;", 1)[0]
    runtime_set = set(re.findall(r"'([a-z0-9]{4}-[a-z0-9]{4})'", source_block))
    if runtime_set != catalog_set:
        raise RuntimeError(
            f"Runtime source map drift: catalog={len(catalog_set)} runtime={len(runtime_set)} missing={sorted(catalog_set-runtime_set)} extra={sorted(runtime_set-catalog_set)}"
        )

    archived = {row["id"] for row in catalog if row.get("tier") == "archive"}
    expected_archives = {"6eyk-hxee", "ypjt-5ydn", "qh9u-swkp", "9mw4-x3tu", "2emp-mxtb", "6sqe-dvqs", "96tg-4mhf", "sa6p-acbp"}
    if archived != expected_archives:
        raise RuntimeError(f"Legacy archive classification drift: {sorted(archived)}")

    print({
        "status": "ok",
        "source_count": len(catalog_set),
        "schema_field_count": schemas.get("field_count"),
        "legacy_archive_count": len(archived),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
