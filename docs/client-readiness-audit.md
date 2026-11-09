# Client-readiness execution audit

Reviewed 2026-11-09. Baseline: protected `main` commit
`2f75f0c23a741e344667aa1a6681b1d5e0d1a1c8`, tree
`f8b59c9423f6e44006494eba918a9a2923fb0394`. This document describes the
`work/client-readiness-execution-20261109` implementation, not an accepted production installation.

## Release assessment

The existing public application is an evidence-research demonstration. A complete nationwide
API, insurer production installation, multi-user authorization and actual insurer acceptance
have not been established. A route rendering pass, source probe or synthetic fixture does not
certify those later stages. See [acceptance matrix](client-acceptance-matrix.md) for exact scope.

## Execution inventory

| Priority / workstream | Prior implementation | Changes in this execution | Remaining acceptance |
| --- | --- | --- | --- |
| P0 warehouse-to-browser gate | Carrier receipts and a separate Integrity page | Carrier loading now requires the matching deep audit and health response: exact cut, warehouse hash, all 36 source identities/hashes/times and mapping totals; bounded transfers, abort and failure handling | Real installed nationwide release, actual HTTPS and UI reconciliation |
| P0 public API readiness | Health could be green without installed audit | `/readyz`; carrier evidence returns 503 without matching deep audit; Docker healthcheck uses readiness | Authorized host, capacity/security tests and post-deployment checks |
| P0 data dates | Parseability only | Pinned-cut plausibility flags for dates before 1900 and after the collection cut; raw values retained; future effective dates are review flags, not automatic errors | Re-run on actual complete national raw sources |
| P0 release operations | Manual immutable files and documented rollback | Revalidated staging, hash-bound installation manifest, compare-and-swap activation history, rollback and restore/corruption drills | Durable approved installation and restart/HTTP verification |
| P0 private loss intake | Offline CLI/storage | Authenticated browser/API preview, signed ten-minute approval, session/owner binding, original-byte hashes, atomic import, read-only history and valuation export | Independent review, real insurer source acceptance; not multi-tenant |
| P0 linked policy identity | Reviews protected some HTTP changes; claims separate | Cross-process portfolio/loss write lock; accepted-claim policy identity/period/currency changes blocked through the shared importer | Reviewed amendment/migration workflow for legitimately changed policies |
| P0 private storage | Launcher default inside repository | OS user-data directory outside Git; explicit migration requirement for legacy files; no silent movement/deletion | Windows ACL and encrypted-storage verification on actual host |
| P1 client reporting | Existing public reports | Loss valuation summaries carry batch, input/portfolio hashes, reviewer and import time; currencies remain separate; unknowns retained; money displayed as explicit minor units | Full policy decision packet and real source-document reconciliation |
| P1 existing ingestion/release PRs | #67/#68/#69 under active work | Read exact current heads/checks, avoid competing changes; no weakened limits or fabricated success | Independent rereview, successful exact-head full CI and protected release |
| P1 geography | State observations, accepted local FEMA county source; NOAA draft | No unsupported carrier-route inference or fabricated hazard scores added | Approved NOAA release, further official sources, verified coordinates/routes and hosting |
| P2 modelling | TRI draft #17 with known parsing/completeness defects | Numerical score remains withheld | Research corrections, exact SMS binding, outcome validation and expert approval |

## Evidence and test discipline

The local checkout was reconstructed from an existing CI source archive. Before modifications,
its Git tree was verified to equal the protected-main tree above. Tests execute the actual changed
modules, including real loopback HTTP requests against synthetic databases. Browser tests are
part of the existing reproducible application-review workflow; a newly written browser test is
not counted as passed until its run succeeds and images are inspected.

Historical receipts, old failed workflow runs and the October 23 nationwide JSON are unchanged.
No full national source acquisition, NOAA publication, paid resource, production tenant or real
insurer claim was created by this execution. None of the local test fixtures is promoted as data.

## Review and release

Submit this branch for independent review and exact-head CI. Reconcile concurrent #69 before
merging if its change is needed for live-source acceptance. Resolve findings on their actual
reviewed head; do not self-approve or use earlier checks as approval for later code. After merge,
verify the hosted full SHA and source-to-HTTP-to-UI agreement, not only navigation screenshots.

## Independent review follow-up and retained browser evidence

Initial PR #70 head `eb01c486fb5e562b7c3fda6fd0659a78fea568bd` passed fast validation,
FEMA source validation and reproducible browser review. Run `42630237433` exercised the new
private loss workflow and API/browser integrity integration. Artifact `13680785904` ZIP SHA-256
`3e04c37074b37b795d87dd271266fdcfa457ffddc32f131e9d21909a22661981` was verified;
all 279 archived source files matched the tested local source tree and all six release asset
hashes matched. CI built merge ref `4aa2394c5848b6916c3dde11412850eec4484e49`, whose
source tree matched the PR implementation. Actual desktop/mobile loss images were inspected.
These are synthetic browser checks, not a private installation or new national source cut.

Independent review then found that legacy-ledger rejection could mutate schema, and release
staging/activation needed directory fsync ordering. The legacy defect was reproduced: four of
five new regressions failed before the fix. Schema initialization now uses rollback-capable
DDL, with byte-preserving rejection checks. Staging fsyncs populated directories before rename
and their parent after rename; activation persists history before switching the current pointer.
Durability-order and failure-injection regressions exercise the controls. Disabled-button text
and full-section mobile captures are also improved. These subsequent changes require their own
exact-head CI and independent rereview; earlier green checks do not approve newer code.
