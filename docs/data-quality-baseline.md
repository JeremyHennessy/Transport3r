# Data quality baseline

Transport3r now has one machine-readable identity contract for all 36 registered FMCSA/DOT sources: `data/fmcsa_source_contract.json`. Python acquisition, nationwide mapping, frontend complete loading and contract validation consume that contract. A row is never assigned to an arbitrary carrier when a direct USDOT, inspection parent or legacy docket is missing, conflicting or ambiguous.

## Acceptance contract

A nationwide cut is accepted only when all 36 complete source downloads pass publication-watermark, schema, row-count, byte-hash and CSV-shape verification. Raw CSV is stored as deterministic gzip to keep the 83-million-row cut practical without creating a second plaintext copy. The warehouse retains raw text fields and a separate indexed identity map for each source.

The acceptance receipt contains, for every source:

- published, acquired and warehouse row totals;
- resolved, identified-only and unresolved counts;
- a specific reason code for every row;
- distinct identified carriers and exact duplicate rows;
- missing, valid and invalid event dates plus earliest/latest valid dates;
- publication watermark and artifact SHA-256.

The receipt's common `cut_available_at` is the immutable 36-source collection completion time, not an individual event date or the last source's event maximum. Individual source acquisition/publication times remain alongside it for audit.

Promotion fails if rows are lost or multiplied, a mapping status/reason is absent, a source is missing, or any raw artifact differs from the verified source cut. `IDENTIFIED_ONLY` rows retain a syntactically valid carrier identifier that is not uniquely present in the same-cut Company Census. `UNRESOLVED` rows remain queryable in raw/mapping tables but are excluded from carrier API responses.

The retained October 23 acceptance receipt is `data/nationwide_acceptance_20261023.json`. Its fresh-process verification covers 36 sources and 83,531,140 rows; published, acquired and warehouse totals are equal. Aggregate mapping is 81,004,526 resolved, 271,159 identified-only and 2,255,455 unresolved rows. The 6.9 GB warehouse hash is recorded in that receipt rather than committing the warehouse binary to Git.

Mapping reasons are deliberately granular. Direct sources distinguish invalid USDOT, no Census row, ambiguous Census identity, resolved identity and Census self-resolution. Inspection children distinguish invalid/missing/duplicate/conflicting parents, invalid or conflicting child USDOT assertions, parent USDOT absent/ambiguous in Census, and resolved parent lineage. Legacy docket rows distinguish invalid/missing/multi-owner/unknown-owner dockets, owner USDOT absent/ambiguous in Census, and resolved docket lineage. The receipt retains the count for each reason by source; no catch-all reason can silently absorb rows.

## Golden regression set

`data/golden_carriers.json` freezes the passing October 23 reconciliation: 97 exact Census identities, 25 detailed carriers and six prior regressions. CI uses the 25-carrier cohort for complete 36-source acquisition/warehouse promotion and uses all 97 identities plus the 25 detailed source windows for live mapping reconciliation. It is an engineering regression population, not a representative statistical sample.

`data/golden_verification_20261023.json` retains the passing exact-cut receipt: 197 live/warehouse/API checks, no failures, and matching publication watermarks for the five compared sources. The receipt binds the result to the accepted nationwide cut and warehouse hash.

## Serving contract

`scripts/evidence_api.py` serves a verified nationwide DuckDB read-only. Carrier responses require one unique Census identity and return all `RESOLVED` rows from all 36 sources with a common-cut/hash/completeness receipt. The receipt and existing coverage panel expose population-wide resolved, identified-only and unresolved totals; unresolved/ambiguous rows are never returned as carrier evidence. Configure `VITE_EVIDENCE_API_URL` (the Pages workflow reads repository variable `EVIDENCE_API_URL`) to make Carrier 360 use this API. Without that deployment variable, the app explicitly labels its existing complete fallback as a live public-source window rather than a warehouse cut.

The service can run directly or from `deploy/evidence-api/Dockerfile`; mount the verified DuckDB and set `EVIDENCE_WAREHOUSE`, `EVIDENCE_ALLOW_ORIGIN` and `PORT`. `scripts/validate_golden_warehouse.py` refuses comparison unless the retained live reconciliation and warehouse share exact publication watermarks, then compares live, warehouse and API counts across the frozen set.

## Temporal and scoring boundary

`data/temporal_policy.json` makes cut completion the knowledge time, prohibits cross-cut mixing and prohibits backdating current values. The retained October 23 SMS observation confirms that the official website exposes a September 25 snapshot date but no artifact identifier binding that release to the eight exact DataHub extracts. SMS monthly binding, historical feature validity, forecasting and TRI v0.1 therefore remain blocked rather than inferred.
