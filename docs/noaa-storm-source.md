# NOAA NCEI Storm Events — verified annual source, not carrier exposure

The official [NOAA NCEI Storm Events database](https://www.ncei.noaa.gov/access/storm-events-database/) provides three related bulk annual CSV.gz source families: `details`, `locations`, and `fatalities`. Their published event-level identifiers are retained for source lineage; this ingestion does **not** join to trucking companies, shipment routes, policies, insured assets, or carrier claims.

Original publisher directory: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/

Official CSV format: https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/Storm-Data-Bulk-csv-Format.pdf

## Source scope

Initial accepted publication is the latest available 2025 annual file cut for each of the three official source tables. The importer reads the official directory listing and **selects the latest `cYYYYMMDD` creation/revision** independently by table, pins those filenames, and re-checks the publisher catalog after the downloads. The 2026 annual data are incomplete and intentionally not used as a complete comparison year.

The ingestion keeps original gzipped files and a manifest of exact URLs, bytes and SHA-256 values. A SQLite source index is built with:

- `event_detail`: one NCEI EVENT_ID; YEAR, STATE, EVENT_TYPE, observed time, county/zone reference and original damage values, plus optional reported start-point coordinates
- `event_location`: EVENT_ID and LOCATION_INDEX key, the publisher-reported point, coordinate status, and explicit parent event-link status
- `event_fatality`: EVENT_ID and FATALITY_ID key only, plus parent link status; excludes individual fatality personal attributes
- `source_receipt`: source cut and stage-specific acceptance metadata

**Reporting caveats:** Storm Events are selective, historically heterogeneous reports of significant weather phenomena, not an exhaustive grid of all hazard occurrences. Coordinates are reported points, not validated areal storm footprints or confirmed facility/route intersections. Damage values are observed reports and **not insurer loss payments**. NOAA files are revised over time; source revision dates and acquisition dates remain separate.

## Reproducible run

```bash
python -m unittest discover -s scripts -p 'test_noaa_storm_events.py' -v
python scripts/noaa_storm_events_ingest.py --year 2025 --output outputs/noaa-storm-2025-v1
```

For a year-specific refresh, use a **new** release directory and explicitly record the publisher revision. Do not overwrite earlier source receipts. Never count a missing source download as a zero-event year.

Dedicated GitHub workflow `.github/workflows/noaa-storm-annual.yml` tests both fixture-level contracts and **real full-year official archive download**, then validates source-to-SQLite row counts, key uniqueness, missing coordinates, source family completeness, and SHA-256 receipt. It preserves original publisher files and a SQLite index as a retained CI artifact.

## Acceptance and integration boundaries

- All three source files must be present; no fabricated table rows.
- Details EVENT_ID must be unique per year. Locations and fatalities maintain independent composite keys; unmatched EVENT_ID counts are recorded explicitly and no join is forced.
- Null/unusable coordinates are retained as NOT_REPORTED/INVALID; never treated as a valid zero-coordinate geometry.
- Source publication revision is checked before and after acquisition; original file hashes and sizes are retained.
- Index and source count must reconcile for all three tables. A passed HTTP connection alone is insufficient.
- No carrier risk or business-interruption score is calculated; verified actual trip traces or operational facilities, independently validated point-to-geometry joins, event date matching and exposure estimates are future requirements.

**Current status:** PR source validation only. It is not installed in the public Transport3r Atlas or a production web API. A carrier name, headquarters location or DOT filing alone is not proof of exposure to an NCEI storm event.
