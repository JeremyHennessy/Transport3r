# SMS query-window consistency

The live SMS regression previously acquired carrier rows without checking whether their source datasets changed between its first and last query. A monthly refresh could therefore combine old and new inputs while still producing some matching measures.

The validator now observes each required source before querying carrier data and again after its final query. It compares the source update watermark, table identity, schema fingerprint and total source row count. Missing/failed observations, invalid identities or markers, a changed marker, and observations that do not bracket the query window fail the gate. The application runtime validator independently checks the retained lineage before accepting the sample; it does not trust a stored PASS label. A numeric replay match cannot override a failed source-cut gate.

CI retains the initial source observations even if later acquisition fails. Completed query payloads retain both observations, full metadata, query-window times, and any cut rejection reasons. Existing artifacts are not overwritten. Standalone Python validation brackets its three queried sources; the expanded application regression brackets all six sources: both SMS input datasets and all four official-output populations.

## What this establishes

`STABLE_DURING_QUERY_WINDOW` means those observed source markers remained unchanged around acquisition. This is a bounded consistency check, not a database transaction or a guarantee that no unreported upstream mutation occurred.

`monthly_alignment` remains `NOT_VERIFIED` and `snapshot_date` remains null. Upload time, schema capture time, maximum event date, and a passing numeric regression do not establish a common monthly calculation date. Existing browser views continue to load public evidence and are not certified by this CI sample as synchronized historical snapshots. No runtime formulas or app presentation changed.

## Current primary-source evidence

The [FMCSA Open Data Program](https://www.fmcsa.dot.gov/registration/fmcsa-data-dissemination-program) distinguishes the monthly input snapshot from later publication of input and output files. The [SMS help center](https://ai.fmcsa.dot.gov/SMS/HelpCenter/) describes the snapshot/release schedule as tentative. Neither supplies a file-specific historical identity that can be inferred from Socrata upload timestamps.

The [live SMS website](https://ai.fmcsa.dot.gov/SMS/) displayed a July 31, 2026 data date when checked September 8, 2026. The six portal datasets used in the regression had August 13 upload watermarks. This is useful supporting context, but it does not bind each downloaded portal artifact to that website snapshot. Exact monthly alignment remains unresolved until an authoritative file-to-snapshot mapping or archived release artifacts establish it.

Tests cover stable observations, each independent rollover marker, missing/failed/wrong-source observations, malformed or misplaced timestamps, and a full Python regression that correctly fails a simulated rollover despite 12 numeric matches. Live validation retained 16 carriers, with 61 numeric comparisons matching and three unavailable denominator cases reported separately.
