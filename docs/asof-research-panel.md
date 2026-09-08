# Acquisition-time carrier features

This offline pipeline establishes a current baseline and supports future month-end feature construction from preserved cuts. It does not reconstruct historical features from current downloads or fit a model. It has no production UI integration.

## Reproducible workflow

```sh
python scripts/cohort_snapshot.py --per-stratum 10
python scripts/build_asof_panel.py --cut warehouse/raw/REPORTED_CUT_ID --as-of ACTUAL_COMPLETION_TIMESTAMP --output warehouse/staging/UNIQUE_OUTPUT_ID
```

For later acquisitions, retain the original population:

```sh
python scripts/cohort_snapshot.py --cohort warehouse/raw/ORIGINAL_CUT_ID/cohort.json
```

For an elapsed month end, supply preserved cuts and the UTC month-end cutoff at `23:59:59Z`, plus `--month-end`. The builder chooses the most recent complete cut that was already available at that cutoff. It rejects future cutoffs, unavailable history, mixed cohorts, tampered artifacts and existing output directories. The original population must itself have been selected by the cutoff. A September acquisition cannot provide an August carrier-month, regardless of the dates inside its rows.

The pilot cohort selects the lowest USDOT identifiers within seven explicit active-Census strata: fleet bands A, B/C, D/E, F/G/H, V–Z, reported passenger cargo and reported hazmat. Overlap is deduplicated. Selection responses and metadata are retained. These strata correspond to 1, 2–6, 7–11, 12–19 and 1,000+ reported units, plus the two overlapping operation indicators. This is a convenience engineering sample with age, size and active-entity selection bias; it is not a representative population, peer group or model validation sample. No demo-carrier list or outcome filter selects the cohort.

## Source contract for these features

All sources are official DOT DataHub extracts scoped to the preserved USDOT list. Each query is ordered by Socrata row ID, paged without a browser cap, and checked against the selected row count before and after acquisition. Every response page and metadata artifact is hashed. Duplicated source IDs, out-of-cohort rows, count/schema/watermark changes, missing pages and malformed lineage fail verification. The ceiling is 100,000 rows per source for this pilot; exceeding it fails rather than yielding a partial feature cut.

| Source | Grain and key | Dates and history | Normalization and limitations |
|---|---|---|---|
| `az4n-8mr2` Census | Entity / `dot_number`; exactly one row required for exposure | Current daily snapshot; `mcs150_date` is a reporting date, not historical availability | Nonnegative reported units, drivers and VMT; current denominators are explicitly named. VMT is not earned/insured exposure. |
| `fx4q-ay7w` inspections | Inspection / `inspection_id`, joined by `dot_number` | `insp_date`; published rolling three years; current corrections | Nonnegative integer `oos_total`; unknown totals/dates make affected features unavailable. Duplicate inspection IDs reject construction. |
| `aayw-vxb3` crashes | Commercial-vehicle crash report / `crash_id`, joined by `dot_number` | `report_date`; current published file and corrections | Counts are vehicle reports, not unique crashes. Severe means fatality, injury or tow-away involvement; uncertainty is retained. No fault inference. |
| `m3ry-qcip`, `h3zn-uid9` | AB and C passenger SMS carrier outputs / `dot_number` | Monthly current output; 24-month measurement basis; acquired watermark retained | Each population remains separate. Numeric measures and public percentiles are retained without conversion or clipping. Missing/ambiguous rows remain unavailable. |
| `4y6x-dmck`, `h9zy-gjn8` | AB and C property SMS carrier outputs / `dot_number` | Monthly current output; acquisition does not reconstruct earlier releases | Measures remain separate from passenger outputs. Structurally unavailable public percentile fields stay null. No inferred property percentile. |

Metadata watermarks identify upstream updates, not exact row availability or measurement dates. The source observation time is when this system acquired the evidence. Before/after checks do not guarantee an upstream transaction: undetectable same-count changes can remain possible. Daily inspection publication can omit inactive entities and other excluded categories, so a later empty extract does not establish no future adverse event. Inspection totals/rates require active Census status; inactive, missing or ambiguous identity makes those features unavailable while retaining separately named known row counts.

Primary references: [FMCSA Open Data Program](https://www.fmcsa.dot.gov/registration/fmcsa-data-dissemination-program), and each source's stored official DataHub metadata. The FMCSA page documents rolling inspection coverage, population exclusions, and multiple commercial-vehicle reports within a crash.

## Feature semantics and coverage

Feature schema `CARRIER_ASOF_FEATURES_0_1` uses `(as_of_date - N days, as_of_date]` for 30/90/180/365-day event windows. Future-dated events are excluded and counted separately. Missing event dates make window totals unknown. Rates need an observed, nonzero denominator. Known severe reports remain recorded even when other reports have unresolved severity; an exact severe total stays null in that case.

One feature row points to one complete source cut. Source manifest, page hashes, acquisition times, cohort hash, feature hash and implementation hashes make the construction auditable. The manifest records per-feature coverage and SMS population availability over the full selected denominator. The four SMS tables are not pooled into a composite or selected with an arbitrary first-row rule.

Current power units in a rate are explicitly named as a current reported denominator. No historical fleet exposure is inferred. Census reporting age, VMT year, operation fields, sparse observations and applicable SMS population need further eligibility rules before modeling.

## Acceptance result and next gate

The September 8 pilot acquired 62 Census rows, 39,760 inspection rows, 30,409 crash-vehicle reports and 68 SMS rows across four populations: 70,299 total rows from seven sources. It produced 62 reproducible as-of observations. Nineteen carriers lacked an inspection denominator for the 365-day OOS rate and retained null rates.

The real-cut August 31 reconstruction attempt was rejected. No historical month-end observations or mature future labels were established. `oos_next_90d`, `crash_report_next_180d` and `severe_report_next_365d` are null with `FOLLOW_UP_NOT_ESTABLISHED`; they are placeholders, not manufactured negative examples. Reporting lag, corrected/deleted records, current-source exclusions, label surveillance and event definitions must pass a separate outcome ascertainment gate before any labels can train a model.

Therefore Phase 3 remains incomplete and Phases 4–8 remain blocked by temporal evidence. Do not calculate AUROC, calibration, risk deciles or forecast probabilities from this pilot. The frozen v0.1 research model is registered separately under `research/`; its formula has not changed or been released.

## Remaining insurance semantics

An official legacy dictionary defines `TERM/REPL` as replacement following a new submission. That definition is for the legacy cancellation-method field, not an explicit modern `FILING_STATUS_REASON` crosswalk. The modern MOTUS documentation also describes different schema and blank-string deletion behavior. No cross-schema code substitution is applied, and the maximum-amount unit discrepancy remains unresolved. See [legacy dictionary](https://data.transportation.gov/api/views/wahn-z3rq/files/6b2991b6-05c6-4745-a1d8-a1595f34b021?download=true). Modern filing rows are not used as training targets in this pipeline.
