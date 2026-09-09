# Verified local evidence warehouse

## Purpose and scope

The local pipeline now supports complete cohort-scoped extracts from 14 official sources, followed by verified SQLite promotion and complete carrier exports. This extends the existing seven-source acquisition and preserves its original cohort rather than selecting a new model population. It does not add a nationwide database, connect GitHub Pages to a local disk, remove browser query limits, release a risk score, or establish historical/monthly source alignment.

The browser continues to use its live bounded queries and coverage reports. Local analysts can use the warehouse for complete source records within the preserved cohort, including records beyond the browser's limits. Raw snapshots and SQLite files are ignored by Git. CI retains its small engineering-cohort acquisition and verification artifacts.

## Source profiles

The existing `baseline` profile remains a readable/writable v3 cut containing Census, daily inspections, daily crash reports and four SMS output populations. The explicit `underwriting_evidence_v1` profile is v4 and requires all 14 sources:

| Family | Sources | USDOT field | Interpretation |
|---|---|---|---|
| Census | `az4n-8mr2` | `dot_number` | Current reported entity/exposure; MCS-150 date is not historical availability. |
| Daily safety | `fx4q-ay7w`, `aayw-vxb3` | `dot_number` | Full available cohort inspection and commercial-vehicle crash-report records. Source population and publication limits remain. |
| SMS outputs | `m3ry-qcip`, `h3zn-uid9`, `4y6x-dmck`, `h9zy-gjn8` | `dot_number` | Four separately retained public populations; no inferred percentile. |
| SMS inputs | `kjg3-diqy`, `rbkj-cgst`, `8mt8-2mdr`, `4wxs-vbns` | `dot_number` | Census, inspections, violations, crash reports. Acquisition completeness is not validated monthly alignment or model eligibility. |
| Current MOTUS evidence | `inys-ebih`, `c5y8-a4uz` | `usdot_number` | Current carrier authority and active/pending filing records. Raw amounts/codes remain unchanged; filings do not establish complete policy coverage. |
| New Entrant orders | `p2mt-9ige` | `dot_number` | Order/rescission evidence retained without inferring current registration or fault. |

Every raw source field is retained in JSON. Socrata `:id` is stored as `source_row_id`, separate from business event IDs. SMS violation `unique_id` is a parent inspection join and is not treated as a unique violation key. Daily inspection children, remaining MOTUS history/deltas and legacy docket-based sources are outside this profile; their full ingestion requires a subsequent join-aware profile.

## Acquire, verify, promote and export

From the repository root, use Python 3.12 or newer (SQLite is in the standard library):

```sh
python scripts/cohort_snapshot.py --profile underwriting_evidence_v1 --cohort warehouse/raw/ORIGINAL_CUT/cohort.json
python scripts/verify_snapshot.py warehouse/raw/NEW_CUT
python scripts/evidence_warehouse.py promote warehouse/raw/NEW_CUT
python scripts/evidence_warehouse.py verify
python scripts/evidence_warehouse.py inspect --dot 3706 --profile underwriting_evidence_v1
python scripts/evidence_warehouse.py export --dot 3706 --profile underwriting_evidence_v1 --output UNIQUE_carrier_3706.json
```

Use the exact cut ID printed by acquisition. For an initial engineering cohort, omit `--cohort` and use `--per-stratum 1` through `20`. New runs should reuse the preserved cohort to keep the selected denominator fixed. The default ceiling is 100,000 rows per source; an explicit `--max-rows` can raise the fail-closed ceiling up to 1,000,000. This ceiling never produces a truncated successful cut. Existing files/cuts/exports are not overwritten.

The default database is `warehouse/curated/evidence.sqlite`. A global `--db PATH` before the subcommand selects another warehouse. The tables are `cuts`, `members`, `sources` and `records`; records retain the full JSON payload and indexed USDOT/source/cut identity. Views and business measures are not manufactured from fields with unresolved semantics.

`inspect` returns counts and lineage without raw event payloads; `export` writes every retained row for the carrier's selected source profile. Neither is a zero-history or clearance statement. Use `--as-of TIME_WITH_TIMEZONE` to choose the latest complete cut already acquired by that time. Unknown cohort members, future observations and times before a qualifying acquisition fail rather than returning zero. A profile filter prevents silently substituting a seven-source baseline for the expanded profile. No records from different cuts are mixed into one export.

## Integrity and temporal boundaries

* Acquisition pages, lineage and cohort files are hashed; row IDs, carrier joins, query scope, row totals, metadata stability and availability timestamps are verified before promotion.
* All sources in a cut must complete. Partial/error cuts cannot enter the warehouse. Transfer ceilings fail rather than discarding excess rows.
* A SQLite transaction inserts the cut, members, sources and every record together. Interrupted imports roll back. Re-promoting identical verified bytes checks the stored copy and returns ALREADY_PRESENT; conflicting cut IDs fail.
* Read-only queries verify stored manifest/cohort/lineage hashes, complete source sets, row counts, payload hashes and denormalized identity indexes. SQLite integrity and foreign-key checks are available through `verify`.
* The original raw cut remains the source of record. Writer behavior is append-only, but SQLite and filesystem files are not WORM storage or protection against privileged edits. Preserve manifests separately for stronger custody controls.
* Each source has its own publication watermark. A complete cohort cut is conservatively available only after its last source completes. Stable metadata around acquisition cannot guarantee an upstream transaction or matching SMS measurement months.

## September 9 acceptance evidence

The preserved September 8 cohort has 62 carriers and cohort SHA-256 `7821dbea2a4a806d2d8af22c04d388f30ca43ad1aa3d87bca1cec7d1064075c8`. Expanded cut `20260909T111631601998Z-1a4c0efd` completed at `2026-09-09T11:18:46.600442Z`; manifest SHA-256 is `ddaec8318888a7fc20c646b9d7a22d59a500cbe2e0fd0cd355919be78d95b2f1`.

It contains 109,466 rows: 62 Census, 39,760 daily inspections, 30,409 daily crash reports, 68 SMS outputs, 62 SMS Census, 27,179 SMS inspections, 10,048 SMS violations, 1,835 SMS crash reports, 14 MOTUS carrier, 28 MOTUS insurance and one New Entrant order row. These counts describe the retained cut, not current nationwide totals.

All 868 carrier/source count comparisons passed. An actual complete export for USDOT 3706 contained 26,709 daily inspection records. The original seven-source cut was also retained in the local database. As-of lookup can select it before the expanded cut became available; it cannot backdate the new sources.

The unchanged feature schema produced 62 as-of observations using its original seven sources from the expanded cut. Nineteen 365-day OOS rates remained null for unavailable denominators. Additional SMS/filing records are retained evidence, not new scoring features or outcome labels. Forecast status remains BLOCKED_NO_MATURE_LABELS.

## Automated release gate

The default live gate now acquires the 18-source `underwriting_evidence_v2` profile (schema v5), including all four daily inspection child families through verified parents. Existing v1 cut validation remains supported. See [inspection children and drilldowns](inspection-drilldowns.md) for the acquisition contract and September 9 acceptance evidence.

```sh
python scripts/validate_evidence_warehouse.py --output UNIQUE_VALIDATION_DIRECTORY --per-stratum 1
python scripts/validate_evidence_warehouse.py --cut warehouse/raw/EXISTING_EXTENDED_CUT --output ANOTHER_UNIQUE_DIRECTORY
```

The gate acquires or verifies an extended cut, promotes it twice, verifies the stored warehouse, reconciles all carrier/source counts and checks a complete export for the carrier with the most inspections. It retains raw acquisition, SQLite, count checks, export and validation JSON. Unit tests additionally cover rollback, tampering, scope changes, MOTUS keys, profile completeness, unknown carriers, as-of eligibility, conflicting cut IDs and preservation of unrelated databases.

## Next gates

Expand the remaining sources through explicit inspection-parent and docket joins; establish source-window/exposure eligibility and exact SMS release alignment; resolve remaining MOTUS code/amount semantics; retain successive cuts and establish reliable future-outcome ascertainment before fitting a model. Power BI numerical reconciliation still needs matching refreshed exports. The local warehouse is a usable evidence foundation, not completion of the historical modeling phase.
