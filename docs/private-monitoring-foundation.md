# Private portfolio and durable change monitoring

This document describes the original local foundations. The subsequent password-protected loopback UI, acquisition scheduler, durable inbox, reviewed relationships and descriptive peers are documented in [Local private workspace](local-private-workspace.md). The public Pages site still does not host private records.

Implemented local foundations; neither is a hosted multi-user service. GitHub Pages continues to display the product boundary. No insurer policies have been invented, imported into public data, or committed.

## Portfolio contract and storage

`data/portfolio-schema.json` defines the versioned `INSURER_PORTFOLIO_1` import envelope. `scripts/portfolio_store.py` validates the whole batch before a transaction, rejects duplicate account/policy keys, and preserves an append-only change history. Identical imports are idempotent. Policy dates are ISO calendar dates with a positive period. Limits/premium are integer minor currency units with an explicit three-letter currency. Units and insured VMT are nonnegative integers; unknown values are null. Insured exposure never falls back to Census values. Account, policy, USDOT, dates, status and review status are required; text lengths are bounded. An account/policy key represents one policy record; give renewals distinct policy identifiers.

Local command: `python scripts/portfolio_store.py --db warehouse/private/portfolio.sqlite --input <private-envelope.json>`. The default architecture is an operator-owned local SQLite file, protected by the operator's filesystem access controls. `public` and `dist` paths are rejected. Private/monitoring folders are ignored by Git. Import validation is not encryption or tenant authentication. Local backup/retention policies remain operator responsibilities.

Before connecting the public Portfolio page: introduce an authenticated private service, tenant-scoped authorization, encrypted transport/storage, validated identity assignment, per-tenant audit/export/deletion policies and durable backups. The service must use this contract rather than publish policy data as Pages assets or browser-only fake persistence. No service or tenant account is provisioned by this increment.

## Material-change observations

`python scripts/material_alerts.py --evidence-db warehouse/curated/evidence.sqlite --alerts-db warehouse/monitoring/alerts.sqlite` compares the latest two eligible verified cuts. Explicit `--previous-cut` and `--current-cut` are supported. Cohorts must match, observations must be strictly ordered, and only common source families are compared. Audit-only identity cuts are excluded. A repeated cut pair/rule version is idempotent.

Stored alerts retain USDOT, previous/current state, source, both cut IDs and source observation times, detection time, evidence link and the materiality rule. Rules cover newly observed crash reports, newly observed positive-OOS inspections, violation record-set changes, authority/filing record-set changes and reported exposure/status/date changes. Numeric exposure changes require at least 10 percent and one unit. Missing/invalid values produce issues, not zero-change claims. Socrata row-ID churn alone is ignored in record-set comparisons. Newly observed events may have occurred earlier; source corrections are possible. Filing record changes are review signals, not automatic coverage gaps or legal prohibitions.

SMS movement is explicitly not evaluated until exact comparable releases are bound. There is no scheduler, notification delivery or browser subscription service. Run the comparison after a new complete cut is acquired and verified. Two observations only hours apart demonstrate durable comparison, not a mature monitoring history.

## Temporal and model gates

`capture_sms_release.py` preserves official SMS website HTML plus eight DataHub metadata documents and hashes. A website snapshot date is not assigned automatically to those DataHub extracts. `temporal_readiness.py` checks availability and reported-exposure eligibility, retains source/date issues and emits null future labels with explicit blockers. `build_asof_panel.py` selects only verified cuts knowable at the requested UTC time. It rejects unavailable prior month ends and future observations.

The current cohort is deliberately small and nonrepresentative. No matched historical month-end panel, mature future follow-up, insurer claims/loss dataset, TRI v0.2 scores or forecasts are created. First acquire immutable monthly releases with verified source binding, retain contemporaneous exposures, establish population/missingness rules and a reporting-lag surveillance policy. Then form prospective 90/180/365-day labels with complete follow-up, temporal splits and subgroup/calibration checks. FMCSA involvement/OOS outcomes must remain distinct from insurance loss.
