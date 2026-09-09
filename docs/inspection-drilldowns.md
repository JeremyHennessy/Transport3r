# Complete inspection children and report/VIN drilldowns

## Acquisition contract

`underwriting_evidence_v2` is an 18-source, schema-v5 profile. It extends the unchanged 14-source v1 profile with inspection units (`wt8s-2hbx`), violations (`876r-jsdb`), citations (`qbt8-7vic`) and special studies (`5qik-smay`). Baseline v3 and v1/v4 cuts remain readable. Every required source must complete before promotion.

`scripts/inspection_children.py` constructs a unique inspection-ID → USDOT map from the complete preserved daily inspection extract. Child payloads retain their original fields; no fabricated USDOT is inserted into the raw JSON. The SQLite carrier index derives USDOT through that map and rechecks it during verification. Daily child rows and SMS violation rows keep their different source identities and join keys.

Child queries cover the entire preserved parent set in deterministic, disjoint batches of 250 IDs, using the registered numeric/text inspection-key type. Four worker threads acquire independent batches. Source metadata/counts must be stable around the whole child extract, and each batch has exact preflight and post-download counts, contiguous hashed pages and unique Socrata row IDs. Aggregate preflight counts enforce the accepted source ceiling before page downloads; a changed or oversized response fails rather than returning truncated success. Child acquisition must follow parent availability, and the parent source must still match its original watermark, schema, table identity and cohort count after each child family completes. An empty verified parent set has zero child batches, not a made-up child lookup.

The offline verifier rejects missing batches/pages, changed query scope, parent-map changes, orphan children, contradictory child USDOTs, duplicate source IDs, count mismatches and chronology changes. Raw payload hashes and the derived carrier indexes are checked after atomic warehouse promotion. Publication stability is not a transactional multi-source snapshot or proof of matching SMS months.

```sh
python scripts/cohort_snapshot.py --profile underwriting_evidence_v2 --cohort warehouse/raw/PRIOR_CUT/cohort.json
python scripts/verify_snapshot.py warehouse/raw/NEW_CUT
python scripts/evidence_warehouse.py promote warehouse/raw/NEW_CUT
python scripts/evidence_warehouse.py export --dot 3706 --profile underwriting_evidence_v2 --output UNIQUE_carrier_export.json
python scripts/validate_evidence_warehouse.py --cut warehouse/raw/NEW_CUT --output UNIQUE_validation_directory
```

`validate_evidence_warehouse.py` now acquires v2 by default in CI, while accepting preserved v1 cuts for compatibility. All carrier/source counts and all sources in the largest carrier export are reconciled. Historical MOTUS/docket joins remain outside this profile.

## Browser behavior

The existing `#/carrier/{USDOT}/inspection/{ID}` route previously searched the 500 recent loaded carrier inspections. It now queries the selected inspection directly, requires one unambiguous matching ID and USDOT, then loads its four child families independently. Missing, ambiguous and wrong-carrier parents prevent child queries. Failed child requests remain unavailable; successful empty requests remain empty. Each child is bounded at 5,000 rows with lookahead and visible partial status. Coverage export now includes the selected inspection ID and labels its scope explicitly.

The inspection page shows the official report number/date/state/level, child counts, source records, observed units and a Refresh action. Refresh issues new requests, allowing failed child sources to recover. Route changes hide prior inspection content immediately, and obsolete responses cannot overwrite a newer inspection.

VIN links in Fleet open `#/carrier/{USDOT}/vin/{VIN}` with observations from the existing recent inspection/unit window. Each displayed unit requires a matching, unambiguous parent belonging to the carrier. VIN links from a specific inspection append `?inspection={ID}` so an older observation remains reachable even outside the recent 500 inspections. The page explains its selected-inspection scope and offers a separate link to the recent carrier window. Inspection links return to their verified parent report. Observations do not establish ownership, a current fleet schedule or insurance coverage.

The browser continues to query public FMCSA sources. It does not download or serve the local SQLite warehouse; complete offline cohort exports and bounded browser requests remain distinct products. No score or source population is changed by these routes. The work uses existing navigation/components/styles, with a small scrollable table style for drilldown records.

## Acceptance evidence — September 9, 2026

Preserved cut `20260909T121214040360Z-20d16b62`, available at `2026-09-09T12:18:19.748186Z`, has manifest SHA-256 `751a5eb9bc05534e7f67dba85710378ac47f29da62bb0e9fed5e25c7f280fd2e`. It retains the same 62-carrier cohort (SHA-256 `7821dbea2a4a806d2d8af22c04d388f30ca43ad1aa3d87bca1cec7d1064075c8`).

| Preserved rows | Count |
| --- | ---: |
| Original 14 sources | 109,466 |
| Inspection units | 72,877 |
| Inspection violations | 22,491 |
| Inspection citations | 51 |
| Inspection special studies | 7,442 |
| Total, 18 sources | **212,327** |

All **102,861** daily child rows pass parent-based carrier assignment. All **1,116** carrier/source count checks pass, and all **10,048** SMS violations still pass the separate SMS parent/date audit. The cut was promoted into the existing warehouse while preserving the earlier seven- and 14-source cuts. Local validation evidence is retained under `outputs/inspection-children-validation/`.

The production-build browser gate adds nine simulated checks for deep links, all four child families, VIN context, return navigation, wrong carrier, missing parent, stale response isolation, unavailable counts and refresh recovery. Unit tests cover exact paging boundaries, typed parent queries, aggregate ceilings, tampering, empty parent sets, duplicate/orphan identities, v5 warehouse indexing and legacy compatibility.

Real public-source browser verification opened inspection **79625568**, report **5410000300**, dated **September 10, 2023**, for USDOT **3706**. It returned two observed units, including VIN **3AKJHHDR1NCMS1700**. The VIN route retained the deep inspection context and linked back to the report. The same inspection ID under USDOT 2855794 was rejected. Fleet → VIN → inspection links also worked for USDOT 3938496. Desktop/mobile screenshots and six real-data checks are retained in `outputs/inspection-local-ui/`.

## Remaining gates

Establish exact SMS release alignment and exposure eligibility, then add explicit event-window controls with source-aware monthly counts. Full retained VIN history can be exposed through a separately designed warehouse service/export workflow. Complete remaining MOTUS history/delta and legacy docket acquisitions before treating this as the full 36-source warehouse. Historical observations, future labels, percentiles and a numeric risk model remain separate validation work.
