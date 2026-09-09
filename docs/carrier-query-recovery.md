# Carrier table request recovery

Review of release `33690f39186c556780ca05e8f7b43e15f68e3802` reproduced a failed Retry: copying the applied-filter object did not change the serialized effect dependency, so no request was sent. Applying unchanged filters had the same defect. Reset on an already-default URL also did not refresh.

An explicit refresh counter now triggers those user actions while preserving the applied filters. Equivalent shared/legacy URLs are compared by canonical filter state. Each request owns an AbortController and cancels when superseded or when the directory unmounts. The existing current-request guard still rejects an obsolete response even if a transport ignores cancellation. Previous rows are cleared during loading; the table headline reports loading or source unavailability instead of retaining the preceding match count.

The nine-second deadline now covers the response body as well as headers. User/navigation cancellation stays distinct from a source timeout, and timers/listeners are released after completion. No automatic browser retry loop, score model, source query semantics or stylesheet change is introduced.

The CI gate `validate-carrier-recovery.mjs` serves the actual built production bundle on loopback and runs eleven Chrome checks with the repository's recorded Census fixtures. It exercises Retry, same-filter Apply, legacy-URL Apply, default Reset, cleared loading state, request cancellation, obsolete-response exclusion, invalid ranges, risk availability and navigation away. Failure responses and slow responses are browser-only fixtures, not edits to FMCSA or production data. Unit tests additionally verify pre-cancelled requests, cancellation after response headers and body timeouts.

This closes the directory recovery defect found during release review. The remaining numeric-risk gates are unchanged: unresolved source semantics, comparable observation windows, historical availability and outcome validation must be resolved before releasing a scoring model. PR #17 remains separate.
