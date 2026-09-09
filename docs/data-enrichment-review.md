# Data review and enrichment — September 9, 2026

## Released behavior

The Safety tab includes an explicit daily event-window explorer. Users apply inclusive start/end calendar dates (up to three years). Each official daily source receives the same carrier/date predicate for detail and count requests. Daily inspections use `fx4q-ay7w.insp_date`; daily crashes use `aayw-vxb3.report_date`. Both registered fields contain YYYYMMDD text. Boundaries are validated before query construction; returned rows must have a valid date in scope and the matching USDOT. The existing recent Safety evidence retains its original scope.

Each source is checked for stable `rowsUpdatedAt` and `viewLastModified` metadata around acquisition. Missing metadata, changed publications or failed requests leave that source unavailable independently. Reapplying refetches; stale responses cannot replace a newer window. A separately queried count is a source-window total, while detail is bounded at 500 rows. Monthly loaded counts are lower bounds when detail is truncated, including zero-loaded months. Partial first/last months follow the user dates. Counts and metadata are not a transactional database snapshot, lifetime history, SAFER totals, or proof that missing/invalid source dates belong to the selected window.

VIN pages with a verified parent inspection now offer an on-demand [NHTSA vPIC](https://vpic.nhtsa.dot.gov/api/) lookup. Only the normalized observed VIN is transmitted. Responses require one matching VIN and an explicit decoder status; ambiguous/missing/foreign results fail. The app displays make, model, model year, manufacturer, vehicle/body type, GVWR class, primary fuel and manufacturing country when supplied. Missing fields stay absent. Nonzero decoder codes and original warning text remain visible alongside provisional specifications. New requests clear prior results; errors can be retried. There is no automatic bulk VIN acquisition.

The manufacturer-supplied specifications are separate from original FMCSA observations. They establish neither ownership nor current condition, insurance, recall applicability, or unrepaired status. Model year is returned by NHTSA without substituting inspection year. The API documents automated rate controls and optional model-year hints; no year hint is sent because this workflow has no independently verified model year.

## Source-date findings

- The verified daily date fields are YYYYMMDD text. A live SMS inspection sample uses `30-AUG-24`. Applying daily lexical date bounds to SMS would be incorrect; the query helper rejects that use.
- [FMCSA explains](https://ai.fmcsa.dot.gov/SMS/HelpCenter/Index.aspx) that SMS uses a monthly MCMIS snapshot and a snapshot-relative event window. The oldest/newest loaded event dates, saved catalog date and source-row update timestamp are not interchangeable with that snapshot date.
- Census report dates and mileage years describe separate exposure declarations. Selecting a daily event window does not establish contemporaneous exposure or authorize a score denominator.
- Exact SMS release alignment remains unverified. This release adds explicit daily-window querying and date-scope clarity; it does not certify a common SMS month or historical training panel.

## Additional source assessment

| Priority / source | Useful enrichment | Join and temporal requirements | Current disposition |
| --- | --- | --- | --- |
| 1 — [NHTSA vPIC](https://vpic.nhtsa.dot.gov/api/) | Vehicle specification and VIN-quality context | Full observed VIN linked through a verified inspection; decode status and retrieval time retained | Integrated on demand; public-origin CORS and real VIN examples tested |
| 2 — [PHMSA hazmat registration](https://www.phmsa.dot.gov/registration/registration-information) | Registration history and covered periods | Validate downloadable schema and exact USDOT/HM-company crosswalk; keep covered years separate from issue date | Candidate. Official landing page reviewed; its linked registration download portal returned 404 during review. No records imported or assumed matched |
| 3 — [NHTSA recall campaigns](https://www.nhtsa.gov/nhtsa-datasets-and-apis) | Manufacturer/model-year campaign context | Reconcile decoded make/model/year with recall taxonomy; keep campaign identifier and publication dates | Candidate. Documented API queries make/model/year, not VIN repair completion. Do not label campaigns as open recalls on a carrier |
| 4 — [PHMSA hazmat incidents](https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics) | Commodity, release, location and reported consequences | Resolve carrier identity separately from reporter; deduplicate incident IDs while retaining multiple detail rows and revisions | Candidate. Official Form 5800.1 reporting/search documentation reviewed; no carrier join validated |
| 5 — [EPA SmartWay](https://www.epa.gov/smartway/smartway-partner-list) | Voluntary participation and divisional-fleet sustainability context | Validate company/division identity and data year; preserve voluntary-program coverage | Candidate. Public program list reviewed; name similarity alone must not attach participation or performance to a USDOT |
| 6 — [BTS NTAD](https://www.bts.gov/ntad) | Freight networks, terminals and infrastructure maps | Geographic overlay with layer date/metadata; use actual event/route locations when available | Candidate. Carrier registration address alone is insufficient for route or operating-exposure inference |

The Data Sources page lists all six with explicit integrated/candidate statuses, separately from the unchanged 36-source FMCSA contract. No candidate feeds a risk model. Data source additions do not bypass remaining MOTUS/docket acquisition, exact SMS releases, historical exposure eligibility, or future-outcome validation.

## Verification

The source-window CI audit now also uses bounded transient retries for its raw metadata and cohort-selection requests. Attempt URLs/statuses are retained in `acquisition-attempts.json`. Transport errors, timeouts, HTTP 429 and 5xx may retry up to three times; invalid payloads, permanent HTTP failures and publication changes still fail. The repair followed an observed CI `fetch failed` error before reconciliation began.

Eight new unit tests cover calendar boundaries and injection, shared detail/count predicates, rejected SMS date encoding, foreign/invalid rows, partial monthly zeros, changed publication metadata, decoder warnings, response identity and request provenance. Eleven production-bundle browser checks cover user interaction, old-response isolation, refetch/recovery, source changes and candidate/integrated labels. Real-source examples and screenshots are retained under `outputs/date-enrichment-local-ui/` and, after deployment, `outputs/date-enrichment-live-ui/`.

Live-source browser checks for the inclusive 2024 calendar year returned 8,658 inspections and 374 crashes for USDOT 3706 (500 inspection details loaded), two inspections and no crash rows for USDOT 3938496, and no rows in either daily file for USDOT 2855794. These are current-source results within the selected dates, not historical snapshot values or safety clearance. VIN `3C63RRGLXPG628183` decoded as a 2023 RAM 3500 with no reported decoder error; recorded VIN `3AKJHHDR1NCMS1700` returned Freightliner Cascadia fields alongside an explicit check-digit warning. Desktop and mobile checks passed without runtime errors.

## Continued assessment and integrated geography

[Census 2025 state boundaries](https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_state_20m.zip) now supply 52 bundled state/DC/PR polygons with a ZIP hash and reproducible converter. Exact event-state abbreviations determine the regional display. US-government geography is attributed; there is no geocoding or inferred route. It is a UI geography registry, separate from FMCSA facts and model features.

| Source | Grain / identity / time | Acquisition and use limits | Disposition |
| --- | --- | --- | --- |
| [PHMSA registration](https://www.phmsa.dot.gov/registration/registration-information) | Company registration and covered annual period; official search supports USDOT/MC/HM ID | Company history search requires portal login. The public data-file link did not expose an accessible dataset in this review; bulk schema, publication hash and redistribution terms remain unverified | Warehouse candidate after exact artifact/key validation; no inferred compliance or model use |
| [PHMSA incidents](https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics) | Form 5800.1 report/detail/revision; reporter may differ from carrier; event/report/availability dates separate | Official query tool exists. Bulk schema, revision keys, cadence and redistribution terms require artifact review | Consequence context candidate; no carrier attachment until identity/grain validated |
| [EPA SmartWay rankings](https://www.epa.gov/smartway/smartway-carrier-performance-ranking) | Annual voluntary divisional-fleet submissions and five performance ranges; data year differs from reporting year | Public spreadsheets; preserve attribution and endorsement limits. Company/division names are insufficient USDOT joins; file rights/crosswalk need validation | Optional sustainability warehouse context after exact mapping; not a safety/loss feature |
| [BTS NTAD](https://www.bts.gov/ntad) | Network/facility layers with per-layer dates and IDs | Public catalog; inspect each layer's metadata, refresh and use terms before bundling | Future geographic context. State-only events do not establish roadway exposure |
| [NHTSA campaigns](https://www.nhtsa.gov/nhtsa-datasets-and-apis) | Campaign/product, daily publication; exact make/model/year taxonomy required | Official API/dictionaries reviewed; model match does not establish affected VIN or repair status | Defer until taxonomy validated. Context warehouse possible; no risk-score contribution |

Seven external geography/specification/candidate entries now appear separately from the 36 FMCSA sources. Source evaluation does not mean every candidate was ingested or cleared for every use. No candidate feeds a production model.
