# NOAA annual Storm Events public-source API and installation handoff

This module serves published source information only. It is **not** a carrier's actual storm exposure, a route hazard intersection, the complete footprint of an event, an insurance claim, or a score.

## Acceptance

An optional `NOAA_STORM_INDEX` absolute path mounts the immutable `events.sqlite` created from official NOAA NCEI 2025 details, locations and fatalities. On startup the read-only API verifies its embedded source receipt, NOAA identity, year, official original file URLs and SHA-256 provenance, stable source revision, accepted raw/indexed row counts, orphan accounting and SQLite integrity. Unverified explicit archives cannot be served.

If the index is missing, NOAA endpoints return HTTP 503 and `NOT_INSTALLED`; if an index is invalid, startup rejects it. Existing FMCSA Carrier 360 and FEMA county APIs continue independently when NOAA is not configured.

## Endpoints (all public-source-only GET / HEAD)

| Endpoint | Meaning |
|---|---|
| `/v1/geography/noaa/status` | Source-year, file SHA-256, accepted table counts, unmatched event links, publication stability, no-carrier-attribution flag |
| `/v1/geography/noaa/events/1012345` | Exact NCEI EVENT_ID, event type/time/state and up to 100 published location points; source fatality count only, no individual fatality details |
| `/v1/geography/noaa/locations?state=TEXAS&limit=200&offset=0` | Bounded paginated **publisher-reported points** for events linked to the specified exact uppercase source-state label. Limit 1–500. Response provides total rows, returned rows and partial/page state. |
| `/healthz` | Existing nationwide FMCSA warehouse health plus whether a NOAA Storm Events source index is installed |

The source is not a carrier ID index and does not accept a USDOT query. `No points` in one state/period **does not** mean no storms occurred; source reporting, filing coverage and point locations may be incomplete.

## Local source deployment (not a live public host)

The optional private-host reference `deploy/evidence-api/compose.public-sources.example.yml` mounts verified FMCSA, FEMA and NOAA source database files read-only and exposes the service to **localhost only**:

```bash
export TRANSPORT3R_WAREHOUSE_PATH=/srv/transport3r/verified/warehouse.duckdb
export TRANSPORT3R_NRI_INDEX_PATH=/srv/transport3r/verified/nri-counties-dec2025.sqlite
export TRANSPORT3R_NOAA_INDEX_PATH=/srv/transport3r/verified/noaa-storm-2025.sqlite
docker compose -f deploy/evidence-api/compose.public-sources.example.yml config --quiet
docker compose -f deploy/evidence-api/compose.public-sources.example.yml up --build -d

curl --fail http://127.0.0.1:8787/v1/geography/noaa/status
curl --fail 'http://127.0.0.1:8787/v1/geography/noaa/locations?state=TEXAS&limit=20'
```

Do not set the public GitHub Pages `EVIDENCE_API_URL` to a local address. A production installation requires a TLS reverse proxy, firewall, rate limiting, hosting location/availability, security review, backup, source refresh/version schedule, resource profiling and verified deployed commit/data SHA. This reference hosts **public datasets only**, never local insurer policies or claims.

## Validation and constraints

Dedicated NOAA source CI runs synthetic source acceptance plus public API HTTP tests using a simulated fixture, followed by actual official-source acquisition and source-to-index reconciliation. The fixture must never be represented as an official data cut; origin verification is mandatory at runtime.

Before rendering NOAA event points in a carrier geographic Atlas:

- Verify the independently acquired operating terminal coordinates or actual driven routes, not the registration address.
- Document reported point accuracy, event time/window, category and uncertainty. A location is not a floodplain, wind corridor or full event footprint.
- Define explicitly whether a mapped overlay is just **regional context**, not an observed shipment exposure.
- Combine hazard layers only after time/spatial alignment and model validation; do not equate NOAA source damage reports with insurance claims or liability.

The full plan to integrate NOAA maps with MapLibre/H3 remains in [Issue #57](https://github.com/JeremyHennessy/Transport3r/issues/57). The current public Atlas deliberately labels NOAA source overlays unavailable until this read-only API is actually hosted and verified.
