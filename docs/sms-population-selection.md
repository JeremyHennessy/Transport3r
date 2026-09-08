# Official SMS output selection

Verified against FMCSA source metadata on September 8, 2026:

| Dataset | Published population |
| --- | --- |
| [4y6x-dmck](https://data.transportation.gov/api/views/4y6x-dmck.json) | General AB output: active interstate and intrastate hazmat carriers of property and/or passengers |
| [h9zy-gjn8](https://data.transportation.gov/api/views/h9zy-gjn8.json) | General C output: active intrastate carriers of property and/or passengers |
| [m3ry-qcip](https://data.transportation.gov/api/views/m3ry-qcip.json) | AB passenger-only output, including additional passenger percentile/alert fields |
| [h3zn-uid9](https://data.transportation.gov/api/views/h3zn-uid9.json) | C passenger-only output, including additional passenger percentile/alert fields |

The internal `smsABProperty` and `smsCProperty` aliases are retained for compatibility; those source populations are not property-only. The previous general-first selection masked the passenger-specific row even when both were present.

One shared selector now drives the official row, source identity and replay comparison. A passenger-specific row takes precedence over its overlapping general row. This is an application selection rule based on source specificity, not a claim that FMCSA prescribes application rendering priority. All four queries must finish successfully and without truncation. Each returned row must match the requested USDOT, each source must contain at most one row, and simultaneous AB/C membership or conflicting shared measure values is unresolved rather than silently selected. Reasons remain machine-readable in `officialOutputIssues`; unresolved official output does not enter comparison counts. Valid inspection-input calculations can remain available independently.

Raw output rows remain in their separate evidence slices. This does not infer current operating class from an unrelated Census cut, pool peer populations, calculate percentiles, or establish that asynchronously published input/output datasets share an exact historical cut. Temporal reconciliation remains a separate gate.

The live runtime regression now queries all four populations, including two AB and two C passenger candidates, and retains its public inputs/results as a CI artifact. The captured four-carrier passenger fixture validates source selection. For USDOT 1021580, official driver BASIC values are zero while relevant driver inspection denominators are zero; the replay remains unavailable. The validator reports those as unavailable and excludes them from numeric match counts. Nonzero official values without a replay denominator still fail the regression.

Local expanded evidence: 16 carriers, 61 numeric comparisons matching within the existing tolerance, and 3 separately reported unavailable comparisons. This bounded engineering regression is not full-population, temporal, predictive or actuarial validation.

No TSX, CSS, navigation, labels or markup changed. Passenger-specific official values flow through the existing source and field renderers. The approved visual checkpoint is still unresolved; this repair does not designate a replacement baseline or release TRI.
