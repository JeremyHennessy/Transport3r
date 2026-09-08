# SMS runtime input integrity

The application continues to use SMS v3.21. The official [FMCSA methodology](https://csa.fmcsa.dot.gov/Documents/SMSMethodology.pdf), checked September 8, 2026, identifies version 3.21, methodology revised May 2026 and document revised June 2026. This repair changes input acceptance, not the arithmetic for valid records or a TRI formula.

Previously blank/invalid numeric weights became zero, duplicate inspection IDs silently replaced earlier weights, and a violation could contribute without a matching relevant inspection. These conditions can manufacture a small replay value or a misleading comparison.

The runtime now requires unique, present inspection IDs; recognized nonblank relevance flags; relevant-inspection time weights of 1, 2 or 3; a matching relevant parent for each included violation; finite nonnegative severity; and a violation time weight that agrees with its parent. Missing BASIC descriptions make classification incomplete. A malformed supplied total severity is not replaced with a guessed fallback. Where total severity is absent, the existing base-plus-OOS fallback requires its inputs; Controlled Substances/Alcohol retains its existing no-OOS-increment rule. Zero severity remains a valid numeric value.

Published inputs can omit non-affirmative relevance fields; the existing affirmative-selection rule remains in place. The live sample contains `true` text and omitted flags. This repair does not invent an affirmative relevance flag from absence.

Carrier-level replay additionally rejects input rows whose USDOT does not match the requested carrier. Invalid or incomplete input produces `PARTIAL_DATA` with null numerator, denominator, calculated measure, delta and safety-event group. Machine-readable `inputIssues` preserve the reason. Such results cannot enter match statistics. Existing display markup renders the unavailable values; no layout, labels, CSS or navigation changes are included.

The existing Python regression now optionally retains its queried inputs for `validate-sms-runtime.mjs`. CI runs those same records through the application's bundled TypeScript and fails on rejected inputs or deviations above the existing 0.015 comparison tolerance. This prevents a passing independent Python calculation from concealing a defect in the app implementation. The sample is bounded live regression evidence, not an immutable historical training cut or representative model validation population.

Local validation: nine deterministic regression cases, plus a live sample of 12 carriers, 229 SMS inspections and 320 violations, yielded 48/48 available official measure comparisons within tolerance. Valid severity capping and the Controlled Substances/Alcohol fallback remain covered by hand-calculated tests.

The existing official-output population selection, monthly cut alignment and unimplemented peer-percentile reconstruction remain separate work. This repair does not approve TRI, forecast probabilities or insurance-loss estimates.
