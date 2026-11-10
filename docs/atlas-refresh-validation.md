# Atlas refresh and invalid-input verification

The integrated candidate at 22683a3fb18e60674d23d687e2316faece249133
failed its synthetic browser job in workflow 42711316643 at the Atlas
invalid-input request-count assertion. The earlier rendered Atlas captures passed;
the whole workflow remains failed. Its artifact 13716555767 was downloaded and
its ZIP SHA-256 d3497be46e801439cf51bedf21455c711d2b43684737d729e35e89e421191394
and archive CRC were checked. No failed run is retroactively relabelled.

The prior test observed the first request of a refresh, then waited for a button
and a map that could still describe the previous render. That is not an explicit
request-completion boundary. The new application state records a monotonically
increasing load generation and ignores completions from superseded generations.
Invalid submission clears evidence and invalidates the current generation, so a
late successful response cannot restore a rejected carrier view.

The browser test now waits for the requested generation's completed state before
counting requests caused by invalid input. It retains the no-new-request and
no-stale-map assertions. A second scenario deliberately holds synthetic valid
responses, submits an invalid form, releases the older responses and verifies
that the invalid state remains empty. Recovery must work through ordinary valid
input. Request logs, state and screenshots are retained on a scenario failure.

A pending request for an earlier valid carrier can still finish its bounded shared
source retrieval; invalid input does not create a new source query. This change
is UI generation control, not a claim of aborting every shared network request.
Synthetic fixtures are not actual public-source acceptance or a production release.

Six deterministic reducer regressions verify refresh, stale completions, delayed
success/failure after invalidation, clearing, retry and invalid sequence rejection.
The actual built browser workflow must pass on the new exact source revision.
