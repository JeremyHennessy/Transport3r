# FEMA National Risk Index county source acceptance (v1.20)

## Source and intended use

Official download: https://www.fema.gov/about/reports-and-data/openfema/nri/v120/NRI_Table_Counties.zip

Official FEMA technical documentation: https://www.fema.gov/sites/default/files/documents/fema_national-risk-index_technical-documentation.pdf

This module **downloads and verifies FEMA's National Risk Index v1.20 county-level tabular file at its native STCOFIPS grain**. It is a data-foundation task for Transport3r's future geography Atlas, not a carrier-scoring feature.

The source contains FEMA's **relative community risk ratings, scores, and expected annual loss** estimates. Those are not empirical insured transport losses or carrier-specific risk scores. No carrier location, depot, route, H3 cell, facility, policy, claim or identity is joined.

## Reproducible execution

```bash
python -m unittest discover -s scripts -p 'test_nri_county_ingest.py' -v
python scripts/nri_county_ingest.py --output outputs/nri-v120-$(date -u +%Y%m%dT%H%M%SZ)
```

For an independently saved, verified source archive:

```bash
python scripts/nri_county_ingest.py --archive /secure/official/NRI_Table_Counties.zip --output outputs/nri-replay-001
```

Never replace an existing release directory. Each output contains:

- `official.zip`: exact original archived source bytes; SHA-256 in `manifest.json`
- `counties.csv`: deterministic FIPS-sorted normalized county rows; SHA-256 in the same manifest
- `manifest.json`: source URL/final redirect, acquisition UTC timestamp, observed source fields, version, original and normalized hashes, downloaded/accepted/rejected/unknown-score counts, validation state and strict no-carrier-risk flags

The downloader refuses non-HTTPS redirects, archives larger than 85 MB, CSV decompression larger than 150 MB, wrong/duplicate CSV members, missing required source columns, duplicate or malformed five-digit FIPS codes, invalid source risk numeric values, unrecognized release versions, excessive rows, and less than 3,000 source rows in production mode. A rejected raw file remains as immutable evidence and the normalized release is **not** promoted.

The dedicated `.github/workflows/nri-county-source.yml` workflow executes offline contract tests and actual official-source acquisition, then uploads the raw source, normalized county file, and the provenance receipt as a GitHub Actions artifact. CI success is required before any source is marked validated; a connection probe alone is insufficient.

## Next step after successful source ingest

- Independently validate public county geometry/vintage and exact county FIPS crosswalk against a licensed geographic base.
- Query FEMA's county metrics **only** for independently verified terminal coordinates or confirmed route/stop geometries with stated spatial uncertainty.
- Preserve mapped/unmapped classification, uncertainty, source observation date, rating scale and source data vintage. Do not automatically treat a carrier's MCS-150 address as an operating route or hazard exposure.
- H3 overlay cells must distinguish directly sampled hazard data from estimated or decayed context; any distance-decay rule is a separately versioned *model*, never an official FEMA score.
- Do not derive probability of insurance loss, claim severity, renewal premium, or bind/decline outcomes until insured exposure and outcome validation exists.

**Current release boundary:** Source ingestion and QA only; the public GitHub Pages Atlas continues labeling this source **Not integrated** until a verified indexed release is deployed and queried through a documented read-only API.
