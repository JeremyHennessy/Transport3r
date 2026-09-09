# Large-carrier driver and inspection counts

The September 9, 2026 UTC investigation confirmed that production already served the date-integrity release `ebd8ab62586df878ed2a4e91750a58710fb8dd8c`. The count issues were reproducible in that release, not evidence of an old deployment.

## Findings and repairs

1. Carrier navigation reused component state across USDOT numbers. After opening J.B. Hunt, a failed Census request for Swift left J.B. Hunt's identity, 24,116 drivers and 25,280 power units under Swift's USDOT route. The root router now keys carrier and fleet components by USDOT, resetting identity and evidence together. A failed new identity request cannot retain the previous carrier's counts. Tab changes within the same carrier retain the existing lazy-loading behavior.
2. Safety's inspection card showed a capped `500+` loaded window. It now queries the full available inspection-file count separately from the bounded recent rows, and shows both scopes. Summary and Fleet cards explicitly labeled as loaded rows continue to show the actual 500 loaded rows. Inspection-child counts remain partial when the parent set is partial, with their loaded-window scope visible; partial OOS counts retain a lower-bound marker.
3. The Company Census includes inactive and pending registrations, not just currently active carriers. Driver counts are preserved as reported, with their MCS-150 form date and registration status in the carrier header and Fleet view. The directory now identifies registration status beside each driver count; the detailed report date is also available in its tooltip. Records are not silently removed from search results.

Count queries run alongside row queries. Failed, missing, malformed, negative, fractional, unsafe-integer or contradictory counts cannot become a zero or override the loaded evidence. If the source count is unavailable, the existing bounded rows remain usable and their total is explicitly unavailable. An empty source query is labeled as no returned rows, not proof that no inspections occurred.

## Verified examples

| USDOT | Carrier | Census drivers | MCS-150 form date | Census status | Available inspection-file rows |
| --- | --- | ---: | --- | --- | ---: |
| 80806 | J B Hunt Transport Inc | 24,116 | 2025-07-07 | Active | 30,685 |
| 54283 | Swift Transportation Company of Arizona LLC | 12,883 | 2025-08-05 | Active | 33,439 |
| 264184 | Schneider National Carriers Inc | 11,335 | 2026-01-30 | Active | 22,490 |
| 265752 | FedEx Ground Package System Inc | 127,917 | 2024-12-30 | Inactive | 0 returned |

These are observations captured for the repair, not permanent expected values. `validate-large-carriers.mjs` exercises the actual application mapping and count query against these sources in CI and retains new results. The inactive FedEx record is intentionally included: a large reported fleet must not force a positive inspection count or an inference of current operations. Its SAFER response was titled `RECORD INACTIVE` during this investigation.

J.B. Hunt and Swift's driver counts also agreed with their official SAFER pages. SAFER showed 20,295 and 22,251 US inspections respectively for its stated 24-month periods; those are different scopes and source dates from the public inspection file's full available history. This repair does not claim the file count reproduces SAFER's 24-month totals. It does not introduce rates with mismatched denominators or change SMS weights/formulas.

## Source and validation boundaries

The [FMCSA Open Data Program](https://www.fmcsa.dot.gov/registration/fmcsa-data-dissemination-program) documents the Census's active/pending/inactive coverage and daily publication from a database approximately 24 hours old. A fresh file publication is not a new carrier MCS-150 report. Census registration status is not a determination of insurance coverage, operating authority or the status of an entire corporate group.

Tests cover full versus loaded counts, count-query failure/malformed values, lookahead contradictions, confirmed empty sources, real large-carrier Census mappings, inactive exposure context and the actual Safety/Summary renderers. Browser verification reproduces the cross-carrier identity failure before the repair and confirms the previous name/counts are absent afterward. Styling, navigation structure and card layout are unchanged; the visible additions explain the requested data fields. The unresolved prior visual checkpoint is not claimed as resolved. PR #17 remains separate.
