# Filtered open-source carrier maps and responsive directory

## Implemented scope

The directory map uses MapLibre GL JS 6.17.0 and local Census-derived display boundaries.
It makes no third-party tile, font, geocoding or address-sharing request. The source metadata
and matching counts are requested from the same FMCSA Company Census used by the table.

The map reuses the table's applied WHERE/search filters, strips pagination and ordering,
then reconciles grouped country/state counts against the full filtered count. It checks
publisher metadata before and after acquisition, rejects repeated groups/mismatched totals,
and preserves foreign/missing geography in an explicit unlocated count. Opening the map is
opt-in; changing table page alone does not refetch all state counts. Clicking a supported
state applies the directory's existing shareable filter URL.

The carrier summary groups the loaded inspection/crash records by event state and optionally
by explicitly labelled reporting jurisdiction. Date/layer controls apply to that same loaded
evidence, not a new unrelated live date window. Missing layers, partial evidence, absent dates,
foreign carrier identities and unmapped locations remain distinct. The record list links back
to the carrier's supporting inspection/safety evidence.

## Important boundaries

The checked repository source schemas provide no validated latitude/longitude for these
Census, daily inspection or daily crash datasets. This release therefore shows **state-level
aggregates**, not exact carrier addresses, terminals, inspection sites or crash points.
Registered carrier addresses never substitute for event geometry. State symbols are placed
at display centres and do not establish routes, distance travelled, crash fault or insured
exposure. A precise-point layer still requires independently verified coordinates and a
reviewed provenance-preserving geocoding process.

Supported regional outlines: 50 U.S. states, DC and Puerto Rico. Other countries and territories
remain explicitly unmapped. Local display polygons reverse the repository's rounded 2025
Census cartographic projection. They are not analysis-quality GIS geometry, retain the original
omission of positive-longitude Alaska pieces, and must not be used for hazard intersections.
Original source and SHA remain in `src/stateBoundaries.json`.

## Table

All eleven directory fields are retained. Wide screens use flexible wrapping columns; medium
and mobile screens use labelled cards. Exposure flags and evidence links remain expandable /
clickable. The fix does not clip off-screen columns or shrink them into unreadable text.

## Failure recovery and CI

Source GET requests honour bounded Retry-After, retry only transient statuses, preserve caller
cancellation and include response-body reads in the total deadline. Evidence family requests
run with four workers rather than one large burst. CLI retries reject permanent HTTP/identity
failures and retain attempt evidence. Superseded same-PR workflows are cancelled; no real-source
acceptance check is disabled or converted into a mocked success.

Local tests cover grouped count conservation, filter scope, invalid/missing states, partial
and foreign events, date/layer controls, request deadlines, cancellation and retry policy.
`validate_open_maps_browser.py` tests the actual production MapLibre/WebGL bundle, filter/map
agreement, missing geography and all eleven fields at 1712/1280/1024/768/390px. Its source
responses are synthetic. This is not nationwide acquisition or insurer acceptance.

The local environment blocked browser navigation with ERR_BLOCKED_BY_ADMINISTRATOR. That
restriction was not bypassed; the repository's existing browser-review workflow runs the
rendered checks and retains screenshots. Until its exact-head result is inspected, browser
acceptance remains NOT VERIFIED. The initial local Python full-suite rerun also exceeded its
tool execution deadline; no all-Python-pass result is inferred from that incomplete run.


## Permanent release gate

The one-time source-application workflow and encoded change-set files are removed after
the map implementation was committed. That setup workflow correctly refused to create
files a second time, but continued triggering a misleading failure on subsequent PR runs.
The existing read-only application-review workflow now executes the production-bundle
map/table scenarios on every reviewed candidate. It does not write or push application code.

Acceptance covers a full filtered population (201 synthetic source rows versus a 100-row
table page), state selection/URL filtering, pagination independence, source failure/retry,
layer/date controls, explicit unlocated records, and all 11 table fields without horizontal
scroll at 1712, 1280, 1024, 768 and 390 pixels. Source fixtures do not certify real geocodes
or nationwide source acceptance. Regional aggregate symbols remain labelled as such.

A successful source-application run does not imply production deployment. The current
commit must pass normal checks, independent review and protected merge before Pages
release verification. No local/private records or downloaded warehouse files are included.
