# Transport3r

Transport3r is an FMCSA-first transportation insurance intelligence workspace. It is designed to help an underwriter or risk analyst answer six distinct questions about a carrier: who the carrier is, what exposure it reports, what safety events have occurred, whether authority and insurance are continuous, what changed recently, and which published safety measures can be reproduced deterministically before any proprietary insurance model is introduced.

The product keeps three evidence classes structurally separate:

1. **OFFICIAL_FMCSA** — values and records published by FMCSA or DOT DataHub.
2. **TRANSPORT_CALCULATED** — deterministic calculations reproduced from public FMCSA inputs and a versioned methodology.
3. **TRANSPORT_MODELLED** — proprietary insurance-oriented signals, including the future Transport Risk Index (TRI).

That distinction must remain visible in the data model, calculations, UI, exports and monitoring. A calculated or modelled value must never be presented as an official FMCSA determination.

## Current product workflow

The application is organized around six global workspaces:

- **Overview** — maps each public-data family to its underwriting purpose and shows source/schema health without depending on a live FMCSA request.
- **Carriers** — a filterable nationwide Company Census table with shareable URL filters and direct Carrier 360 evidence links.
- **Portfolio** — the boundary for insurer-owned policy/exposure data and future durable monitoring. Public FMCSA data is not fabricated into a portfolio.
- **Alerts** — the material-change contract for OOS, authority, insurance, crashes, violations, fleet/mileage and SMS movement.
- **Methodology** — the versioned separation between official outputs, deterministic replay and future proprietary modelling.
- **Data Sources** — all configured FMCSA/DOT datasets with purpose, scope, cadence, source health and schema lineage.

Each carrier has a shareable Carrier 360 with:

- **Summary** — identity/exposure, loaded safety evidence, authority/enforcement, insurance continuity and recent MOTUS changes.
- **Safety** — inspections, violations, OOS evidence, citations, Special Studies and crash involvement.
- **Fleet** — vehicles observed in FMCSA inspections using the verified `INSP_UNIT_*` fields. Observed VINs do not prove current ownership or an insured vehicle schedule.
- **Authority** — current/history MOTUS authority, BOC-3, revoke/suspend history, daily differences and New Entrant OOS evidence.
- **Insurance** — active/pending filings, insurance history and daily filing/history differences.
- **SMS** — monthly SMS inputs, applicable official passenger/property output and Transport v3.21 measure replay.
- **Evidence** — the intentionally broad all-source lineage sweep.

## Data → underwriting purpose

### Identity and reported exposure

**Company Census (`az4n-8mr2`)** is the USDOT spine. It supplies legal/DBA identity, physical location, operation class, hazmat indicator, power units, drivers, MCS-150 mileage and other carrier-reported census attributes. It is used for entity resolution and exposure context, not as proof of an insured schedule.

### Daily safety and roadside evidence

- **Crash File (`aayw-vxb3`)** — reportable commercial-motor-vehicle crash involvement and severity context. Crash involvement does not establish fault.
- **Vehicle Inspection (`fx4q-ay7w`)** — inspection events, dates, levels, locations and aggregate violation context.
- **Inspections Per Unit (`wt8s-2hbx`)** — VIN, make, plate, unit and other vehicle observations tied to an inspection.
- **Vehicle Inspections and Violations (`876r-jsdb`)** — violation code/category, unit and OOS evidence.
- **Special Studies (`5qik-smay`)** — Level IV/special-study observations when present.
- **Inspections and Citations (`qbt8-7vic`)** — citation evidence attached to inspection events.

These sources support loss-control review and event-level drillthrough rather than a single opaque score.

### Authority and insurance continuity

Modern MOTUS full/history datasets provide the legal and filing baseline:

- **Carrier (`inys-ebih`)** — USDOT/docket authority profile and status.
- **AuthHist (`yu5v-wbh6`)** — authority lifecycle/history.
- **Insurance (`c5y8-a4uz`)** — active/pending policy filings, insurer, type, limit and dates.
- **Insurance History (`3uet-3z4i`)** — cancellation/replacement/change history.
- **BOC-3 (`6snj-ed7q`)** — blanket process-agent/administrative evidence.
- **RevokeSuspend (`wb4f-neki`)** — suspension/revocation orders and dates.

The corresponding 24-hour MOTUS difference feeds isolate what changed recently instead of burying new events inside static history:

- Carrier `nakq-58th`
- AuthHist `dm5j-zc6c`
- Insurance `x96h-evps`
- Insurance History `xe5s-wca7`
- RevokeSuspend `e67p-xyd5`

These difference feeds are the event layer for future insured-carrier monitoring.

### Monthly SMS calculation and validation

The current monthly input snapshot is separated from daily operational data:

- Motor Carrier Census `kjg3-diqy`
- Inspection Data `rbkj-cgst`
- Crash Data `4wxs-vbns`
- Violation Data `8mt8-2mdr`

Transport3r reproduces inspection-based SMS v3.21 measures from these inputs and validates the result against the applicable official output family:

- AB Pass `m3ry-qcip`
- C Pass `h3zn-uid9`
- AB PassProperty `4y6x-dmck`
- C PassProperty `h9zy-gjn8`

The replay layer is **TRANSPORT_CALCULATED**. Official output remains **OFFICIAL_FMCSA**. Property percentiles and TRI remain blocked until the full peer-population reconstruction and later actuarial validation are defensible.

### Enforcement

**New Entrant Out of Service Orders (`p2mt-9ige`)** are surfaced as a material hard-review fact independent of a composite score. A historical row is not automatically interpreted as a current operating prohibition; effective/current status must be read from the underlying record.

## Runtime architecture

GitHub Pages is the presentation tier. Nationwide multi-million-row FMCSA datasets are not committed to Git history. Instead, the repository persists source/schema/health metadata and retrieves carrier evidence on demand.

The browser runtime deliberately limits public DataHub dependency:

- Overview, Methodology, Portfolio, Alerts and Data Sources use repository-hosted application/static metadata and do not require a broad live carrier sweep.
- The Carriers table makes one Company Census request per table refresh.
- Carrier 360 loads **only the source family needed by the selected tab** and caches successful carrier/source slices during the session.
- Direct browser DataHub requests have a finite timeout and source failures are contained; unavailable evidence is never converted into a zero-risk value.
- Inspection-child joins use a capped recent inspection-ID window and mark partial windows as such.
- Only the explicit Carrier 360 **Evidence** tab performs the broad all-27-source sweep.
- A top-level React error boundary provides a recovery surface instead of a blank page if an unexpected render failure occurs.

This architecture keeps the static application responsive while preserving a path to a durable queryable warehouse and immutable historical snapshots before actuarial modelling.

## Source health and validation

`public/data/source-health.json` and `public/data/source-schemas.json` are generated snapshots used by the UI to expose source availability, freshness and field contracts.

CI gates include:

- TypeScript typecheck;
- production Vite build;
- Python entrypoint compilation;
- live query-shape validation across all 27 configured FMCSA datasets, including the inspection-child joins and fleet field contract;
- a live carrier-directory filter/sort query;
- SMS v3.21 measure replay regression against official FMCSA output.

A green build is necessary but not by itself proof that a hosted UI is visually correct; deployment and hosted/runtime verification remain separate release gates.

## Development

```bash
npm install
npm run dev
```

Validation:

```bash
npm run typecheck
npm run build
python scripts/smoke_carrier_queries.py
python scripts/validate_sms_v321_replay.py
```

## Deployment

`main` deploys to GitHub Pages through `.github/workflows/pages.yml`.

FMCSA source health is refreshed by `.github/workflows/refresh-fmcsa.yml` and can also be run manually.

## Methodology policy

The currently active SMS methodology and any FMCSA-approved future methodology must be implemented as independent rulesets. A future methodology activation must never rewrite historical results.

Every calculated value must retain, where applicable:

- source as-of timestamp;
- calculation timestamp;
- ruleset version;
- raw numerator/denominator inputs;
- peer group;
- evidence confidence;
- provenance classification.

## Disclaimer

Transport3r is an underwriting decision-support system. FMCSA crash records represent reported crash involvement and do not by themselves establish fault. Transport3r-calculated or modelled indicators are not official FMCSA ISS values, BASIC results, safety ratings, legal determinations or insurance decisions unless explicitly labelled as an official FMCSA value with source provenance.
