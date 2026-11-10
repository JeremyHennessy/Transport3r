# Carrier directory source-freshness and timeout recovery

This follow-up preserves the current public carrier directory, map and Intelligence release while correcting two reliability states that can otherwise look healthier than the evidence supports.

## Source snapshot freshness

The bundled source-health document is a saved probe snapshot, not a live carrier-data check. A 36/36 healthy snapshot is shown as healthy only while its `generated_at` timestamp is no more than 48 hours old. The header re-evaluates freshness once per minute and when the browser tab regains focus or visibility. Invalid, future-skewed or older timestamps render a warning rather than a green health state.

This does not modify or fabricate the saved source results. It only changes how old evidence is labelled in a long-lived browser session.

## Bounded Census timeout recovery

Carrier-directory requests get exactly one fresh retry only when the first request fails with the explicit local deadline error `FMCSA request timed out`.

The retry:
- waits 350 ms;
- remains abort-aware during backoff;
- cannot issue a second request after caller cancellation;
- does not retry HTTP failures, invalid payloads, user cancellations or arbitrary exceptions;
- fails closed after a second timeout;
- surfaces `FMCSA timed out; retrying once…` while the retry is active.

No request ceiling, query filter, population definition or source validation is weakened.

## Validation

Unit regressions cover first-timeout recovery, second-timeout failure, cancellation before/during backoff, non-timeout errors and the 48-hour freshness boundary. A production-bundle browser scenario advances a saved source snapshot beyond the threshold in a long-lived tab and requires the UI to change from healthy to stale without a reload.

These checks do not establish nationwide source completeness or production uptime. They only verify recovery semantics and honest display of the saved source-health age.
