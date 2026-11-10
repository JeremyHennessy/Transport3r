# Map review blockers and validation-run reliability

This change addresses PR #72 findings 4518825986, 4518825993 and 4518825998.
It does not publish a nationwide data cut, merge protected main or deploy the app.

## Corrections

Daily inspection/crash rows must contain a valid carrier identifier matching the
requested USDOT. Missing, malformed, foreign, conflicting alias values and wrong
source families do not enter mapped carrier counts. Padded identifiers may match
without changing the original source record. The shared check protects summary
maps, report maps and retained snapshot selection; the older Atlas renderer now
uses the same identity rule.

Daily event dates use the strict YYYYMMDD parser, not the generic legacy date
parser. A value such as 01022026 remains unknown and cannot pass a dated map
filter. Undated rows may remain in an explicitly unfiltered view, with the
unknown-date count visible. Source records are never rewritten to force a match.

Inspection event-state membership is checked against supported display regions.
A missing or unknown event state can fall back to a supported REPORT_STATE only
as an explicitly labelled reporting jurisdiction. The reporting toggle excludes
those records. Unknown event and reporting codes remain unlocated. Crash records
do not borrow an undocumented inspection-only REPORT_STATE fallback.

## Reproductions and tests

The new map-evidence-integrity suite ran 23 tests against the unchanged reviewed
source: 12 failed and 11 passed. Failures included all three reviewer findings and
related Atlas/alias/source-family cases. After correction, all 23 pass. The full
JavaScript suite, including five CI preservation checks, passes 405 tests.
TypeScript and production build pass. The browser script compiles and adds
unknown-state fallback and malformed daily-date cases to the actual UI test.
Exact-head browser and full-source CI must still pass before release acceptance.

## Validation-run reliability

The CI and application-review workflows are grouped by workflow, event and PR/ref.
New PR revisions cancel superseded runs in the same group; manual runs are not
cancelled by that PR policy. This prevents future overlapping acquisitions from
obsolete revisions. Runs already started without the group are not retroactively
cancelled by this configuration.

Artifact names include both the source commit and run attempt. A retry therefore
does not collide with or overwrite an earlier attempt's retained evidence. All
read-only permissions, the required real-source cohort acquisition, the original
1,000,000-row safety ceiling and fail-closed validations remain in place. No test
is changed to continue on error, skipped, or replaced with a preserved data cut.

References used for workflow semantics:
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency
- https://github.com/actions/upload-artifact

The live-source acquisition is a separate acceptance gate. Unit tests, synthetic
browser fixtures, a prior successful source cut and this document do not establish
current nationwide completeness, deployment, private installation or CAB parity.
