# Transport3r production readiness: executable gate contract
Updated 2026-11-08. Baseline: protected main `2f75f0c23a741e344667aa1a6681b1d5e0d1a1c8`. This document is a **plan and verification contract**, not evidence that any pending gate passed.

## Immutable release boundaries

- PUBLIC: GitHub Pages static app. Last independently recorded successful release: Actions 42320761938; hosted full SHA `2f75f0c23a741e344667aa1a6681b1d5e0d1a1c8`; 18 routes/36 viewports; screenshot artifact 13552488061. Preserve f733/e27 failed runs as failures.
- PUBLIC-SOURCE API: allow-listed, read-only FMCSA/FEMA metadata; not installed on durable authorized hosting. No private insurer data.
- PRIVATE: operator-only portfolio and loss-history CLI from #66, not an authenticated multi-user browser/API and not installed or accepted by an insurer.
- RESTRICTED: do not retry NOAA integration publication, new nationwide workflow publication, or blocked local browser navigation by another tool or path. NOAA #60/#61 remain open and blocked; TRI #17 remains draft. No paid hosting without explicit approval.
- DO NOT publish policy IDs, account IDs, claim records, insurer documents, shipment locations, authentication material, or private screenshots to public Pages, GitHub source, source API, or public CI artifacts.

## Gate A: full nationwide source acceptance (BLOCKED pending authorized acquisition)

Inputs: a retained immutable **full nationwide** original-source cut with publisher URL, observed/published vintage, SHA-256, source schema and identifier mapping for each of the 36 sources. The verified 25-carrier cohort (496537 source records; 241341 child rows; 900 count checks) is **not** a substitute.

1. Run the existing `scripts/audit_warehouse_integrity.py` with `--deep` against the retained full source warehouse and output a versioned receipt outside public assets. Do not run a prohibited new publication workflow.
2. Independently recompute source counts from original rows, count exact duplicates **excluding ingestion row ID**, validate key uniqueness and foreign keys, source-to-carrier identity, orphan rows, join fanout and conservation by source. Keep original and normalized grain counts separate.
3. Require PASS/release_ready true, same SHA/cut in receipt and warehouse, 36/36 source coverage, zero unexplained discrepancies, explicit null/unknown counts. Preserve rejected and exception rows with reason codes; never silently discard them.
4. Repeat from preserved bytes on a second clean runner and compare normalized outputs and receipt hashes. Fail closed if source unavailable, schema drifted, receipt missing, or count reconciliation differs.
5. No nationwide totals, duplicate metrics, carrier exposure counts, or scoring in UI until a deployed API has the **same accepted** cut and SHA.

Evidence: immutable original source manifest, deep audit JSON, reproducibility comparison, rejection register, reviewer signoff, authorized release ID.

## Gate B: durable public-source API (NOT INSTALLED)

Existing reference: `docs/evidence-api-fema-deployment.md`, `deploy/evidence-api/compose.nri.example.yml`. Loopback Docker is not durable production.

1. Obtain explicit authorization for the host/network and any spend. Design private/public separation first. Do not expose port 8787 directly.
2. Install only accepted, read-only, SHA-pinned source indexes; nonroot container, least-privilege mounts, TLS, rate limits, access policy, request limits, security updates, monitoring, encrypted storage, backups and restore rehearsal.
3. Verify `/healthz`, `/v1/integrity`, FEMA status/FIPS lookup, and carrier evidence with same release SHA/cut. Reconcile actual HTTP JSON with SQL and source receipts for sampled and edge-case carriers.
4. Test restart, failure/503, stale manifest, missing source, source swap, rollback and restore. Verify public Pages never requests a private endpoint or localhost on an external browser.
5. Record host release, container digest, DB/index hashes, public endpoint access controls, test results, on-call owner and rollback instructions. Only then connect EVIDENCE_API_URL.

Evidence: actual authorized installation ID, deployed image digest, health/API responses, reconciliation, security signoff, recovery test.

## Gate C: authenticated private claims workflow (IMPLEMENTATION PENDING)

Reuse `scripts/private_loss_history.py` and `docs/private-loss-history-intake.md` as the single validation/accounting engine. Do not rewrite identity or bypass the preview fingerprint.

1. Design authenticated private API/UI with organization, user, reviewer role and explicit account/policy scope. Enforce authorization on every request and every row; fail closed on unknown tenant or role.
2. Upload private normalized loss data into an isolated encrypted workspace. Enforce file size, schema, currency, date, policy/account/USDOT/coverage identity and document provenance; reject narratives/PII beyond the allowlist.
3. Preview is read-only and returns explicit unmatched/ambiguous/conflicting reasons. No ledger file, state mutation, or public artifact from preview.
4. Commit requires a separate authorized reviewer, permission confirmation, exact input+portfolio+schema fingerprint, audit trail and idempotency key. Reject changed input, cross-tenant policies, identity reassignment and stale approvals.
5. Preserve atomic all-or-nothing writes, immutable valuations, stable (source_id, claim_id) identity, null-vs-zero, currency separation, no double counting of snapshots, and rejected unversioned ledger migration.
6. Test two-tenant isolation, horizontal/vertical access, forged session, replay, CSRF where applicable, concurrency, stale approval, rollback, backup/restore and zero private-data leakage into logs/public bundles. Synthetic test fixtures must contain no real insurer data.
7. Require an independently authorized real insurer sample and manual reconciliation before labeling as insurer-accepted. A green CI suite does not constitute private installation.

Evidence: threat model, endpoint contract, authz matrix, synthetic end-to-end checks, reviewer signoff, private install verification, separately controlled real-file acceptance.

## Gate D: geography and route attribution (NOT ACCEPTED)

- Maintain explicit location classes: carrier HQ, independently verified terminal, recorded inspection/crash point, actual dated GPS trip, hypothetical route. Never infer a driven route from HQ or county.
- Require geometry, coordinate reference system, publication/effective date, precision and identity for every point/polygon/line. Source-reported event points are not complete event footprints.
- Test invalid coordinates, duplicate features, boundary intersections, nulls, stale vintage, route crossing, antimeridian and distance-decay sensitivity before any H3/exposure overlay.
- FEMA county NRI is relative community context, not insured loss. NOAA source observations remain blocked from publication. No risk-colored map until evidence and semantics are approved.

Evidence: geometry QA report, source identity links, reproducible intersections, reviewed legends and screenshot tests.

## Gate E: TRI and actuarial scoring (WITHHELD)

- #17 official SMS percentages like `"0%"` and `"4%"` must parse correctly or be flagged unavailable; missing official backbone must never silently produce a credible numeric TRI. Preserve distinctions between research score, official FMCSA output and actuarially validated model.
- Require exact FMCSA cut and peer population, passenger/property rules, time-valid exposure and claims, censoring, leakage and mix controls, out-of-time and out-of-carrier validation, uncertainty, calibration, fairness, drift and independent signoff.
- Until complete, suppress numeric TRI/risk forecasts, hazard colors and claims-based premium/loss predictions.

## Protected release procedure

For each permitted branch: confirm fresh Issue #57 and main SHA; fetch exact PR head, reviews, unresolved threads, required checks and ancestry. Fix only the authorized branch. Never weaken tests or bypass protection. Merge only after exact-head checks/reviews pass. Then verify new Pages run, hosted full SHA, 18 routes/36 viewports, screenshot ZIP SHA and 58 embedded hashes, and visually review Integrity/Insurance/Atlas. Keep historical failures. Update Issue #57's **matrix**, not only comments. Independently verify private installation and data acceptance.

## Current blockers / ownership

| Gate | State | Missing acceptance |
| --- | --- | --- |
| A nationwide | Blocked from new workflow publication | Authorized complete source cut and independent deep reconciliation |
| B hosting | Not installed | Host approval, security and durable runtime |
| C private claims | CLI implemented only | Authenticated UI/API, security tests, private installation and real insurer acceptance |
| D geography | Observational Atlas | Verified geometry/actual routes and source-safe exposure semantics |
| E scoring | Draft #17 blocked | Percent parsing, comparable population, outcome/model validation |

Do not mark any gate complete based solely on this document, a PR merge, synthetic CI, a probe, or a 25-carrier cohort.
