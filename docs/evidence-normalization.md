# Evidence normalization: FMCSA_EVIDENCE_20260908_2

This version describes source interpretation and missing-data presentation. It is not TRI and does not change the frozen v0.1 scoring branch.

## OOS orders

The [FMCSA OOS dictionary, revision 3](https://data.transportation.gov/api/views/p2mt-9ige/files/7259450f-19ab-436c-99c3-62c1f9bcbc1b?download=true) describes one order per row. STATUS concerns the USDOT entity. It does not establish current operating authority or determine whether an OOS order remains operative. OOS_DATE is the issue date; the live schema exposes the dictionary's rescission date as `rescind_date`.

The application separately labels rescinded orders, issued orders with no recorded rescission, future rescission dates and unresolved records. Invalid dates, a rescission before issue, and future issue dates cannot establish a present adverse order. A missing rescission is explicitly described as missing from the record; it is not an independently verified active-order finding. The interpretation uses the evidence view's observation time and does not reconstruct a historical knowledge state.

The real fixture includes USDOT 1438: issue July 9, 2022, rescission July 11, 2022, USDOT status ACTIVE. Its order is displayed as rescinded. Historical-only rescinded orders no longer generate the unrescinded-order review message. Revoke/suspend history remains historical; a changed historical row is not a current-effect revocation.

## Filing changes and amount units

The [MOTUS insurance-history schema](https://data.transportation.gov/api/views/3uet-3z4i) and [daily history-difference schema](https://data.transportation.gov/api/views/xe5s-wca7) distinguish cancellation, replacement, name change and transfer. Each refers to the previous filing. The application retains those event reasons and separately classifies effective/future/unknown dates. It does not infer a gap or confirm replacement coverage from a changed row.

**Amount units remain unresolved.** The [current filing metadata](https://data.transportation.gov/api/views/c5y8-a4uz) describes maximum amounts in thousands of dollars. However, captured common raw values include 750000 and 1000000. Automatically multiplying all values by 1000 produces implausible results across a large population. This is evidence of a source-description/scale discrepancy, not proof of the correct alternative scale. `scripts/fixtures/motus-amount-scale.json` retains the attributed query, description and distribution.

The renderer therefore shows `MAX_COV_AMOUNT` as a **source amount**, with an explicit unit uncertainty note. It applies no guessed currency conversion or magnitude-based heuristic. `UNDERL_LIM_AMOUNT` is a distinct field and is never used as a substitute maximum. A resolved dollar/exposure model remains blocked on authoritative unit reconciliation.

## Missing and partial evidence

- Summary requests all six MOTUS delta feeds before presenting their aggregate. Missing/partial feeds produce unavailable values or qualified lower bounds, not a complete zero.
- Missing crash severity fields remain unknown. Known positive events are retained even when other records are incomplete. Incomplete summary inputs cannot produce a clear review state.
- Fleet acquisition failures end loading and display an evidence failure while retaining the separate carrier-reported exposure. Missing observation sources do not display zero observed VINs.
- Partial source windows produce explicit source notices. No partial browser result is certified as a complete carrier history.
- Failed SMS input sources suppress numerical replay. Cases without a valid denominator are excluded from comparison counts. Successful complete empty queries still describe zero returned rows, never a clean carrier.

Pure runtime and server-rendered component tests cover these cases. Live preview checks include the rescinded-order carrier and USDOT 4127614's filing values. No CSS, layout or navigation changes are included; the compiled stylesheet remains `index-Bm4xuMs8.css`. The unresolved approved visual checkpoint is still required for scoring presentation work.
