# Power BI project review — September 9, 2026

## Scope and evidence

Reviewed both PBIP semantic models and report definitions plus all three PBIX files in `D:\Transport`. The inventory contains **140 table definitions (including generated date tables), 180 measure definitions, 97 relationships, 20 report pages and 170 visuals**. These are counts across files, not unique business concepts. Original Power BI assets were read only; no Desktop refresh, DAX execution, service publication or numerical reconciliation with Power BI was performed.

| Asset | Tables | Measures | Relationships (both directions / inactive) | Pages / visuals |
| --- | ---: | ---: | --- | --- |
| SMS Test PBIP | 12 | 0 | 11 (10 / 0) | 1 / 1 |
| Transport Risk Model PBIP | 55 | 78 | 53 (31 / 4) | 9 / 92 |
| SMS Test.pbix | 15 | 17 | 8 (8 / 2) | 1 / 2 |
| SMS Test v2.pbix | 15 | 22 | 8 (8 / 2) | 1 / 3 |
| Transport Inspections and Crashes 2.pbix | 43 | 63 | 17 (17 / 0) | 8 / 72 |

`scripts/review_powerbi.py` inventories TMDL objects, source IDs, relationships, page names, visual types and field references. For PBIX it uses the read-only [PBIXRay](https://github.com/Hugoberry/pbixray) parser, pinned for this run to 0.15.5, to extract schema, DAX, Power Query and storage metadata. Each PBIX SHA-256 was identical before and after extraction. No carrier tables were exported from the PBIX files. Full definitions stay in ignored local outputs rather than public repository history.

Local evidence: `outputs/powerbi-review-full/inventory.json`, the three adjacent `*.metadata.json` files, and `outputs/powerbi-warehouse-validation/validation.json`. Reproduce the review with `python scripts/review_powerbi.py D:\Transport outputs/new-powerbi-review --pbix` in a Python environment containing `pbixray==0.15.5`.

PBIX input hashes:

* SMS Test: `90f4d3495fae724ccd184a86f5a28b85604ce3aa1fb0df8a655a4a1620dcb520`
* SMS Test v2: `feb4322675c231eda6f02c9f5fccad677d9b5338ba1ff3775fb07535f50c8e0b`
* Transport Inspections and Crashes 2: `7741a25bdd4ef52308636e8ab2e978600b60b233a520dfb54cc7810c04690b5a`

## What each model contributes

**SMS Test PBIP** is a source exploration model: twelve OData tables, no explicit measures, and a violation-code table visual. It separates Census, inspection, violation and crash inputs; AB/C passenger and property outputs; and four INTER/INTRA extracts. Its raw numeric and date fields are largely imported as strings. Source definitions provide a useful mapping reference, not validated calculation results.

**SMS Test PBIX and v2** add typed inputs, six BASIC measure families, exposure/utilization calculations, event groups and percentile experiments. v2 has six percentile measures where the earlier file has one measure and several calculated percentile columns. Both have bidirectional violation → inspection → Census paths and inactive passenger extract relationships. Their score calculations are prototypes requiring the corrections below.

**Transport Risk Model PBIP** contains daily Census, inspections, inspection units, violations, citations, crashes, category/code lookups, geography and a shared date table. Most imported tables refer to Power Platform dataflow entities; the local files do not reveal those dataflows' full upstream transformations or refresh cuts. Its Company List, DOT Inspection Summary, DOT Crash Summary, VIN Crash Summary and crash-condition pages are useful navigation references. Four generic hidden/exploratory pages hold tables and a scatter plot. It also contains a separate experimental risk formula.

**Transport Inspections and Crashes 2 PBIX** uses a deduplicated DOT dimension spanning Census and an additional query, reads Parquet from a `jobs/latest` storage layout, and joins daily inspection children and monthly SMS inputs. The readable model contains inspection and SMS facts, **no crash fact table**, despite the filename. Its Inspection Summary and Report Summary each contain 23 visuals; other pages cover measure breakdowns, score distributions, shared-contact matching and violation code review. Its distinct DOT dimension and report/VIN drilldowns are useful patterns. A mutable `latest` path is not an immutable historical source cut.

## Findings that prevent direct formula reuse

1. **Double denominator in both SMS PBIX files.** `hos compliance basic measure`, for example, already divides a weighted violation sum by inspection time weight; `hos compliance basic normalized` divides that result by the same denominator again. The other normalized families follow this pattern. With a base numerator 20 and denominator 10, these definitions produce 2 and then 0.2. This is an algebraic check of the definitions, not a DAX execution result.
2. **Unusable denominators become zero scores.** SMS PBIX measures use `DIVIDE(..., ..., 0)`. The Transport Risk Model normalized columns use error-to-zero log transforms and an explicit zero fallback for nonpositive components. A missing component cannot be interpreted as low risk. Neither prototype supplies outcome calibration supporting its weighted aggregate.
3. **Different unvalidated risk formulas.** Transport Risk Model uses component weights 2, 1.75, 1.75, 1.25, 1.25, 1 divided by 9 and a further rescaling. The inspection PBIX uses 0.30, 0.15, 0.10, 0.20, 0.20, 0.05 and log/rescaling operations. These are not interchangeable versions of an established insurance score. They are not adopted into TRI.
4. **Severity logic needs inspection-grain replay.** SMS PBIX base measures sum `severity_weight * time_weight` while separate adjusted OOS columns exist but are not referenced by those measures. Transport Risk Model groups severity/OOS combinations and then rolls up by inspection date; multiple inspections on the same day must not collapse into one scoring group. The inspection PBIX uses `tot_severity_weight * Time_Weight + OOS_Weight` for some families and omits the final addition in others. Resolve the upstream definition of `tot_severity_weight` before deciding whether OOS is missing or double-counted. Use the application's versioned, tested replay rather than copying these formulas.
5. **Recency changes with refresh time.** Transport Risk Model's inspection and crash `TimeWeight` columns use `TODAY()` and `DATEDIFF(..., MONTH)` with no explicit future-event exclusion. A future event can enter the youngest bucket. Those columns cannot reconstruct a selected historical as-of date.
6. **Date filters are inconsistent.** Transport Risk Model's shared inspection/crash date relationships are inactive. Its base count measures activate them, while several inspection denominators and OOS measures do not. In the inspection PBIX, `Inspection Violations (SMS)` activates the *daily inspection* date relationship; there is no direct shared-date relationship to SMS inspections in its extracted relationship graph. Numerical effects require an actual filtered DAX run.
7. **Filter backflow can change exposure and denominators.** Both SMS PBIX models use bidirectional violation → inspection → Census relationships. The inspection PBIX uses bidirectional filtering on all 17 relationships. Validate carrier, geography, date and violation slicers separately so a violation selection cannot silently redefine the eligible inspection denominator or reported fleet population.
8. **Different measures use different grains.** Transport Risk Model's `Inspection Violations` distinct-counts violation IDs. The inspection PBIX's same-named measure distinct-counts *inspection IDs in the violation table*. The latter measures inspections with violations, not violation rows. Driver inspections, reported drivers and violation rows must retain separate names and counts.
9. **Exposure source and age are hidden by fallback.** The inspection PBIX's Drivers, PUs and VMT measures prefer SMS Census, falling back to daily Census when blank, without displaying the selected source cut. `AVERAGE(nbr_power_unit)` over a current Census table is not a historical average fleet. Keep current reported exposure, report date, mileage year and source explicit.
10. **Population ambiguity is concealed by MAX.** The inspection PBIX appends AB/C property outputs into `sms_combined`, then uses MAX for official measure selection. The query does not add an explicit AB/C source discriminator. Multiple conflicting rows must remain an ambiguity, not silently select the maximum.
11. **Percentile experiments are not official validation.** SMS files differ in dense-rank versus midpoint-rank logic, insufficient-group handling and calculated-column versus measure context. The unsafe-driving grouping shown in both uses only combination-carrier group labels. Peers, segment eligibility, population source and monthly cut must be reconciled before reuse.
12. **Hazmat and presentation checks remain.** `Inspections - Hazmat` includes both Y and N placard-required values. Confirm the intended denominator before labeling it a hazmat inspection metric. The PBIP retains “All Manufacturers” and report query references such as `Measures (2)` and `Selected manufacturer`; some PBIX query references also have old spellings. These are review leads, not proof of broken rendered bindings, since query-reference labels can be stale while actual semantic expressions remain valid.
13. **Shared contact information is a lead, not misconduct.** The inspection PBIX's “Chameleon” columns flag repeated email, phone, address, DUNS and officer text. These can reflect legitimate relationships or shared service providers. Any future UI should say “shared registration details,” show the exact matching evidence, and avoid asserting evasion, common ownership or fraud.

## Source mapping disposition

| Power BI input family | Existing application source | Disposition |
| --- | --- | --- |
| Company Census | `az4n-8mr2` | Existing explicit reported exposure; dataflow transformation equivalence unverified |
| Daily inspections / crash reports | `fx4q-ay7w` / `aayw-vxb3` | Keep different event grains and file windows |
| Inspection units / violations / citations | `wt8s-2hbx` / `876r-jsdb` / `qbt8-7vic` | Join through verified inspection parent IDs; complete child acquisition is implemented in v2/v3 with parent and source-count validation |
| SMS Census / inspections / violations / crashes | `kjg3-diqy` / `rbkj-cgst` / `8mt8-2mdr` / `4wxs-vbns` | Already present in 14-source preserved cuts |
| AB/C property and passenger | `4y6x-dmck`, `h9zy-gjn8`, `m3ry-qcip`, `h3zn-uid9` | Retain source/population identity; no MAX-based resolution |
| Additional INTER/INTRA extracts | `hg4d-8cim`, `isy5-3gj3`, `n6n3-vpjj`, `dri9-7c4y` | Found in models; not added to the 36-source live contract without separate necessity/schema validation |
| Code/weight/geography lookups | Dataflow entities, embedded tables, PDF or storage-derived lookups | Retain source/version and unknown codes; not presumed current official mappings |

## Implemented follow-up

`scripts/inspection_evidence_audit.py` now audits a **verified complete cut** before warehouse promotion validation succeeds. It enforces unique daily/SMS parent identities, rejects duplicate raw identities and carrier contamination, checks every SMS violation against its parent USDOT and event date, and separates violation rows from distinct inspections with violations. Missing dates make window totals unavailable while preserving known counts. Explicit inclusive window boundaries and zero-observed months are exported; sparse months do not become acquisition failures. It never equates daily inspection IDs with SMS unique IDs.

The existing CI warehouse acquisition gate now retains `inspection-audit.json` and fails if its parent/date integrity is incomplete. This change is an offline pipeline gate, not a new browser data service or a numeric risk release.

The retained 62-carrier cut `20260909T111631601998Z-1a4c0efd` passes: 39,760 daily inspection parents, 27,179 SMS parents, 10,048 of 10,048 violations matched, zero join/date issues. The complete warehouse validation still reconciles 109,466 rows and 868 carrier/source counts. For the illustrative **730-day** September 10, 2024–September 9, 2026 window:

| USDOT | Daily rows, whole file / window | SMS rows, whole file / window | SMS violation rows / distinct parents in window |
| --- | --- | --- | --- |
| 3706 | 26,709 / 18,413 | 18,468 / 17,434 | 6,100 / 4,245 |
| 5373 | 970 / 663 | 647 / 622 | 319 / 201 |
| 119 | 2 / 0 | 1 / 0 | 0 / 0 |

For USDOT 3706, daily events extend to September 6, 2026, while SMS inspections extend to July 30, 2026. The different observed ranges help explain count differences; they do not certify a common monthly release or fully explain every unmatched record. USDOT 119's retained inspections precede the selected window, so zero observed rows in that window is not no history.

## Next implementation order

1. Completed: v2/v3 retains daily inspection units, violations, citations and studies through preserved parent IDs, with source-update checks and orphan rejection.
2. Completed: inspection/VIN routes, daily windows, monthly visuals, state maps and report exports. Browser evidence remains bounded and separate from the offline warehouse.
3. Establish exact SMS release alignment and exposure eligibility before comparing Power BI-exported measures or admitting new model features. Reuse `compare-measure-snapshots.mjs` only for identical source cut, grain, filters and event windows.
4. If editing the Power BI models next, make versioned copies, fix denominator/date/null semantics first, and execute matched-cut DAX fixtures before replacing originals. No model score or percentile is released by this review.

## Matched-cut numerical acceptance remains blocked

The preserved PBIX metadata and Power Query definitions do not expose an immutable source artifact equal to the new acquisition. No DAX result for that same cut has been executed. An identical date slicer is insufficient. Do not call definition review or a self-comparison numerical reconciliation. The existing comparison harness requires exact USDOT, source ID/cut, window boundaries, date field, grain and filters; unavailable and mismatched values remain separate. Required next evidence: an immutable matching Power BI refresh and executed DAX exports for inspection/violation/OOS counts and denominators, reported exposure and applicable SMS populations. Originals remain untouched.
