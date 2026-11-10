# Transport3r — independent engineering, data and UI readiness assessment

**Reviewed:** 2026-11-09. **Decision:** Transport3r is an increasingly capable public FMCSA research/prospecting application and a prototype local insurance workbench. It is **not yet a verified nationwide, continuously served or insurer-accepted underwriting production system**. Do not equate a green route smoke test, a healthy source probe, a cohort receipt, and production evidence acceptance.

## What was actually inspected

- Protected public main as verified by GitHub Pages: \`2f75f0c23a741e344667aa1a6681b1d5e0d1a1c8\`. Screenshots/HTML/JSON from run 42513381210, artifact 13630178464, ZIP SHA-256 \`b433c4754db67001d68302df1664e779134496ed954aeecc8c750ba16a5a5159\`.
- All **18 named routes at 1440px and 390px**: overview, carriers, atlas, atlas-carrier, summary, safety, authority, evidence, portfolio, alerts, methodology, fleet, insurance, SMS, sources, inspection, VIN, integrity. Inspected 36 browser records, route HTML and representative full/section screenshots.
- Existing CI app-review source archive and pinned node_modules; locally executed **222 Node tests, all passed**, TypeScript typecheck and a production build after the working-tree reliability changes. The local repository was reconstructed from a CI archive and has a temporary local Git SHA; this is **not** an exact-head GitHub approval or hosted deployment.
- Source mapping, completeness loader, insurance-line model, live Census directory, source health badge, private server security boundaries, Integrity API and corresponding browser/unit checks.
- Master Issue #57, historical open PRs #17/#60/#61, PR #67 and the newly opened snapshot PR #68. Reviewed Codex's specific P2 comment on #67 rather than treating a COMMENTED review as approval.
- Relevant original product requirements: DOT/name/region search, FMCSA/CSA/ISS trends, insurance filing continuity, corporate ownership/fraud leads, weather/road/fleet maps, monitoring, portfolio/reports, cargo and insurer exposure. The last five require additional evidence, not decorative pages.

## Evidence acceptance ladder (do not collapse these stages)

| Layer | Verified today | Not proved |
| --- | --- | --- |
| Static UI/navigation | 36/36 existing-hosted route/viewport shell checks; no page overflow/runtime error on captured view | Full interactive accessibility, all source requests settled, all button actions and data accuracy |
| Source probe metadata | 36/36 saved source probes; same 36 IDs and 810 fields in Oct 23 and Nov 8 snapshots | Health of each live carrier request, full original-row acceptance, complete nationality/population coverage |
| Retained real cohort | 20261106T210505035609Z-fcd78af6: 25 carriers, 36 source IDs, 496,537 original rows including 241,341 inspection-child rows, 900/900 raw-to-index comparisons, accepted SHA and SQLite checks | All-carrier or all-years source completeness, uniform SMS vintage, unique incidents across different grains |
| Historical nationwide baseline | Earlier Oct 23 cut and counts retained as historical evidence | A **fresh**, independently certified nationwide deep duplicate/orphan/fanout audit, installed immutable cut and HTTP/UI reconciliation |
| Geographical community data | FEMA NRI county: 3,232 records, 3,144 scores, 88 unknown; local index verified | Hosted index, facility/terminal geocodes, actually traveled routes or carrier-attributed natural-hazard exposure |
| Private insurance workbench | Single-owner loopback session controls, local policy/review/checklist functions; offline loss-history CLI with synthetic tests | Authenticated multi-user tenant authorization, real insurer files and source documents, claims review UI/API, production installation and actuarial outcome acceptance |

These are not additive row populations. In particular, 496,537 source records are not 496,537 unique incidents or insured losses.

## Confirmed P1 — the browser gate was overstating source readiness

**Reproduction from retained HTML, not inference:** 7 of 18 desktop route captures and 7 of 18 mobile route captures contained the heading \`Loading complete carrier evidence\` and **none** of those 14 captures showed \`Complete carrier evidence loaded\`. All 36 route records still reported PASS. Specifically, desktop and mobile summary/safety/authority/evidence/fleet/insurance/SMS views commonly showed the sweep pending.

**Why this matters:** \`scripts/verify_live_ui.py\` waits for a few headings and preview components, not the completion of the parallel 36-source loader or an immutable warehouse receipt. The 36/36 PASS means **routing and visible preview rendered**, not 36/36 sources loaded for those carriers. A headline such as “0 source requests partial or unavailable” applies only to the selected preview scope and should never be read as a full-warehouse count.

**Change proposed on #67:** each route record now explicitly says \`ROUTE_SHELL_AND_VISIBLE_PREVIEW_ONLY\` / \`full_source_reconciliation: NOT_TESTED\`; if the 36-source component is present, the JSON captures whether it was loading, incomplete or merely UI-reported complete. This is an *honest test-scope fix*, **not** a completed end-to-end evidence audit.

**Release acceptance:** deterministic settled-vs-error browser cases, exact-head PR build and new hosted capture, and real source→index→HTTP→UI reconciliation on an accepted nationwide cut.

## Confirmed P1 — a green source badge can reflect old observations

- The public main \`public/data/source-health.json\` was generated **2026-10-23 18:52:08Z** and reports 36 healthy probes.
- The existing refresh branch \`data/fmcsa-source-lineage\` contains an official-source probe snapshot from **2026-11-08 21:18:08Z**.
- Direct comparison: the branch is one commit ahead/zero behind main and changes only the two public source metadata JSON files; source IDs and field-name arrays remain identical, with **36 sources/810 fields** in both cuts. Branch refresh does not mean live carrier queries cannot time out.
- The previous top-bar green state checked \`healthy === 36\` but **not snapshot age**. At review time this displayed ~17-day-old observations as visually healthy.
- **PR #68** proposes the newer saved metadata. **PR #67** now downgrades a snapshot older than 48 hours to a visibly stale warning even when every old probe passed. The badge still explicitly says “snapshot”, not live connectivity.

**Release acceptance:** exact-head checks and protected merge of each PR, Pages hosted SHA verification, and monitoring that identifies when automated refresh creates a branch but cannot open a PR (prior Actions token 403). A nightly probe without publication is not a public freshness update.

## Confirmed P2 reviewer defect — automatic Census retry was undocumented and untested

- Live Carriers requests use a 9-second deadline. The earlier hosted browser run 42509381915 failed desktop Carriers (35/36 overall), with a visible FMCSA timeout; later hosted-main browser review passed 36/36.
- #67 introduced one additional attempt after a 350 ms backoff; two timeouts can mean **~18.35 seconds** until error. Independent Codex P2 correctly pointed out that the PR still said documentation-only, \`docs/carrier-query-recovery.md\` said no retry, and no tests exercised the new path.
- On #67, the retry has been isolated into a cancellation-safe helper, the UI explicitly displays “FMCSA timed out; retrying once…”, and **five deterministic regressions** now cover success after timeout, repeated timeout, HTTP/schema/AbortError no-retry, abort during backoff and aborted caller. Recovery documentation and PR scope now disclose worst-case latency. Existing-source failure remains visible after retry and no historical/cache data is substituted.
- Locally the modified branch snapshot passed 222 Node tests, TS typecheck and production build. **Exact final PR-head GitHub checks and independent rereview are required.**

## UI review: actual observed value, not just visual polish

| Surface | What works visually | Precise weakness / recommendation |
| --- | --- | --- |
| Overview | Strong legibility and coherent hierarchy | Avoid product-feature impression that full insurer pricing, monitoring or predictive risk already exists |
| Carriers | Useful 100-row source-paged table, filters, shareable URLs and reported exposure context | Filters consume most of desktop first viewport; hide optional advanced filters while preserving hash/shareability. A risk-score availability control returns empty because no score exists: explicitly disable it or retain an unambiguous “not released” explanation |
| Carrier 360 tabs | Consistent identity, source links and drilldowns | Huge repeated identity/header/exposure stack; on 390px, evidence often below the fold. Compact identity on subsequent tabs; retain USDOT and source/as-of dates |
| Safety, SMS, Insurance | Separate official output, calculated replay and insurer decision-support context; no fictional numerical risk model | Full sweep often pending at capture; call out preview vs accepted full cut next to counts. Filing absence in a bounded request is not effective coverage/absence |
| Atlas | Useful observed state-level inspection/crash footprint; avoids invented routes | Cannot support facility/terminal/route proximity insurance pricing. Keep map legend “reported jurisdiction, not actual route”; defer colored natural hazard scores |
| Portfolio and Alerts | Local operator workflows and audit provenance exist | Public screen is an entry point, not a production multi-user insurer portfolio or live monitoring service. Explain private-local vs public context once, avoid repeated setup cards |
| Data Integrity | Correctly withholds unverified nationwide totals and duplicates | Mainly dashes because no accepted nationwide API. Provide last accepted cut, last probe time and action/status separately instead of making every unknown appear like a measurement |
| Mobile | No page-level overflow in captured routes, nav remains usable | Above-the-fold space dominated by header, pills, metrics and navigation. Put the underwriting decision/evidence state earlier; collapse secondary metadata but not source caveats |

**Specific numeric warning:** the desktop Carriers screenshot displays **3,026,698 reported power units vs 1,013 reported drivers across the current 100-row page**. These are independently summed reported fields from a fleet-band sort, not a verified coherent fleet/exposure portfolio. Do not compute a fleet ratio or insurer rate from them without completeness, outlier and same-report-date checks. This discrepancy is a *review flag*, not a verified source corruption finding.

## Technical root cause: three incompatible loading/identity horizons

1. **Directory:** one live Socrata Company Census query against \`az4n-8mr2\` with 100-row page + lookahead, per-request timeout and page-level controls.
2. **Preview:** mode-specific bounded FMCSA/MOTUS/SMS source requests; their row counts can legitimately be zero or partial and are from mixed publisher vintages. There is no guaranteed same-month source cut.
3. **Complete carrier sweep:** attempted 36-source browser acquisition; identity contract has 24 direct USDOT, 7 legacy USDOT, 4 inspection-parent and 1 docket-bridge mappings. Multi-page live acquisition, metadata-before/after checks and up to three retries per request do not produce an independently immutable nationwide release. The 36-source browser sweep cannot replace a warehouse audit and can take considerable time under rate limits.

**Recommended target architecture:** retained publisher bytes and SHA → typed source identity/row-grain validation → independent nationwide deep audit/receipt → immutable read-only DB/index → authorized HTTPS evidence API with the **same release/cut/SHA** → browser previews, provenance and explicit UNKNOWN states. Background refresh must atomically publish a new cut or preserve the last accepted one; no silent swap or fabricated zero.

## Insurance and product gap against the original brief

| Originally requested | Current status | Acceptable next milestone |
| --- | --- | --- |
| DOT/name/geography search and detailed safety | Available in public research UI | Add source-settled browser and identity tests |
| CSA/SMS/ISS benchmarking and historical trend | Official/replay foundations; exact population/month and ISS rules not fully accepted | Freeze same-release peer windows and prove denominator comparability |
| Insurance filings, cancellation/reinstatement monitoring | MOTUS current/history/delta views and local alerts, **not** verified coverage or a continuously served monitoring product | Dated filing lifecycle, coverage unit interpretation, policy comparison and notification operations |
| Underwriting portfolios, claim history and client reporting | Local single-owner workbench and loss importer; reports exist | Authenticated tenant-scoped review/claim UI, private audited source acceptance, report with traceable dates and policy decision record |
| Parent groups, fraud and cargo/theft exposures | Investigation concepts, not validated adverse fraud/claims conclusions | Source-attributed ownership edges and exact case/shipment corroboration |
| Weather, roads, locations, risk hexes and route exposure | State observation Atlas, FEMA county source only | Independently geocoded terminals and actual trip/route geometry with temporal hazard intersections |
| Calculated insurer risk / TRI | Withheld draft #17 | Fix official SMS \`0%\`/\`4%\` parsing and data completeness, then independent outcome/actuarial validation |
| NOAA Storm Events overlays | #60/#61 behind review/publication block | Resolve distinct unmatched EVENT_ID versus orphan child-row accounting and receive authorization before publication |

## Open PR disposition and protected release sequence

- **#17 (draft):** official SMS percent-string bug makes TRI numeric result unreliable; no release. Keep numerical TRI and insurer pricing hidden.
- **#60 and #61:** NOAA source/API/FEMA integrations require independent review and explicitly blocked publication; do not bypass.
- **#67 (open, ready):** production and UI acceptance documentation, live Census timeout recovery, 48h source-health warning, 6 targeted tests and explicit route smoke scope; **do not merge until independent finding reviewed and exact-head checks pass**.
- **#68 (open, ready):** narrowly scoped Nov 8 public source metadata refresh; checks/review/Pages verification required before describing as deployed.

### Recommended execution order

1. Finish and independently rereview #67; validate the actual PR build, 6 new regression tests, error states, 36 desktop/mobile route shells, and classify source-sweep states separately.
2. Validate and release #68 only under normal branch protections; watch the public header change with current metadata, and fix the Actions 403 auto-PR publication process.
3. Freeze an approved full nationwide source cut; independent original-row duplicates, orphan links and join fanout audit plus source/DB/HTTP/UI conservation. Do not resume previously blocked acquisition/publishing operations without authorization.
4. Deploy an authorized, durable read-only public evidence service with provenance, monitoring, access/rate policy, exact SHA matching, backup and rollback.
5. Implement private authenticated insurer claims/portfolio workflow on #66 with per-tenant authorization, review approval, encrypted persistence and actual source-document acceptance.
6. Only then add real route/facility hazard joins and actuarially validated model work. Keep unsupported scores, fraud labels and carrier-route inferences suppressed.

## Definition of done

A user should be able to choose a carrier and policy, see the exact accepted data cut, locate original source identities and publication dates, distinguish zero from missing/partial, load the complete source coverage from a stable service, review claims/documents within an authorized private tenant, receive reproducible alerts, and export an auditable insurer decision record. The release must survive CI, independent review, private security QA, same-SHA hosted browser checks, failure/restore drills and real acceptance evidence.

**No current green screenshot, saved probe, source fixture or open PR establishes all of those conditions.**
