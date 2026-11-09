# Transport3r complete progress, source-connection and UI review — 2026-11-09

**Review scope:** Current protected public release `2f75f0c23a741e344667aa1a6681b1d5e0d1a1c8`; open PRs #17/#60/#61/#67; Issue #57; exact-head CI on PR #67 `3b5381cff588dc7cd6bf9e354b5996e211a2df9e`; retained browser screenshot/JSON artifact 13630178464 (36 route/viewport records). This report reviews *evidence actually available*, not a new production deployment.

## Evidence status

- PR #67: CI run 42513381367 PASS; fast/private validation 42513381143 PASS; reproducible application review 42513381210 PASS. **No independent submitted PR review, no protected merge or deployment** at inspection. Browser run verified **existing hosted main** SHA, not the PR branch's retry code.
- Earlier PR #67 browser run 42509381915: 35/36; desktop Carriers timed out, surfaced honest source-unavailable UI; retained failure artifact 13628269646. Later hosted-main 36/36 pass does **not** prove retry implementation fixed the cause.
- 25-carrier retained real cohort 20261106T210505035609Z-fcd78af6: 36 sources, 496537 original source rows (241341 inspection-child rows), 900/900 raw-to-index carrier/source count comparisons, original SHA and SQLite checks. Not nationwide acceptance.
- Last recorded refresh: 36 healthy probes, 810 fields. Probes are not carrier-query success, live service health, completeness or independent audit.
- FEMA county NRI: 3232 county records; 3144 observed scores; 88 null. Validated local index, not a hosted exposure/route product.
- Nationwide deep audit: no certified currently deployed full nationwide source-to-index-to-HTTP reconciliation. Historical 83m source rows cannot be shown as current accepted totals.
- Private insurer: #66 CLI/ledger available, but authenticated multi-tenant API/UI, private installation, insurer-file reconciliation and real outcome acceptance absent.
- NOAA #60/#61 publication explicitly blocked; distinct unmatched EVENT_ID versus orphan child-row receipt accounting unresolved. TRI #17 SMS `0%`/ `4%` parsing defect and score completeness remain blocked. Neither should be released as risk scores.

## Full visual inspection: 18 routes × desktop 1440 and mobile 390

Inspected contact sheets of all 36 screenshot PNGs from artifact 13630178464, and machine JSON per route. All records show PASS/no document overflow/runtime error. Screens inspected: overview, carriers, atlas, atlas-carrier, summary, safety, authority, evidence, portfolio, alerts, methodology, fleet, insurance, SMS, sources, inspection, VIN and integrity.

### Strengths
- Shared light interface, navy/orange accent, consistent top navigation and carrier subnavigation across evidence pages.
- Carrier context (USDOT, registration, operating class, power units/drivers) remains visible across tabs; carrier deep-link, inspection and VIN drill-down routes render.
- Atlas does not fabricate route lines; Integrity withholds unavailable nationwide audit counts; Insurance avoids unapproved numerical risk scores.
- Mobile layout reflows to narrow columns without horizontal document overflow; primary navigation and actions remain visible.

### UI issues / prioritized remediation
| Priority | Area | Observed issue | Required acceptance |
| --- | --- | --- | --- |
| P1 | Carrier data connection | Prior desktop live Census request timed out; later retry-less hosted-main pass is not proof of resilience | Add deterministic unit test for first timeout then success, repeated timeout, abort during backoff and HTTP error (no retry); test exact PR bundle in browser before merge; preserve unavailable/Retry after final failure |
| P1 | Carrier evidence tabs | Several mobile screenshots capture `Loading complete carrier evidence` or `Loading carrier map` in the first viewport even though the page passes | Add post-load screenshot assertion/wait for source settled, including explicit unavailable state, for key carrier tabs; don't confuse loaded route shell with complete evidence |
| P1 | Integrity | Unavailable nationwide service is correctly disclosed but cards remain largely empty | Keep UNKNOWN (not zero); show last accepted cut, source-vs-API status and reason/next action when available; never fabricate completeness |
| P1 | Atlas | Base atlas has empty source-state sections; carrier map is source-evidence context, not route exposure | Improve explicit no-data/unknown labels; do not render implied driven routes, hazard grades or carrier-attributed county NRI |
| P2 | Mobile carrier tabs | Repeated large carrier identity header and two-row tab navigation consume substantial initial viewport | Consider compact sticky identity summary and collapsed metadata *after* accessibility/interaction testing; preserve USDOT and source context |
| P2 | Carriers | Large filters push table below first desktop viewport; mobile filters occupy several screens | Add optional collapsed advanced filters and visible applied-filter summary, retaining shareable hash and accessible keyboard controls |
| P2 | Portfolio/Alerts | Public entry screens emphasize local-only workspace and setup rather than a populated underwriting workflow | Clarify private-local versus public-source capability; don't suggest insurer records sync or cloud storage |
| P2 | Source freshness | Header health indicator reflects a saved probe snapshot, not live Census health | Preserve snapshot label and separately show live query status/time; avoid green=production-ready |
| P3 | Visual density | Repeated pale cards and explanatory paragraphs lower scan speed | Tighten secondary copy, strengthen heading hierarchy and prioritize a single evidence-state summary; keep disclaimers accessible |

These are review findings, **not fixes already deployed**. Captures do not validate hover/focus, screen-reader behavior, contrast ratios, real private user sessions, full data accuracy or live production source acceptance.

## Data/connection matrix

| Connection | Current evidence | Missing before production claim |
| --- | --- | --- |
| FMCSA public Socrata Company Census | Live UI reads source; one timed-out request observed, later successful screenshot | Retry/cancellation tests, upstream latency telemetry, stable read-only index fallback with accepted cut |
| 36 FMCSA sources | Source schema and probes; 25-carrier real sample fully reconciled | Nationwide full original-source cut, deep audit, independently reproducible receipt, complete carrier coverage |
| Public-source evidence API | Loopback-only install reference, not a live durable deployment | Approved host, TLS/access/rate/monitoring, exact source SHA, HTTP-to-SQL-to-UI reconciliation, rollback rehearsal |
| FEMA county NRI | Accepted local source/index with 88 nulls | Durable serving, validated point/polygon geometry, source vintage and actual insured location |
| NOAA Storm Events | PR #60/#61 research and historical CI | Correct unmatched EVENT_ID versus child-row accounting; separate source acceptance; publication remains blocked |
| FMCSA SMS/TRI | Official evidence visible; TRI #17 draft | Percent-format parsing, completeness, peer population, uncertainty, claims outcome and model review |
| Private claims | Offline #66 importer and synthetic tests | Authenticated scoped UI/API, approved private host, tenant isolation, actual insurer sample and independent reconciliation |

## Safe execution order

1. Independently review PR #67 retry implementation; add deterministic timeout/abort/no-retry tests; verify exact-head CI and browser using **PR bundle**. Do not merge without independent approval.
2. Improve browser test to distinguish route-shell PASS from carrier evidence settled/UNKNOWN. Review mobile accessibility and key screenshot states.
3. Complete full nationwide original-source deep audit only via authorized acquisition path; preserve blocked workflows and historical failures.
4. Authorize and install secure, durable, public-source read-only API; reconcile accepted warehouse and HTTP/UI counts and hashes.
5. Build and security-review private claims API/UI on top of #66, preserving separate tenancy and immutable claim identity; require actual insurer acceptance.
6. Resolve #60/#61 and #17 blockers before any NOAA publication, risk score or hazard coloring. Keep unknown as unknown.
7. After independent reviews and approved merge, confirm Pages deploy SHA, all 36 browser checks, screenshot hashes and visible data-state labels. Update Issue #57 with actual outcomes, not expected outcomes.

**Release conclusion:** Public UI is functional and visually coherent but not a complete connected nationwide insurance platform. No full-production claim is supported yet.
