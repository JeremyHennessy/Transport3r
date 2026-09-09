# Empty inspection evidence and risk availability

Case: USDOT 2855794, PG TRUCKING LLC. Reviewed 2026-09-09 against production `dac356916208dd69b3da0e069931fd03d9cc6dd0`.

Direct Company Census queries return an inactive registration, MCS-150 date 2016-02-19, 92,901 power units and 110,113 drivers. Those unusual values are present in the upstream source fields; the application was not substituting another carrier's exposure. Official SAFER independently says this USDOT is inactive. The daily inspection file, SMS inspection input and SMS Census returned no rows for this USDOT. This does not establish that no inspections ever occurred. Current published source windows, inactive registration and a much older exposure report must remain distinct.

The display defect was a reassuring Summary with no derived flags despite inactive/stale exposure and no returned inspection evidence. Risk was also not explicitly represented in Summary, although no numeric Transport3r model is released for any carrier.

Shared repairs, without USDOT-specific display branches:

- Summary shows the available daily inspection-file count with the loaded row count and the distinction from SAFER's 24-month count.
- Inactive, missing-date, future-date and more-than-two-year-old Census reports receive exposure context; the raw source figures remain intact. Two years is a display review rule, not a claim about legal compliance or risk probability.
- Successful empty, unavailable and partial inspection states are separate. Empty inspections prevent a reassuring no-flags conclusion. Safety explains empty rows and links to the exact USDOT in SAFER.
- Summary explicitly displays risk-score availability and links to official SMS/replay evidence. No model or synthetic risk value is introduced.
- The mileage-year zero sentinel becomes Year unavailable in Summary, Fleet and the carrier directory. Reported mileage zero is preserved as a separate field.

Regression checks use a minimal captured PG Trucking fixture without contact fields and generic empty/failed/partial cases. A new live CI gate exercises all 36 production evidence mappings on both PG Trucking and active USDOT 3938496, validates source IDs and returned carrier/inspection-child identities, and records request failures. All-source join/normalization and four existing large-carrier checks remain required. These samples cannot certify every carrier record or historical coverage.

The user's requested UI repairs authorize these scoped additions. Existing CSS and navigation remain unchanged. PR17 stays frozen and unreleased; numeric risk and historical alignment gates remain open.
