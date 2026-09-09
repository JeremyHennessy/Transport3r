# Data review and UI clarity

Reviewed against main / deployed `033ff56c87a0ba4e338b9b2aa1dc5c56da3a0358` on 2026-09-09 UTC. The current user explicitly requested UI fixes and additions. The historical `25157fb` checkpoint still does not resolve; the recorded current production screenshot is the before comparison, not a substitute approval record. These changes use existing components and styles, with a scoped mobile navigation fix. PR #17 remains open at `7d61b32268e089fb0da090628641ef2b5f6bad0a`.

## Confirmed defects and repairs

- Overview advertised 27 sources and only five MOTUS deltas. Registry-derived counts now reconcile: seven Census/safety/inspection, 20 authority/insurance including six deltas and eight archives, eight SMS, one enforcement.
- Saved probe results looked current, and missing snapshot data could show zero failed probes. Health is derived from configured per-source records; absent snapshots/counts remain unavailable. Check times, source update metadata and carrier report dates are distinct. The newest metadata timestamp is no longer labelled a daily-only update.
- Missing/invalid carrier power units contributed zero to the summary. Exposure totals now retain reported-zero values and disclose known-row coverage for partial totals. Entirely missing values and failed requests display unavailable. Reported-driver totals are also available.
- MCS-150 report dates were only in a hover tooltip. They now appear in directory rows. Registration can be filtered at the source before the row limit; it describes a USDOT registration, not an entire corporate group or operating authority.
- Sources now support search and probe-status filters, direct official dataset links, saved check times and error details. Missing probes remain visible in the all-source denominator.
- Mobile navigation previously hid later destinations in a narrow scrolling area. All destinations now wrap visibly. Carrier and source tables have keyboard-focusable scroll regions; the directory explains horizontal scrolling and differing report dates.
- The shared source request timeout ended after headers, leaving body parsing unbounded. It now covers JSON reads, including schema and health metadata. Failed/malformed responses remain errors.
- SMS copy no longer claims current files are proven to share one monthly cut. The common-month gate remains unverified.

## Validation scope

All 36 live metadata/sample probes passed (810 registered fields). Source registry alignment and the live data-contract check passed across the registered sources. These are schema, join and sampled field validations, not a certification of every upstream record, historical completeness or comparable time windows.

Six additional unit tests cover exposure missingness/zero/overflow, source-family reconciliation, missing snapshot versus measured failures, registration query validation, response-body deadlines and malformed/HTTP error handling. Ten additional production-bundle browser checks exercise missing exposure, failed data requests, registration queries, visible dates, source search/status/error presentation and registry totals. These complement the eleven existing recovery scenarios and existing live large-fleet/SMS gates.

Local desktop and 390px mobile checks use live Census data. The three Arkansas examples report 59,121 drivers and 56,531 power units in the loaded slice, with per-carrier report dates displayed. Synthetic missing-field/source-failure fixtures are restricted to the browser test harness and explicitly marked as simulations.

Remaining gates: historical source alignment, unresolved MOTUS filing semantics, comparable model features and validated outcomes. No numeric TRI, peer percentile, forecast or insurance-loss model is released.
