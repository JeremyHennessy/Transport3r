# TRI v0.1 research model card

This card documents the implementation at commit `7d61b32268e089fb0da090628641ef2b5f6bad0a`. It freezes observed semantics for review; it does not approve the model. No formula was altered.

| Attribute | Value |
|---|---|
| Model ID | `TRI_0_1_RESEARCH` |
| Version | `0.1` |
| Published field | `2026-09-08` |
| Implementation status | `RESEARCH_NOT_ACTUARIALLY_VALIDATED` |
| Audit disposition | Not ready for release; feature integrity and comparability defects confirmed |
| Implementation | [transportScore.ts](https://github.com/JeremyHennessy/Transport3r/blob/7d61b32268e089fb0da090628641ef2b5f6bad0a/src/transportScore.ts) |
| Target | Heuristic present observable concern; no fitted future-outcome target |
| Horizon | None |
| Population | Carriers with loaded runtime evidence; no fixed eligible modelling population |
| Training / validation periods | None established |
| Performance / calibration / subgroups | Not established |
| Insurance outcome validation | None |

## Purpose and out-of-scope uses

The stated purpose is research triage and evidence prioritization. It is not an official FMCSA safety rating, CAB formula, validated probability, expected loss, loss ratio, or insurance pricing model. Bind/decline, eligibility, premium and automated underwriting decisions are out of scope. The current audit also finds that its research output should be withheld from release until the identified integrity defects are resolved.

## Exact arithmetic

Define `WA` as the weighted mean of finite non-null components, renormalized over those that remain. Define `C(x)` as clipping to the range 0–100. The composite is `WA(SMS:0.60, events:0.20, enforcement:0.15, coverage:0.05)`, rounded to one decimal. Coverage alone cannot produce a displayed score; at least one of SMS, events or enforcement must be non-null. There is no additional minimum evidence requirement.

### SMS component

The first available output row is selected in this order: AB property, C property, AB passenger, C passenger. Five numeric percentile aliases are read and clipped. The weighted mean uses Unsafe Driving 30%, HOS 25%, Vehicle Maintenance 20%, Driver Fitness 15%, and Controlled Substances/Alcohol 10%. Missing BASICs are reweighted within this component.

Public property schemas do not contain those percentile fields, so the component is structurally absent from those rows. The first-row selection also means a property output can mask an available passenger output. No carrier-type selection rule, snapshot matching, percentile validity flag, or minimum BASIC coverage is applied by this function.

### Events component

Crash severity units per row are mutually exclusive: 4 if a fatality is reported; otherwise 2 if an injury is reported; otherwise 1 if tow-away is truthy; otherwise 0.5. With a loaded empty crash slice, crash pressure is 0. With rows and positive finite power units, it is `C(25 × severity units / power units)`. With rows and unavailable/nonpositive exposure, it is `C(8 × severity units)`. With no crash slice, it is null.

OOS pressure is `C(100 × distinct OOS inspection IDs / loaded inspections)`, provided inspection and violation slices exist and the denominator is nonzero. The actual implementation omits the real daily `out_of_service_indicator` alias. Event pressure is `WA(crash pressure:0.55, OOS pressure:0.45)`.

There is no explicit event-date window, recency weighting, peer population or truncation adjustment. The loader can retrieve 500 parents but children for 250. Missing crash severity fields default to zero before a row is assigned 0.5 residual severity units. Reported power units are a current carrier value, not aligned historical exposure.

### Enforcement component

The component is non-null if any MOTUS carrier, revoke/suspend or New Entrant slice exists, including an empty successful slice. Start at 0. Any authority status matching revoked/suspended/inactive/not-authorized/out-of-service text gives 100; pending gives at least 35. Any loaded revoke delta gives 100. Any New Entrant order row gives at least 95. Historical revoke rows give at least `min(70, 35 + 5 × count)`. Use the maximum applicable pressure, then clip.

New Entrant rescission/status dates are not evaluated. Historical orders and changed rows are not resolved into current effect. Authority classes and dispositions are not modelled individually. These are unresolved semantics, not verified current prohibitions.

### Coverage component

All rows in the MOTUS insurance slice are treated as active/pending rows. An active-file delta gives at least 35; a history delta gives at least 25; either delta without an active row gives at least 45. With active rows and no deltas, the value is 0. If the relevant sources exist but no rows are returned, coverage is null with an explanatory note. No source means null.

The normal Score route loads Summary mode, which omits the insurance-history delta. Changes are counted without adverse-direction, cancellation, replacement, filing-requirement or current-effect classification.

## Missingness, bands and confidence

Missing top-level components are reweighted. With SMS missing and events/enforcement/coverage available, effective weights become 50/37.5/12.5. With only events and enforcement, weights become 57.14/42.86. Empty successful evidence can still produce non-null zero components and a displayed 0. This is distinct from correctly retaining null when no slice exists.

Bands are: below 25 “Lower signal”; 25–44.9 “Moderate signal”; 45–64.9 “Elevated signal”; 65–79.9 “High signal”; 80–100 “Severe signal”; null “Insufficient data.” These thresholds have no measured future event-rate or actuarial interpretation.

Confidence is a deterministic checklist: 45 points times the fraction of five BASICs available; 15 each for non-null events and enforcement; 10 if coverage is non-null or has an explanatory note; 2.5 for each present power-units/drivers/mileage/MCS-150-date input; 5 for matching fleet band or 2 for unknown band; minus 5 per source error up to 20. Clip to 0–100 and round to an integer.

This percentage is not a probability or statistical confidence interval. It does not account for slice truncation, source-cut age, historical effect, subgroup validation or actual predictive uncertainty. A no-filing explanation can earn the coverage points. Textual presence earns exposure points even when parsing or plausibility is problematic.

## Hard-review flags

Separate flags cover fleet-band mismatch, MCS-150 age above 24 months, fatality-involved loaded crashes, revoke/suspend delta presence and New Entrant order history. They are not averaged away. However, MCS-150 age depends on wall-clock `new Date()` and a parser that fails for compact encodings; the model return object has no explicit observation date. A fatal-crash flag does not imply fault or insured loss.

## Hand calculations and diagnostics

These are synthetic diagnostics, not empirical carrier validation:

| Input | Hand calculation / observed output |
|---|---|
| Percentiles 80, 60, 40, 20, 0; other components 0 | SMS = 24 + 15 + 8 + 3 = 50; composite = 0.60 × 50 = 30.0 |
| Same example, SMS absent | Available zero components produce 0.0; confidence falls from 100 to 55 |
| One recognized OOS inspection, no crashes | OOS 100; event pressure 0.45 × 100 = 45 |
| Same row using actual daily source field | OOS is missed; actual implementation returns 0 |
| 250 OOS child IDs, 500 parent inspections | OOS 50; event pressure 22.5; unqueried outcomes are unknown |
| One fatal crash, 10 power units, no inspection component | Crash/event pressure = 4 / 10 × 25 = 10; old and recent crash dates yield the same result |
| Empty MOTUS carrier slice alone | Enforcement 0; displayed score 0.0 |
| Rescinded old New Entrant order alone | Enforcement and displayed score 95 |

Seventeen cases are preserved in `tri-v0.1-audit-fixtures.json`. A separate real-source example contains four OOS rows across two of three inspections for USDOT 3938496; the frozen branch's helper returns zero. Main has subsequently repaired that data binding. This historical diagnostic verifies a mapping defect without turning the sample into a validated model population.

## Validation status and required next version

No score distribution, component correlations, incremental predictive value, band separation, calibration, subgroup performance or out-of-time outcome metrics have been established. The separate 48/48 SMS measure regression does not validate this composite. The current UI's “confidence” label and “Official SMS backbone” wording need correction after the presentation baseline is resolved.

A successor needs an immutable feature schema, explicit observation/source cut, eligibility and missingness policy, complete aligned windows, order/filing lifecycle semantics, applicable official-output selection and measured subgroup coverage. Changes to these score semantics must be separately versioned. Preserve the v0.1 implementation and diagnostic outputs as an audit reference; do not silently relabel corrected values as the same model.

Change history: this card was first created for the September 8, 2026 custody audit. It documents the open PR head; it is not a production model registration.
