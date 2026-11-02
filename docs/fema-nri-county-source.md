# FEMA National Risk Index county source acceptance (v1.20)

## Source and intended use

Official published ZIP (returned HTTP 403 to GitHub Actions on Nov 2, 2026): https://www.fema.gov/about/reports-and-data/openfema/nri/v120/NRI_Table_Counties.zip

**Official fallback selected for active acquisition:** FEMA's December 2025 v1.20.0 public ArcGIS FeatureServer county layer: https://services.arcgis.com/XG15cJAlne2vxtgt/ArcGIS/rest/services/National_Risk_Index_Counties/FeatureServer/0 . The layer's published metadata identifies the source as National Risk Index Counties and carries a publisher data-update watermark. It is a separate official distribution, not a mirror of unknown provenance.

Official FEMA technical documentation: https://www.fema.gov/sites/default/files/documents/fema_national-risk-index_technical-documentation.pdf

This module **downloads and verifies FEMA's National Risk Index v1.20 county-level tabular file at its native STCOFIPS grain**. It is a data-foundation task for Transport3r's future geography Atlas, not a carrier-scoring feature.

The source contains FEMA's **relative community risk ratings, scores, and expected annual loss** estimates. Those are not empirical insured transport losses or carrier-specific risk scores. No carrier location, depot, route, H3 cell, facility, policy, claim or identity is joined.

## Reproducible execution

```bash
python -m unittest discover -s scripts -p 'test_nri_county_ingest.py' -v
python scripts/nri_county_ingest.py --output outputs/nri-v120-$(date -u +%Y%m%dT%H%M%SZ) --arcgis
```

For an independently saved, verified source archive:

```bash
python scripts/nri_county_ingest.py --archive /secure/official/NRI_Table_Counties.zip --output outputs/nri-replay-001
```

Never replace an existing release directory. Each output contains:

- `source_table.zip`: for ArcGIS acquisitions, a deterministic **reconstructed** CSV container, NOT the original FEMA ZIP. For direct ZIP acquisition, it is the original ZIP. The manifest identifies which representation was used.
- `arcgis-original-responses/`: original UTF-8 JSON publisher metadata, exact count responses and every ordered page, with original URL, SHA-256 and row counts in the manifest; these exist only for ArcGIS acquisition
- `counties.csv`: deterministic FIPS-sorted normalized county rows; SHA-256 in the same manifest
- `manifest.json`: source URL/final redirect, acquisition UTC timestamp, observed source fields, version, original and normalized hashes, downloaded/accepted/rejected/unknown-score counts, validation state and strict no-carrier-risk flags

The downloader refuses non-HTTPS redirects, archives larger than 85 MB, CSV decompression larger than 150 MB, wrong/duplicate CSV members, missing required source columns, duplicate or malformed five-digit FIPS codes, invalid source risk numeric values, unrecognized release versions, excessive rows, and less than 3,000 source rows in production mode. The ArcGIS path also requires the exact FEMA layer identity, all contracted fields, unique ordered OBJECTID values, reconciled publisher counts and unchanged source schema/data-update watermark before and after pagination. A rejected raw file remains as immutable evidence and the normalized release is **not** promoted.

The dedicated `.github/workflows/nri-county-source.yml` workflow executes offline contract tests and captures the official FEMA ArcGIS FeatureServer, then uploads all original JSON pages, reconstructed source table, normalized county file, and a provenance receipt as a GitHub Actions artifact. An archive supplied with `--archive` undergoes content QA but **does not prove origin** unless the archive is independently verified. CI success is required before any source is marked validated; a connection probe alone is insufficient.

## Next step after successful source ingest

- Independently validate public county geometry/vintage and exact county FIPS crosswalk against a licensed geographic base.
- Query FEMA's county metrics **only** for independently verified terminal coordinates or confirmed route/stop geometries with stated spatial uncertainty.
- Preserve mapped/unmapped classification, uncertainty, source observation date, rating scale and source data vintage. Do not automatically treat a carrier's MCS-150 address as an operating route or hazard exposure.
- H3 overlay cells must distinguish directly sampled hazard data from estimated or decayed context; any distance-decay rule is a separately versioned *model*, never an official FEMA score.
- Do not derive probability of insurance loss, claim severity, renewal premium, or bind/decline outcomes until insured exposure and outcome validation exists.

**Current release boundary:** Source ingestion and QA only; the public GitHub Pages Atlas continues labeling this source **Not integrated** until a verified indexed release is deployed and queried through a documented read-only API.


## Read-only indexed distribution and API handoff

A verified source bundle is not yet publicly deployed. The accepted 3,232-row county cut can be installed into an independently versioned, read-only SQLite database without rebuilding or changing source metrics:

```bash
python scripts/nri_county_index.py --release /secure/releases/nri-20261102 --index /secure/indexes/nri-dec2025.sqlite
python scripts/nri_county_index.py --index /secure/indexes/nri-dec2025.sqlite --lookup 01001
```

`nri_county_index.py` verifies the source manifest, official publisher identity, vintage, source and derived archive SHA-256, every original captured ArcGIS page and metadata SHA-256, and full published-to-normalized row reconciliation. It independently verifies SQLite integrity and indexed counts. The resulting 3,232 county records preserve 88 unknown scores as NULL—not zero. The index path is immutable: any attempt to overwrite it fails.

The existing optional read-only DuckDB warehouse API can mount this separate SQLite source index by setting `NRI_COUNTY_INDEX=/secure/indexes/nri-dec2025.sqlite` (or using `--nri-index`). If the source index is missing or invalid, startup fails closed; absence leaves the NRI routes unavailable without changing FMCSA endpoints.

Supported **source-context-only** HTTP GET/HEAD endpoints:

- `/v1/geography/nri/status`: accepted original-source index status, counts (known/unknown), SHA-256, source vintage and explicit no carrier/route attribution. HTTP 503 and `NOT_INSTALLED` when the index is not configured.
- `/v1/geography/nri/counties/01001`: a county by **exact five-digit STCOFIPS**, preserving NULL score values and original FEMA relative risk rating and expected annual loss estimate. 404 for an unrepresented county and 400 for invalid identifiers.
- `/healthz`: the existing FMCSA warehouse health plus whether an NRI source index is installed; this is **not** a live-source connectivity probe.

**Integration example**: an independently verified facility location must first be matched to a county through reviewed geocoding and boundary intersection. Only then may the county NRI context be displayed, explicitly labeled as regional community risk. No MCS-150 company headquarters or carrier ID is automatically joined; actual operating routes require separate independent trip/telematics evidence. No county NRI value is an insurance policy score, hazard occurrence probability for a truck, actuarial expected loss, or transport route risk. Do not use this to price, bind, decline, or infer owned terminals.

The source-index acceptance CI flow is now: official FEMA ArcGIS endpoint → original publisher page capture and before/after watermarks → ZIP-formatted derived source table → validated normalized county CSV → integrity-checked SQLite index → read-only API unit tests. The CI artifact includes all original source bytes, normalized CSV, manifest and built SQLite index, with no insurer or carrier-private data.
