# Local or private-host installation — public-source evidence API

This is a **loopback-only installation reference**, not a secure public hosting certification. The FEMA county release is a public-source context product; private insurer policy records, claims and shipment locations must never enter the evidence API or GitHub Pages assets.

## Prerequisites

- Docker Compose v2, at least 4 GB RAM for the container, and ample fast disk space for a validated nationwide DuckDB warehouse (prior baseline ~7.4 GB).
- A complete, source-accepted FMCSA warehouse with embedded acceptance receipt and independently verified SHA-256. The corrected duplicate audit requires a **fresh complete source cut**; prior receipts must remain immutable.
- A validated FEMA December 2025 v1.20 county SQLite index installed using the source manifest and original ArcGIS response hashes.
- Mount read privileges for container UID 10001. All source files must be read-only to the app. This server may expose only **public** FMCSA/FEMA records.

## Start local source API

Set host environment variables to **absolute index file paths**:

```bash
export TRANSPORT3R_WAREHOUSE_PATH=/srv/transport3r/verified/warehouse.duckdb
export TRANSPORT3R_NRI_INDEX_PATH=/srv/transport3r/verified/nri-counties-dec2025.sqlite
docker compose -f deploy/evidence-api/compose.nri.example.yml config --quiet
docker compose -f deploy/evidence-api/compose.nri.example.yml up --build -d
```

The service binds only to localhost. It uses nonroot UID 10001, read-only mounts and filesystem, no new privileges, no extra capabilities and resource limits. It does not include DNS, public HTTPS, firewall, authentication or rate limiting.

## Confirm source coverage

```bash
curl --fail http://127.0.0.1:8787/healthz
curl --fail http://127.0.0.1:8787/v1/geography/nri/status
curl --fail http://127.0.0.1:8787/v1/geography/nri/counties/01001
curl --fail http://127.0.0.1:8787/v1/carriers/3706/evidence
```

Expected with correctly mounted sources: 36-source verified FMCSA warehouse health, FEMA county index status ACCEPTED_SOURCE_INDEX, 3,232 counties with 3,144 source scores and 88 null/insufficient data; exact five-digit FIPS lookup returns FEMA community relative risk without any carrier or actual route attribution.

**Do not configure a public browser to call a localhost URL.** A separate HTTPS reverse proxy or private access network must be configured and tested. The GitHub Pages build reads EVIDENCE_API_URL as a public source-service URL, not as a secret credential. Never expose private insurer portfolios on this endpoint.

## Refresh and rollback

1. Acquire a **new** immutable source cut, document URLs, dates, original identifiers, downloaded/accepted/rejected/indexed counts, version, SHA-256, and rejected reasons.
2. Validate real publisher records and full raw-to-index reconciliation. Source connectivity alone is not acceptance.
3. Install into a new filename. Validate FIPS lookup, null scores and known carrier fixture. **Do not overwrite a running database.**
4. Update mounts, restart, then test source status, sample Carrier 360 queries and geographic source endpoints. Record the live API container SHA and data release.
5. On failure, restore previous known-good read-only release and retain failed manifests; missing data must display UNKNOWN.

## Production requirements and risk boundaries

A deployment requires HTTPS, firewall, authentication/rate limiting as dictated by insurer audience, TLS renewal, OS/image patching, immutable source backup, encrypted disk, monitoring, query resource limits, and independently reviewed security. The read-only public source index must remain completely separate from the local private policy/claims workbench.

The FEMA county index is **not a carrier risk score**. To assess a facility or stop, independently verify real site coordinates, boundary/vintage, and a correct point-in-polygon match. To assess a traveled route, acquire verified GPS/trip geometry and documented time-varying exposure. Neither is established by carrier headquarters, county NRI relative score or FMCSA filings.
