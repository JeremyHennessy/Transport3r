# Transport3r

Transport3r is an FMCSA-first transportation insurance intelligence workspace. The product is designed around three deliberately separate evidence classes:

1. **OFFICIAL_FMCSA** — values published by FMCSA or DOT DataHub.
2. **TRANSPORT_CALCULATED** — deterministic calculations reproduced from public FMCSA inputs and documented methodology.
3. **TRANSPORT_MODELLED** — proprietary insurance-oriented signals, including the future Transport Risk Index (TRI).

The distinction is structural and must remain visible in the database, scoring engine, UI, exports, and monitoring alerts.

## Current product baseline

The initial GitHub Pages application provides:

- underwriting overview and material-alert surfaces;
- nationwide carrier search scaffold;
- carrier 360 / decision-summary shell;
- safety/SMS, inspections, crashes, fleet, authority, insurance and related-carrier workspaces;
- source-health view with per-dataset cadence and lineage;
- versioned SMS methodology registry;
- a source catalogue covering the principal FMCSA Open Data Program datasets;
- automated GitHub Pages build/deploy;
- automated FMCSA source probing and compact snapshot generation.

The visual language is intentionally related to TowerSignal: light analytical surfaces, navy hierarchy, restrained blue context, orange actions, dense rounded cards and strong evidence provenance. Transport3r is a separate application and does not copy NYC-specific TowerSignal domain logic.

## FMCSA source families

### Daily safety / census

- Company Census (`az4n-8mr2`)
- Crash File (`aayw-vxb3`)
- Vehicle Inspection (`fx4q-ay7w`)
- Inspection Units (`wt8s-2hbx`)
- Inspection Violations (`876r-jsdb`)
- Special Studies (`5qik-smay`)
- Inspection Citations (`qbt8-7vic`)

### Modern MOTUS operating authority / insurance

Full/history baselines:

- Motus Carrier (`inys-ebih`)
- Motus AuthHist (`yu5v-wbh6`)
- Motus Insur (`c5y8-a4uz`)
- Motus InsHist (`3uet-3z4i`)
- Motus BOC3 (`6snj-ed7q`)
- Motus RevokeSuspend (`wb4f-neki`)

Daily differences:

- Motus Carrier (`nakq-58th`)
- Motus AuthHist (`dm5j-zc6c`)
- Motus Insur (`x96h-evps`)
- Motus InsHist (`xe5s-wca7`)
- Motus RevokeSuspend (`e67p-xyd5`)

### Monthly SMS inputs

- SMS Input Census (`kjg3-diqy`)
- SMS Input Inspection (`rbkj-cgst`)
- SMS Input Crash (`4wxs-vbns`)
- SMS Input Violation (`8mt8-2mdr`)

### Monthly SMS outputs

- SMS AB Pass (`m3ry-qcip`)
- SMS C Pass (`h3zn-uid9`)
- SMS AB PassProperty (`4y6x-dmck`)
- SMS C PassProperty (`h9zy-gjn8`)

### New Entrant

- Out of Service Orders (`p2mt-9ige`)

## Data architecture

GitHub Pages remains the presentation tier. The repository does **not** attempt to commit every nationwide raw FMCSA row into Git history. Multi-million-row inspection/crash datasets would make that architecture unreliable and would destroy useful history.

Instead:

- the source registry is version controlled;
- automated runs probe source availability/schema/freshness;
- compact public snapshots are generated for the static application;
- carrier detail is designed for on-demand source retrieval during the prototype stage;
- immutable full raw snapshots and a queryable warehouse are the next persistence layer before actuarial modelling.

This keeps the Pages application deployable while preserving a path to complete national history.

## Development

```bash
npm install
npm run dev
```

Validation:

```bash
npm run typecheck
npm run build
python scripts/refresh_fmcsa.py --probe-only
```

## Deployment

`main` deploys to GitHub Pages through `.github/workflows/pages.yml`.

FMCSA source health is refreshed by `.github/workflows/refresh-fmcsa.yml` and can also be run manually.

## Methodology policy

The currently active SMS methodology and the FMCSA-approved preview methodology must be implemented as independent rulesets. A future methodology activation must never rewrite historical results.

Every calculated value must retain:

- source as-of timestamp;
- calculation timestamp;
- ruleset version;
- raw numerator/denominator inputs where applicable;
- peer group where applicable;
- evidence confidence;
- provenance classification.

## Disclaimer

Transport3r is an underwriting decision-support system. FMCSA crash records represent reported crash involvement and do not by themselves establish fault. Transport3r-calculated or modelled indicators are not official FMCSA ISS values, BASIC results, safety ratings, or legal determinations unless explicitly labelled as an official FMCSA value with source provenance.
