# Transport3r release audit — source → warehouse → API → screen

## First gate: immutable warehouse totals

Run on the **actual deployed** verified nationwide DuckDB, not a synthetic fixture:

```sh
python scripts/audit_warehouse_integrity.py /path/to/verified.duckdb --deep --output /path/to/new-audit.json
```

The audit is read-only, exits nonzero on failed checks, and refuses to overwrite its report. It verifies per-source published/acquired/warehouse/raw row totals, mapping row cardinality and uniqueness, missing mapping rows, reason/status distribution, source SHA-256 receipt alignment, total rows, and (with `--deep`) exact duplicates of original source fields. Preserve the audit JSON and its input warehouse SHA-256 as release evidence. A PASS **does not** certify live UI/API totals or insurance risk.

## Second gate: API/UI reconciliation

Use the exact same warehouse SHA and cut ID exposed by `/healthz`. For at least ten carriers spanning no records, high volume, multiple states, and missing/unresolved identity, compare API carrier evidence with raw/mapping SQL and each displayed card. Record USDOT, source ID, source cut, API response count, rendered count, active filters, date window, truncation, missing-data state and result. Do not treat browser pagination or bounded recent-event slices as lifetime counts. Stop deployment on any unexplained discrepancy.

## Third gate: screenshots and functional tests

After Pages publishes **the merged main commit**, capture desktop and narrow-mobile screenshots for Home, Search, Carrier 360, Insurance, Atlas, Source Health and report views. Test URL sharing, browser back, invalid USDOT, zero records, source timeout, partial slice, keyboard focus, contrast, overflow, maps, export, and the distinction between no data and zero incidents. Record hosted JS bundle hash or commit SHA. A successful workflow alone is not a hosted deployment receipt.

## Geographic and privacy constraints

FEMA NRI county values are community-level relative hazard context; do not apply to carriers as route exposure. HQ, observed event state, geocoded terminal, verified route and hypothetical corridor are separate geometries. No private insurer policy or claims content belongs in public Pages assets. Hazard and actuarial scores remain unavailable until their distinct source, location, claims and calibration gates pass.

## Release decision

Release only when all four are evidenced: (1) immutable data receipts + independent warehouse audit; (2) API/UI totals reconciliation; (3) live SHA and screenshot review; (4) privacy and geographic labeling. Otherwise mark the relevant gate **NOT VERIFIED** rather than PASS.
