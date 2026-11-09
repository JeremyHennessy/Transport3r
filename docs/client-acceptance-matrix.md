# Client acceptance matrix

Status vocabulary: PASS means the named scope actually passed; IMPLEMENTED means code exists
but later acceptance is pending; BLOCKED means an identified external prerequisite is absent;
NOT TESTED means no execution evidence; NOT IMPLEMENTED is not disguised as a dependency.
This is not a blanket production signoff.

| Client workflow | Current status | Evidence / next gate |
| --- | --- | --- |
| Public search and 18 existing routes | Historical route-shell PASS only | Previously retained Pages checks; source completion remains separate |
| Audited carrier source linkage | Implemented; deterministic/HTTP tests PASS locally | `warehouse-acceptance.test.mjs`, `test_integrity_api.py`; real same-cut HTTPS/UI still NOT TESTED |
| National source completeness and duplicates | BLOCKED for current acceptance | No newly accepted national source cut; preserved historical receipt is not a fresh audit |
| Live ingestion drift correction | Active independent PR #69 | Require latest exact-head comprehensive checks and review |
| Source freshness / Census recovery | Active independent PRs #67/#68 | Not treated as deployed until protected merge and hosted SHA verification |
| Date quality review flags | Local tests PASS | `test_date_plausibility.py`; real nationwide rerun NOT TESTED |
| Public-source installation/rollback | Synthetic drills PASS | `test_evidence_release.py`; actual durable host/restart/restore NOT TESTED |
| HTTPS hosting, monitoring, firewall and resource limits | BLOCKED deployment | No authorized host/DNS/billing/access integration supplied |
| Single-owner private loss review | Implemented; unit and HTTP tests PASS locally | `test_private_loss_service.py`, `test_private_loss_api.py`; initial PR-head browser PASS in run 42630237433; later changes require fresh exact-head checks |
| Original file byte-hash approval / changed-file rejection | PASS locally with synthetic data | Includes UTF-8 BOM, stale portfolio, expired/wrong-session token and explicit approval |
| Conflicting claims and policy changes | PASS locally with synthetic data | Atomic ledger rollback, identity protection, concurrent write serialization |
| Private valuation JSON export | Synthetic browser PASS on initial PR head | Byte/source/portfolio lineage; independent currencies; null/zero and historical valuations preserved |
| Private UI desktop/mobile visual checks | Initial PR-head CI PASS; images inspected | Run 42630237433 / artifact 13680785904; synthetic only, later changes need exact-head rerun |
| Windows launcher and actual Windows ACLs | Python path tests PASS; Windows execution NOT TESTED | External OS data default; legacy migration blocked rather than silent |
| Multi-user roles, SSO/MFA and tenant isolation | NOT IMPLEMENTED / NOT TESTED | Existing service remains single-owner loopback; must not be exposed as multi-tenant hosting |
| Encrypted private storage and real backup recovery | NOT TESTED on actual installation | OS/host configuration and private operator acceptance required |
| Actual insurer documents, policies and loss runs | BLOCKED acceptance | No authorized real insurer files supplied; synthetic imports are not source-document reconciliation |
| Material-change inbox | Existing local functionality | Continuous hosted operations and external delivery still NOT IMPLEMENTED / NOT TESTED |
| Full policy decision report / final client exports | Partly existing; NOT ACCEPTED end to end | Current loss JSON is a scoped valuation summary, not a complete underwriting packet |
| Reviewed corporate identity | Existing local casework | Real dated ownership acceptance and adverse-finding review remain separate |
| Geographic operating exposure | NOT ACCEPTED | State observations are not verified routes; further data, geometry and temporal intersections required |
| NOAA #60/#61 | BLOCKED publication / review | Do not bypass prior restrictions; unmatched IDs versus child-row counts unresolved |
| Numerical TRI / insurance pricing | WITHHELD | #17 research, temporal/source comparability and actuarial gates remain |
| Protected merge and public deployment of this branch | Pending | Exact-head checks, independent approval, protected merge, hosted SHA and images |
| FULL PRODUCTION ACCEPTED | NO | National data, durable hosting, security, insurer and operational acceptance are outstanding |

## Demonstration discipline

The new CI loss exercise uses explicit SYNTHETIC account/policy/claim identifiers. It creates a
policy in a temporary local workspace, previews original file bytes, rejects an unmatched USDOT,
requires approval, imports privately, checks valuation totals and downloads a summary. It does
not run a real-carrier search or turn a mock claim into a real underwriting conclusion. Run 42630237433 executed this workflow on initial PR head eb01c486. The full
search-to-carrier-to-policy-to-alert-to-report client journey remains an acceptance scenario to
execute on the approved installed environment.
