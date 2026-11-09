# Data acceptance report

## Historical evidence, not current production acceptance

`data/nationwide_acceptance_20261023.json` retains 36 source datasets, 83,531,140 original
source rows and 4,521,010 Census rows. Its duplicate fields equal row count minus one for
all 36 datasets. These duplicate metrics must not be served as valid measurements. The current
original-column duplicate function is corrected; this does not retrospectively repair an old
receipt. The old file remains unchanged.

Issue #57 retains separate November 6 cohort evidence: 25 carriers, 36 sources, 496,537
records and 900 carrier/source comparisons. This is not a national population, a count of
unique incidents, a common SMS release or actual insurer loss experience. This execution did
not re-download that raw cohort and does not re-certify it from the issue text alone.

The failed real-source gate `42611969386` was 33 COMPLETE / 3 FAILED and was not promoted.
Inspection units, special studies and citations changed counts/publications during acquisition.
PR #69 is active concurrent work. Always retrieve its exact head and check results, not a
possibly stale SHA in its description.

## New implemented gates

- The public evidence API withholds carrier evidence when its independent audit is missing.
  `/healthz` remains process/source liveness; `/readyz` requires installed deep-audit acceptance.
- The frontend verifies that carrier receipt, API health and independent audit all describe
  exactly the same warehouse hash, cut, source coverage and source lineage. Missing or mixed
  releases do not fall back to a verified success.
- Staging re-runs deep warehouse checks, copies to a new content-addressed directory and checks
  copied files again. Activation is an auditable pointer change, not an HTTP deployment claim.
- Date plausibility is evaluated against the explicitly pinned collection time, never today's
  clock. Original values are retained. Parseable future insurance effective dates can be
  legitimate; they are reported as review flags rather than silently discarded.

## National acceptance still required

For every registered source retain original URLs/bytes/SHA, publisher and acquisition times,
published/downloaded/accepted/rejected/indexed counts, duplicates, dates, source grain and
identity reasons. Reconcile parent-child and docket joins without orphan/fanout losses.
Require full source-count conservation, independent deep audit and exact file/cut hashes.
Original raw bytes must be checked separately: the deep warehouse audit and installation tool
compare warehouse/receipt lineage but do not reread every original download.

No new accepted nationwide warehouse exists in this execution environment. No new audited
national totals, corrected national duplicate figures, current API SLA, exact monthly SMS
binding or historical feature panel is claimed. New unit/HTTP/restore fixtures are explicitly
synthetic and must never become public source acceptance artifacts.
