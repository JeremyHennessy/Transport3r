# Official SMS values in carrier summaries

The directory previously queried only Census and the carrier Summary did not render the SMS outputs it already loaded. The SMS tab also omitted passenger fields ending in `_pct` and incorrectly described every percentile as unavailable.

The directory now makes four batched official-output requests for its visible carriers. Each row shows the five published BASIC measures, with a link to the SMS tab. Summary and SMS show Unsafe Driving, HOS Compliance, Driver Fitness, Controlled Substances / Alcohol and Vehicle Maintenance. Passenger-specific percentiles accept the source's percent-suffixed format, including `0%`. Values retain source identity and retrieval time; retrieval time is not asserted to be a shared monthly source cut.

All four populations must resolve before selecting an output. Duplicate, conflicting, unrelated, failed and missing records stay distinct; missing records never become numeric zero. Refresh controls bypass earlier failed lookups. Late directory responses cannot overwrite a newer carrier selection. Official outputs remain separate from incomplete replay inputs and the unreleased TRI model. Public general output does not provide passenger-style percentiles; Hazmat and Crash Indicator values are absent from these output files.

Validation on September 9, 2026:

- 121 JavaScript and 64 Python tests passed; production build and typecheck passed.
- Eleven browser regressions cover automatic batched loading, Summary values, passenger percentiles, zeros, no-row cases, failed refreshes and stale-response isolation.
- Real FMCSA data verified in the production bundle: DOT 3706 Vehicle Maintenance 1.74; DOT 3938496 HOS 7; passenger DOT 100115 Vehicle Maintenance measure 0.69 and percentile 4; DOT 2855794 no public output row.
- Desktop directory/Summary and mobile passenger screenshots retained under `outputs/sms-display-local-ui/`. Hosted verification is recorded separately under `outputs/sms-display-live-ui/` after deployment.

No SMS formula, TRI score, historical feature or Power BI model was changed.
