# Transport3r repair sequence

Custody audit: September 8, 2026. The scoring branch `feature/tri-score-v01-20260908` / PR #17 remains separate. Its frozen reference is `7d61b32268e089fb0da090628641ef2b5f6bad0a`; no TRI formula is included in these repairs.

## Production recovery

PR #18 restored GitHub Actions as the sole Pages publishing source. Production commit `a094293ed81c42813de35519938045f62900bc7d` passed the release manifest verifier and rendered route checks. Every build now carries a full commit SHA, build time, bundled source-metadata cut and artifact hashes. These metadata cuts are not historical carrier snapshots. The verifier rejects development HTML, a stale SHA, mixed files and missing assets.

## First data-integrity repair

- Daily violation OOS, description and unit bindings use actual registered fields; the Safety vehicle-violation and insurance cancellation-date bindings are corrected as well.
- Calendar dates use one strict parser for Safety/insurance date values. Compact YYYYMMDD and legacy MMDDYYYY are recognized, invalid dates return unavailable, and date-only values retain their calendar day across time zones.
- All 500 loaded inspection IDs can feed child queries. Ordered pagination and a one-row lookahead distinguish an exact complete window from a truncated window. Child caps are forwarded; partial results do not claim an exact total.
- Parent inspection and legacy docket-bridge errors remain dependent-source errors. Parent truncation propagates to child coverage. Child cache keys include the actual parent IDs.
- Missing row-count displays and unavailable OOS counts use an unavailable value. SMS comparisons report PARTIAL_DATA when a required source fails. Summary also loads the insurance-history delta.
- The daily violation fields are required by the live schema contract. Runtime tests use a captured public source fixture, boundary dates, paging caps and dependency failures. Fleet validation fails on mismatches and insufficient samples.

Carrier markup structure, navigation, labels, stylesheet imports, and all CSS remain unchanged. The component edits are data bindings and a date-helper call. The compiled CSS retains `index-Bm4xuMs8.css`. The supplied approved visual checkpoint `25157fb` still cannot be resolved; it has not been replaced with another purported approval. Presentation/design work on the scoring branch remains blocked by that missing checkpoint.

## Evidence lifecycle and acquisition repairs

PR #20 preserves unknown/partial evidence in Summary, Fleet and SMS, loads all six MOTUS change sources, distinguishes rescinded order history from orders without a recorded rescission, and separates previous-filing event reasons from current coverage claims. MOTUS maximum amounts are shown as raw source values with unresolved units; no scaling or underlying-limit substitution is applied. See [normalization rules](evidence-normalization.md).

The append-only raw acquisition writer and offline verifier now establish a current-source baseline with artifact hashes and acquisition-time lineage. The initial live check covered two sources, not the full catalog. See [snapshot acquisition and limits](snapshot-acquisition.md). Historical carrier-month features and forecasts remain unimplemented and unvalidated.

## Outstanding release gates

[Large-carrier count repair](large-carrier-counts.md) separates full inspection-file totals from bounded loaded evidence, preserves dated Census driver reports and inactive registration context, and resets carrier identity/evidence when USDOT changes. The live regression now includes large active carriers and an inactive registration. These file counts are not claimed as SAFER 24-month totals.

SMS runtime input validation now rejects invalid weights, duplicated parents, orphan violations and carrier contamination. CI compares the actual application TypeScript to retained official records. [Population selection](sms-population-selection.md) now distinguishes general and passenger-specific AB/C outputs, rejects unresolved population conflicts and keeps comparisons without a denominator unavailable. [Query-window consistency](sms-query-cut-consistency.md) now rejects source changes around the live regression's acquisition window. [Event-date integrity](sms-event-date-integrity.md) rejects missing, invalid or conflicting parent/violation dates and retains event-date ranges without treating sparse history as missing data or inferring a monthly snapshot. See [SMS replay integrity](sms-replay-integrity.md). Full-population and exact monthly alignment validation remain separate gates.

The next offline repair adds a seven-source cohort acquisition and acquisition-time feature builder, with a 62-carrier live engineering pilot. It rejects backdated month ends, preserves unknown rates/labels and retains each SMS population separately. The frozen v0.1 model card, diagnostic results and exact source identities now live under `research/`. See [as-of pipeline and remaining temporal gates](asof-research-panel.md). This is not completion of historical training data or model validation.

This initial repair does not certify Phase 1 complete or make TRI releasable. Browser requests remain bounded (500 inspections, 350 crashes, bounded child batches); their returned history is not a standardized current-risk observation window. Live paging is not a transactional historical snapshot and upstream changes during paging remain possible. [Socrata paging guidance](https://dev.socrata.com/docs/paging.html).

1. Resolve the approved visual SHA and approval record before scoring presentation work.
2. Resolve remaining filing-code mappings and contradictory MOTUS amount units using authoritative clarification. Preserve uncertainty for unknown dates/codes and do not infer current coverage from historical filings.
3. Freeze TRI v0.1 and implement any material scoring changes under a new version. Set eligibility, comparable component masks, observation windows and source-cut requirements. Public property SMS percentile availability and passenger/property selection need explicit treatment.
4. Audit remaining missing-source/partial-data renderers across carrier modes. A successful empty result describes returned rows, not a clean carrier. No current-risk score is introduced in this repair.
5. Extend verified raw acquisition to the required modeling sources and construct a small knowledge-time-aware carrier-month panel. Do not backdate current Census/SMS values.
6. Evaluate score distributions and subgroups only with correct features; train and calibrate event-specific temporal baselines only after historical integrity passes. No insurance-loss model without actual insurance outcomes.

No forecast, peer percentile, statistical confidence or actuarial validation is claimed by these changes.
