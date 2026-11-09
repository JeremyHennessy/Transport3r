# Snapshot-consistent reports and VIN-linked findings

This change extends the open-data evidence core; it does not establish production deployment, complete fleet coverage, repair completion or insurance outcomes.

## Reports

Report safety windows are filtered from the same retained carrier evidence, rather than acquiring a new live safety window after selecting an accepted warehouse. Warehouse reports and exports require matching carrier, release, SHA-256, source lineage, row selection and quality accounting. Missing or invalid dates and dates beyond the retained cut remain explicitly incomplete. Independently verified source totals are preserved when only detail pagination is partial.

The Safety page uses the shared accepted-warehouse cache when that backend is configured. The explicitly separate live-window mode remains available when no warehouse is configured. No fallback turns a failed warehouse into a live verified result.

## VIN findings

A vehicle finding requires a verified carrier and unambiguous inspection parent, followed by a same-inspection unit match. Explicit unit IDs take precedence; contradictory IDs cannot fall back to a convenient unit number. Number-based fallback requires a unique match in a complete unit lookup. Foreign or conflicting parents, ambiguous units and unsupported references remain unassigned. Exact duplicate violation rows and conflicting violation identities are accounted for separately.

The UI retains source records, raw defect-verification codes and unknown OOS values. Repeated codes mean repeated observations, not proven unrepaired defects. Driver-only context and another vehicle's violations are not assigned to the selected VIN.

## Validation boundary

Synthetic regressions cover identity, source lineage, date boundaries, row conservation, unknowns and no-live-refetch behavior. The existing read-only browser workflows exercise the actual production bundle. Browser checks must pass on the exact published revision; earlier map screenshots do not verify these new changes. No national source acquisition or insurer acceptance is claimed.
