# Open-data intelligence tranche — November 10, 2026

This release exposes additional public-source review tools in Carrier 360 without converting them into insurer claims models, fraud determinations, legal-compliance certifications or private-data workflows.

## Implemented

- **W05 Related-carrier / Chameleon-style leads.** Exact Company Census registration details only: phone/cell, email, named officers, DUNS, full physical address and published prior-revocation references. Leads require analyst review and never prove fraud, evasion, ownership or corporate relationship.
- **W06 Accident and incident reporting.** Carrier Intelligence includes a combined dated timeline across inspection/crash involvement, authority lifecycle, insurance history, revoke/suspend history and New Entrant OOS evidence. Source families remain distinct.
- **W09 Regulatory compliance tracking.** Public review checks cover registration status, the FMCSA biennial schedule, current authority evidence, active/pending filing evidence, recent filing/authority changes, revoke/suspend history and New Entrant OOS records. The current FMCSA Motus transition suspension is explicit; a due date on or after June 1, 2026 is not labelled overdue by this ruleset.
- **W15 Peer benchmarking.** On demand, Company Census peers use the same country, carrier operation and fleet-size band, active status, recent MCS-150 report date and positive reported power units/drivers. Results are descriptive averages, not SMS percentiles or loss predictions.
- **W16 Recall database integration.** Verified observed VIN pages can decode NHTSA vPIC make/model/model-year and query NHTSA vehicle recall campaigns for that combination. A campaign candidate is not VIN-specific applicability, open recall status or proof of repair.
- **Source lineage.** The bundled 36-source probe/schema snapshot is refreshed to the November 10, 2026 cut from the existing source-lineage workstream.

## Existing private workflows remain private

The local authenticated workspace continues to own durable subscriptions, inbox alerts, compliance actions, analyst screening cases, reviewed relationships and private portfolio/loss information. The public Pages build does not contain those records.

## Still gated / incomplete

- W02 live GPS/ELD/vehicle-health monitoring requires authorized telemetry.
- W03 insured-claim prediction requires real claims and exposure outcomes plus out-of-time validation/calibration.
- W04 comprehensive cargo theft/shipment intelligence requires specialist or authorized data and real route/commodity exposure.
- W07 complete maintenance/repair history requires authorized maintenance records; public roadside defects and recall campaign context are not repair logs.
- W08 named driver behavior requires an authorized driver link; VIN is not driver identity.
- W10 litigation remains a qualified research lane until court coverage, access and entity matching are validated.
- W11 commercial credit/private financial health is not inferred from DUNS or public registration identifiers.
- W12/W14 durable local alerting exists, but external notification delivery/acknowledgement is a separate integration.
- W13 carrier-level natural-hazard exposure still requires verified geocodes or actual routes; headquarters/state are not route proxies.

All calculated outputs retain source/query time and limitations. Missing data remains unknown, not zero.
