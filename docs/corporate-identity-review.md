# Corporate aggregation and identity review

These features run in the authenticated local workspace, using the verified nationwide warehouse. Public Pages links to the service; private case notes, relationship decisions and portfolio records never enter the public build.

## Corporate aggregation

Use **Relationships → Show reviewed group** with a seed USDOT and a 90/365/730-day safety window. Only approved parent/subsidiary or common-ownership edges enter the connected group. Shared-registration edges, pending/rejected proposals and revoked edges do not. The response includes the approved edges and their review evidence.

Members are deduplicated before Census totals. Known/total member denominators and missing registrations remain visible. Mileage and fleet figures are summed reported values with potentially different reporting dates; they do not establish physical fleet deduplication, insured exposure or ownership at the event date.

Daily inspections and crash vehicle reports are filtered to an inclusive window ending on the earliest of the three source acquisition dates. Exact duplicate records are collapsed excluding only the warehouse ingestion ID. Conflicting event IDs, missing IDs, malformed dates and future dates suppress the complete count and expose known-window rows and issue counts. OOS share is shown only when all relevant OOS totals and event identities/dates are usable. It is a descriptive share of selected inspections, not an official SMS measure. Crash reports are not unique crashes or at-fault events. No SMS scores are added or averaged. Up to 25 example source links accompany each metric; the metric calculation uses every selected record.

This first corporate safety summary covers reported Census exposure, inspections, OOS and crash reports. It does not merge corporate authority/insurance lifecycles or certify historical ownership.

## Chameleon-carrier screening

Enter any unique Census USDOT to search the full registration publication. `IDENTITY_REVIEW_1` matches normalized phone/cell phone (ten digits, accepting a North American +1 prefix), case-insensitive full email, whitespace/case-normalized officer names across both officer slots, nine-digit DUNS, and complete physical address including street/unit, city, province/state, country and postal code. Conservative address matching preserves punctuation and unit numbers. Missing/placeholder values, repeated-digit phone numbers and invalid identifier forms are excluded. Names alone, email domains and partial addresses do not match.

Published `prior_revoke_dot_number` references are returned in both directions and labelled as source references. They do not establish evasion or a verified enforcement finding. A referenced DOT absent from Census will not be a matched candidate, and the reference remains visible in the seed evidence.

Results show every matching category, original source values, normalized values, source cut/hash/time and frequency in the publication. A detail shared by more than 20 registrations receives a common-detail caution. This is a transparent review heuristic, not a statistically validated threshold. Results are ordered by distinct matching-category count and USDOT; two phone matches do not count as two categories. There are 50 candidates per page and a complete candidate denominator.

Shared details can describe legitimate groups, common names, shared offices or service providers. The app does not determine that an entity is a reincarnation, fraudulent or commonly owned. **Draft shared-details relationship** fills the existing proposal form; saving and approval remain separate actions, and shared-details approval never adds corporate membership.

## Ghost DOT review

Per-carrier review compares Census status with dated published inspections/crash reports. The nationwide queue lists inactive/pending registrations with activity in the selected window; 50 candidates per page, ordered by latest activity then USDOT. Opening a candidate runs full event identity/date checks. Unknown/unresolved Census identities and undated activity are not silently treated as clean; per-carrier review reports their limitations, and they are outside the queue population.

`STATUS_ACTIVITY_REVIEW` means current inactive/pending status plus published activity. Census status is not operating-authority status. The current snapshot has no reliable status-effective date. Therefore **activity while inactive is NOT_ESTABLISHED**. Historical activity can predate a subsequent inactivation, and inactivity can have administrative explanations. No result confirms fraudulent or unlawful operation. Missing activity is not evidence that there was no operation.

## Durable case decisions

Both screens support **In review**, **Dismissed** and **Escalated for investigation**, with a substantive analyst rationale. The server recomputes source evidence before saving; it does not trust client-authored findings. Private SQLite tables retain the latest case and append-only decision/evidence history. Saving, dismissing or escalating a case does not change corporate ownership relationships or public carrier data. Case evidence remains available after a later source refresh.

## Verification and boundaries

Regression tests cover missing/placeholder signals, complete-address requirements, cross-slot officer matching, common-detail frequency, deterministic pagination, revocation reference direction, duplicate members/events, conflicting IDs, unknown OOS totals, inclusive dates, source windows, registration ambiguity and private decision history. Authentication and same-origin write checks apply to all new endpoints.

The current publication provides review leads, not changes across historical registrations. VIN continuity, verified enforcement proceedings, actual status-effective dates and independently reviewed ownership documents are useful future evidence. Do not translate review-category counts into fraud probabilities.

Official context: FMCSA's [field operations manual](https://www.fmcsa.dot.gov/sites/fmcsa.dot.gov/files/2024-09/Consolidated%20Electronic%20Field%20Operations%20Training%20Manual%20%28eFOTM%29%20version%209.5..pdf) describes reincarnation/affiliation investigations; [registration guidance](https://www.fmcsa.dot.gov/registration/updating-your-registration) addresses changes to registered business information. These screening rules are Transport3r review heuristics, not FMCSA determinations.
