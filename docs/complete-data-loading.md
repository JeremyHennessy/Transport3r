# Complete public data loading

Carrier search covers all registrations in the nationwide Company Census. Results
are paginated; pagination is not a carrier-cohort restriction.

Every Carrier 360 section loads its quick preview, followed automatically by all
current published carrier records from the 36 registered sources. The Evidence
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

This downloads every row of all 36 source files, independently verifies each full
CSV against its source count and stable publication metadata, and retains hashes
and raw artifacts. There is no carrier selection or row limit. It can take hours.
Raw and curated nationwide files are excluded from Git.

After all 36 sources complete, the same process builds a new DuckDB automatically.
Every CSV field is retained as text, preserving identifiers and source date values.
`raw_SOURCE_ID` tables contain all rows; `carrier_SOURCE_ID` views add USDOT mapping
and a mapping status. Ambiguous parents/dockets, missing parents, zero USDOTs and
unresolved identities stay in the raw data and mapping audit. They are not assigned
to an arbitrary carrier. `source_lineage` retains each source's acquisition and
publication evidence. Final warehouse promotion requires complete coverage,
unchanged raw hashes, matching counts, and no lost or multiplied rows.

A running download, a partial CSV, or an unfinished DuckDB is not a verified
nationwide warehouse. Consult the collection manifest and warehouse acceptance
record. The public app uses the official source APIs directly and can load complete
carrier detail independently of this local bulk acquisition.

## September 9 acceptance examples

Live source acquisition and rendered desktop/mobile checks passed for USDOT
3938496, 2855794 and 3706. USDOT 3706 returned 133,475 records from 36 sources,
including 26,709 inspections and 52,097 inspection-unit records. The record browser
reached inspection page 535 and record 26,709. These are observed acquisition
counts, not permanent carrier totals. At implementation acceptance, the separate
nationwide bulk acquisition was still in progress and was not yet certified.
