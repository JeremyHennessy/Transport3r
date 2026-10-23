# Complete public data loading

Carrier search covers all registrations in the nationwide Company Census. Results
are paginated; pagination is not a carrier-cohort restriction.

Every Carrier 360 section loads its quick preview, followed automatically by all
current published carrier records from the 36 registered sources. When
`VITE_EVIDENCE_API_URL` is configured, complete records come from the verified
nationwide warehouse API and unresolved identities are excluded. Without that
deployment setting, the existing live-source loader remains available and is
explicitly labeled as a live public-source window. The Evidence
tab has a source selector, numbered record pages, every returned field, per-source
exports, and one download of all loaded carrier evidence. Progress and individual
source failures remain visible. A failed request is never a successful empty file.

Complete requests verify counts, stable source row identities, publication metadata
before/after, exact USDOT identities, all inspection parents, and global docket
ownership. Legacy USDOT queries include the original eight-digit representation.
Date windows page through every matching inspection/crash record. Inspection
drilldowns validate the requested parent before loading all child records.

Reports use complete carrier acquisition and complete event windows. Large PDF
appendices use numbered volumes of 1,000 rows to keep printing manageable. The JSON
archive contains all loaded records and fields together. Current-file completeness
does not establish a full lifetime history or a shared historical SMS month.

## Nationwide local warehouse

Install `scripts/requirements-nationwide.txt` in the local Python environment, then:

```powershell
python scripts/nationwide_acquisition.py --workers 4 --build-warehouse
python scripts/nationwide_status.py warehouse/nationwide/raw/COLLECTION-ID
```

This downloads every row of all 36 source files as deterministic gzip, independently
verifies each decompressed CSV against its source count and stable publication
metadata, and retains hashes and raw artifacts. There is no carrier selection or
row limit. It can take hours. An interrupted collection can be resumed with
`--collection PATH`; already verified source cuts are rechecked and reused.
Raw and curated nationwide files are excluded from Git.

After all 36 sources complete, the same process builds a new DuckDB automatically.
Every CSV field is retained as text, preserving identifiers and source date values.
`raw_SOURCE_ID` tables contain all rows; `carrier_SOURCE_ID` views add USDOT mapping
and a mapping status. Ambiguous parents/dockets, missing parents, zero USDOTs and
unresolved identities stay in the raw data and mapping audit. They are not assigned
to an arbitrary carrier. `source_lineage` retains each source's acquisition and
publication evidence. The receipt uses the complete collection timestamp as the
common knowledge-time cut and exposes resolved, identified-only and unresolved
population totals in Carrier 360. Final warehouse promotion requires complete coverage,
unchanged raw hashes, matching counts, and no lost or multiplied rows.

A running download, a partial CSV, or an unfinished DuckDB is not a verified
nationwide warehouse. Consult the collection manifest and warehouse acceptance
record. Start the read-only service with
`python scripts/evidence_api.py warehouse/nationwide/curated/CUT.duckdb`.
Carrier responses require a unique same-cut Census identity and contain all 36
source receipts. Public deployment is selected by the `EVIDENCE_API_URL`
repository variable; direct browser acquisition is the visibly labeled fallback.

## September 9 acceptance examples

Live source acquisition and rendered desktop/mobile checks passed for USDOT
3938496, 2855794 and 3706. USDOT 3706 returned 133,475 records from 36 sources,
including 26,709 inspections and 52,097 inspection-unit records. The record browser
reached inspection page 535 and record 26,709. These are observed acquisition
counts, not permanent carrier totals. At implementation acceptance, the separate
nationwide cut `20261023T190216566877Z-e10ecef3` was certified across all 36
sources: 83,531,140 published/acquired/warehouse rows, with 81,004,526 resolved,
271,159 identified-only and 2,255,455 unresolved mappings. The frozen golden suite
passed 197 same-publication live/warehouse/API checks. These are current-cut data
quality results, not historical-feature or SMS monthly-release certification.
