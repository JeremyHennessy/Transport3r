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

## Remaining gates

This initial repair does not certify Phase 1 complete or make TRI releasable. Browser requests remain bounded (500 inspections, 350 crashes, bounded child batches); their returned history is not a standardized current-risk observation window. Live paging is not a transactional historical snapshot and upstream changes during paging remain possible. [Socrata paging guidance](https://dev.socrata.com/docs/paging.html).

1. Resolve the approved visual SHA and approval record before scoring presentation work.
2. Normalize current effect versus historical orders, rescission, and filing event direction from documented source semantics; retain uncertainty.
3. Freeze TRI v0.1 and implement any material scoring changes under a new version. Set eligibility, comparable component masks, observation windows and source-cut requirements. Public property SMS percentile availability and passenger/property selection need explicit treatment.
4. Audit remaining missing-source/partial-data renderers across carrier modes. A successful empty result describes returned rows, not a clean carrier. No current-risk score is introduced in this repair.
5. Establish immutable raw snapshots and a small knowledge-time-aware carrier-month panel. Do not backdate current Census/SMS values.
6. Evaluate score distributions and subgroups only with correct features; train and calibrate event-specific temporal baselines only after historical integrity passes. No insurance-loss model without actual insurance outcomes.

No forecast, peer percentile, statistical confidence or actuarial validation is claimed by these changes.
