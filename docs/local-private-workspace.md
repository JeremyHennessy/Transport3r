# Local private workspace

The public directory now supports 100-row pages with a one-row lookahead, stable USDOT tie-breaks, null fleet/name sorting last, country and state/province source codes, and exposure review details. Filters and page are shareable. Changing a filter or driver sort starts at page one. The source is mutable: pages are not an immutable full-population export.

Exposure flags retain original values. Rules cover missing/invalid counts, non-active registration, missing/stale/future MCS-150 dates, mileage age, zero-unit/positive-driver reports and at least 20 power units with more than 10 units per driver (including zero drivers), or at least 20 drivers with over 10 drivers per power unit. These are review heuristics, not corrected data, a safety score or fraud detection.

## Start and use

Install `scripts/requirements-nationwide.txt` in your Python environment for DuckDB analytics. Then run:

```powershell
./scripts/start-private-workspace.ps1 -PythonExecutable '<path-to-python.exe>'
```

The launcher selects the most recent verified local nationwide warehouse; an explicit `-Warehouse` path is supported. Open http://127.0.0.1:4789/ and set the owner name and password. Portfolio and Alerts in the public app link to this local workspace without making background requests to localhost. The launcher runs hidden and writes its PID/logs under `warehouse/private/workspace`.

This is a single-owner loopback service. It rejects other Host headers and cross-origin writes, hashes passwords with scrypt, uses expiring HttpOnly/SameSite cookies, and serves only three fixed UI assets. It has no public tunnel, shared-account support, cloud synchronization or external email delivery. Files rely on Windows account access controls and disk security; the SQLite files are not independently encrypted. No private directory is served as static content. Do not expose the service beyond loopback.

## Portfolio and inbox

Save/edit account-policy-USDOT records, import versioned `INSURER_PORTFOLIO_1` JSON or export saved records. Existing portfolio validation and append-only history remain authoritative. Renewals use distinct policy IDs. Editing in the form preserves imported fields not exposed by the form, including currency and premium. No private policy data is seeded.

Subscribe to a USDOT from a policy or the Inbox. The service checks enabled subscriptions daily while running, whether or not a browser is open. “Check subscribed carriers now” requests an immediate background run. Each batch contains at most 140 carriers and uses the existing 36-source complete acquisition and promotion pipeline with a one-million-row per-source fail-closed ceiling. A failed acquisition cannot generate a clean result. Very large batches exceeding the ceiling remain failed and visible; operators should reduce subscription batch size before retrying.

The first verified cut is a baseline. Later verified cuts with the same membership are compared by the existing material-change rules. Membership-specific stores prevent comparing different cohorts. Changing membership can require a new baseline. Delivered inbox entries preserve both source observation times, previous/current state, rule, provenance and delivery time. Delivery is atomic and idempotent. Paused subscriptions receive no new alerts; resuming does not backfill previously detected alerts. A failure records a visible job and retries after one hour. Restarted interrupted jobs are labelled interrupted. The service must remain running and the computer awake; this increment does not install a Windows startup task.

“Complete check” means the evidence acquisition/comparison run completed; it is not a clean-carrier conclusion. Newly observed reports may describe earlier events. SMS deterioration is still excluded until releases are bound.

## Reviewed corporate groups

Relationship proposals require two DOTs, a type, an evidence URL and a description. A separate approval/rejection/revocation records the signed-in reviewer and rationale, with immutable review history. Approved common-ownership and parent/subsidiary edges form connected groups; shared-registration-detail edges never do. Approval is an analyst decision, not an independent verification by the app.

Group summaries deduplicate member DOTs and show Census matches, missing members, status/report dates and known/total denominators for reported exposure. Summed registration reports are not a deduplicated physical fleet or insured schedule, and dates can differ.

## Descriptive peers and enrichment

`CENSUS_PEERS_1` uses a verified current Census publication. Peers share country, operation and fleet band; candidates are active registrations. Eligibility requires positive known units/drivers, report dates within the prior 730 days at source availability, and excludes the documented extreme unit/driver ratio. Minimum 30 eligible registrations and an eligible target are required to publish exact 25th/50th/75th exposure quantiles. Candidate, eligible and excluded counts, source cut/hash and dates are returned. This is a descriptive exposure comparison, not a safety ranking, official SMS percentile or pricing model.

NHTSA recall research requests official make/model/year campaign candidates through the [documented recall API](https://www.nhtsa.gov/nhtsa-datasets-and-apis), retaining the query URL and observation time. It does not infer individual VIN applicability, carrier ownership or repair/open/ignored status. Candidate searches do not change scores.

Predictive models remain blocked by unmatched historical releases, immature follow-up and missing insurer claims/loss outcomes and calibration. The existing temporal readiness pipeline remains unchanged. No unsupported model or mock insurance score is released.
