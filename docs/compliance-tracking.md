# Local compliance tracking

Open **Compliance** in the authenticated local workspace. Enter any USDOT to load its latest stored compliance observation. If none exists, the app derives and stores a dated baseline from the verified nationwide warehouse. A baseline is not a live lookup. **Refresh this carrier now** starts the existing complete 36-source acquisition, verification and promotion pipeline; it does not subscribe the carrier automatically. Daily subscription checks use the same pipeline while the service runs and the computer is awake.

## Evidence checks

`COMPLIANCE_REVIEW_1` evaluates seven source families with eight review checks:

| Evidence | Rule boundary |
|---|---|
| Census registration | Active, inactive and pending remain distinct from operating authority. Missing/ambiguous identity is an evidence gap. |
| MCS-150 reporting date | Reports older than 730 days trigger review; missing/future dates are gaps. This is not a statutory deadline calculation. |
| Current MOTUS authority | Each type/docket/status is retained. Missing, blank or conflicting status is unresolved; non-active status needs review of applicability. |
| Active/pending insurance filings | Exact duplicate business records are collapsed. Future dates need review; missing records/dates remain gaps. Raw amounts are not certified coverage limits. |
| Filing history | Changes effective within 30 days before/after the observation are highlighted. Cancellation, replacement, transfer and name-change source reasons remain visible. No automatic coverage-gap inference. |
| Revocation/suspension records | Records require review of dates, current effect and later reinstatement; an historical record is not a current prohibition. |
| New Entrant OOS | Issue/rescission dates determine the descriptive lifecycle. Entity STATUS is not used as order effect. Missing, reversed and future issue dates remain unresolved. |
| Authority history | Changes within 30 days before/after observation are highlighted with the source type, reason and date. |

Sources: `az4n-8mr2`, `inys-ebih`, `c5y8-a4uz`, `3uet-3z4i`, `wb4f-neki`, `p2mt-9ige`, `yu5v-wbh6`. Source acquisition times, hashes, original rows and pre-normalization row counts are retained. The nationwide reader uses existing exact USDOT mappings; ambiguous/unresolved raw identities are not assigned by name. Checks use the observation date, not today's values backdated into historical observations.

Overall states are **REVIEW_NEEDED**, **INCOMPLETE_EVIDENCE** or **NO_RULE_TRIGGER**. Review/gap counts are shown together. None is a compliance certificate, legal operating determination or proof of insurance. Empty public files do not establish no historical activity or no insurance requirement.

## Refresh and change delivery

Only fully verified cuts are admitted to monitored observations. A failed/partial acquisition leaves the prior dated review intact and records a failed job. Concurrent refresh requests return a visible busy response instead of silently discarding a request. One-off refreshes preserve the daily subscription schedule; retry of an unsuccessful one-off refresh is manual. Scheduled failures retain the existing one-hour retry behavior.

Compliance history is stored per DOT, so these assessment comparisons can continue when the subscribed cohort changes. Both observations must fall within the current enabled subscription period before a change is delivered; first observations and subscription resumption do not backfill prior alerts. Existing raw event/filing alerts retain their separate cohort comparison rules.

One durable inbox item groups changed compliance checks between observations, with previous/current assessment, cut IDs and observation times. This can reflect a dated lifecycle/window transition even when underlying source rows are unchanged. Unchanged daily age values within the same report-age band do not generate alerts. Deliveries and repeated captures are idempotent. No matching SMS-month contract has been introduced, and SMS movement remains excluded.

## Follow-up actions

Each check can have an **Open**, **In review** or **Resolved** action with a due date and substantive analyst rationale. The server binds the action to an existing saved observation/check; client-authored source evidence is not accepted. Action history is append-only. Overdue actions and changed evidence since the review are visible in the tracked-carrier/follow-up queue. Resolving an action neither changes public source records nor suppresses compliance flags. Actions and source evidence remain available after restart.

The tracked-carrier list combines saved policies, subscriptions and previously reviewed DOTs, with 50 carriers per page and the complete denominator. It does not imply that every registration nationwide is subscribed. Open reviews detect newer verified observations every 30 seconds while signed in; an open notes form is preserved until the analyst saves or reloads.

All observations, notes and inbox items stay in the local private SQLite store. No updates are submitted to FMCSA, insurers or third parties. Consult FMCSA's [registration update guidance](https://www.fmcsa.dot.gov/registration/updating-your-registration) and [official authority-status lookup guidance](https://www.fmcsa.dot.gov/faq/how-can-i-check-status-my-operating-authority-mcffmx-number-registration-andor-application-and) to verify or change government records.
