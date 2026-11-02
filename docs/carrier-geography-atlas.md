# Carrier Geography Atlas — observational v1

Public route: `#/atlas` or `#/atlas?dot=3938496`.

The Atlas reuses the existing FMCSA **daily inspection** and **crash involvement** carrier evidence (source IDs `fx4q-ay7w` and `aayw-vxb3`) and the existing Census 2025 state polygons. It renders state-level observation clusters, layer toggles, state selection, loaded counts, browser retrieval timestamps (not publication time), and links back to inspection detail.

## Honest scope

- It is **not** a complete lifetime map. Public request sizes and source failures may truncate loaded evidence.
- State markers are **regional centroids for state-level grouping**, not event latitude/longitude or inferred trip routes.
- Crash involvement does not prove fault; inspection reporting-state fallbacks remain labelled.
- No GPS, mileage-based freight lanes, source-matched terminal geocodes, FEMA polygons, H3 cells, named weather events, PHMSA entity matches or actuarial risk surfaces are included in this version.
- A carrier office or DOT registration location **never** represents the actual operating route.
- The Atlas lists official FEMA NFHL, NRI v1.20, NOAA Storm Events, FHWA NBI, PHMSA incident sources as **not integrated** until fully validated.

## Validation

- `npm test` includes shareable USDOT route and injection rejection.
- Atlas-mode preview requests **only** FMCSA inspections and crash involvement slices. Other Carrier 360 data is not queried for the Atlas.
- `npm run typecheck && npm run build` checks new route.
- Test `#/atlas`, `#/atlas?dot=3938496`, `#/atlas?dot=3706`, invalid IDs, slow-source failures and narrow screens.
- Assert no zero/clean event inference from a failed or partial source.
- Capture and review fresh GitHub Pages screenshots after merge, verify deployed commit SHA and source attribution.

Further geospatial ingestion, MapLibre/H3, raster intersections and exact routes are tracked in Issue #57. Do not activate unvalidated hazard colors on this map.
