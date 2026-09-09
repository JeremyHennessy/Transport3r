# Coverage and carrier reconciliation

## Presentation scope

The user authorized the September 9 review follow-up: implement reconciliation and coverage indicators. The unresolved historical visual reference `25157fb` is not treated as approval for a redesign. This change replaces the Evidence tab's count-only source grid with an accessible, filterable coverage table and adds the same report, collapsed, to existing carrier tabs. Carrier identity, metrics, typography, navigation and scoring remain otherwise unchanged. Existing styles are retained; new CSS is scoped to this report.

## Coverage contract

`src/evidenceCoverage.ts` is shared by UI, JSON export and the live reconciliation report. Every requested source appears, including failures. Status precedence is unavailable, partial, empty, then request complete. No rows returned is not no historical activity. A child total remains scoped to loaded inspection IDs or linked dockets. An empty parent list issues no child request and has no invented acquisition time.

The report separates source acquisition time, saved catalog row-update time, catalog capture time, Census MCS-150 report date, and loaded event ranges. Cached slices retain their original acquisition timestamps. Saved catalog dates are explicitly not current freshness checks. Unmapped event-date semantics remain unavailable; no arbitrary change date is substituted. Date ranges disclose missing, invalid and conflicting fields; sparse valid dates alone are not a completeness failure.

The UI offers coverage filters and exports all requests in the tab as JSON, independent of the selected filter. It exports exposure context and null risk availability, not event records or an implied complete carrier history. Summary is collapsed by default; Evidence is expanded. The table scrolls within its container on small screens.

## Reproducible audit

Run `node scripts/reconcile-carrier-cohort.mjs outputs/reconciliation` from the repository. The audit selects ten low and ten high USDOTs from each of five overlapping strata: large active fleets, inactive registrations, passenger operations, small active fleets and intrastate operations. It adds the six retained carrier regression examples. This deliberately covers older and newer registrations; it is not a random population estimate.

All unique carriers receive Census mapping checks. Two carriers per selection plus the fixed regression examples receive bounded daily inspection, crash, SMS inspection and SMS Census queries with separate source totals. The audit checks carrier identity, inspection keys, mapping and count/window consistency. Raw returned rows, selection URLs and retry outcomes are retained in `observations.json`; its SHA-256 and before/after source metadata are recorded in `summary.json`. Changing metadata, acquisition errors or data discrepancies fail the gate. Metadata stability does not prove a transactional or historical monthly snapshot. CI retains both files as artifacts rather than publishing raw carrier records in Git history.

September 9 local run: 97 unique Census carriers and 25 detailed carriers; zero acquisition failures or checked mapping/count discrepancies. Five source metadata records were stable around the run. The observations hash was `302f250988d070b2d6c9be505cf53f8235842f07fbe2d369518e9d1928c60b72`. This is a sampled engineering result, not certification of every record.

Examples from the retained run: USDOT 80806 had 30,685 daily inspection records versus 20,173 SMS inspection records; USDOT 54283 had 33,439 versus 22,361. Their scopes and cuts differ, so these counts are not forced equal. USDOT 2855794 returned no current daily/SMS inspection rows and retained its inactive registration and 2016 exposure report.

## Power BI reconciliation boundary

The local `D:\Transport` PBIP definitions were inspected, but their imported Power Platform dataflows were not refreshed or executed. Power BI numerical comparison remains NOT_EXECUTED. No Power BI result is labeled a match based on code inspection.

Specific measure-review items in Transport Risk Model:

* `Vehicle Inspection File.TimeWeight` uses `TODAY()` and month boundaries rather than a pinned source cutoff. Replaying a selected historical period requires an explicit as-of date and exclusion of future events.
* The `_date_table` relationship to inspections is inactive. `Inspections` activates it with `USERELATIONSHIP`; `Vehicle Maintenance Inspections` does not. Verify date-slicer behavior in both numerator and denominator before altering relationships.
* `VMT per Average PU` divides Census mileage by Census power units without a historical average in the measure. It must not be called an official average exposure denominator without that calculation and matching source period.
* Bidirectional inspection/violation-to-Census paths and COUNT versus DISTINCTCOUNT need a row-grain and filter-context check. These are review risks, not measured refresh failures.

`scripts/compare-measure-snapshots.mjs` supplies the comparison gate for actual exports. Each JSON input must contain nonempty, identical `dotNumber`, `sourceId`, `sourceCut` (a verified snapshot identity), `windowStart`, `windowEnd`, `dateField`, `grain`, and `filters`, plus a `measures` object of numeric values or null. Use explicit `ALL_AVAILABLE` window labels only for full source-history comparisons, never for bounded browser rows. Preserve nulls. The gate reports NOT_COMPARABLE for different/missing context, INCOMPLETE for unavailable measures, MISMATCH for numeric differences, or MATCH. It does not infer source lineage from a PBIX filename or refresh time.

## Validation

Unit regressions cover coverage states, dependent scope, date conflicts, cached timestamp lineage, missing exposure and comparison eligibility. Production-bundle Chrome checks cover all-source rendering, caps/date ranges, status filters, exported content and Summary default state. Existing recovery, source UI, all-source mappings, large-carrier and SMS gates remain in CI. PR 17 stays frozen; no numeric risk or forecast is released.
