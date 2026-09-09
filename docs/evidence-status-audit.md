# Evidence status and rejection explanations

The next missing/partial-source audit found three presentation gaps after the large-carrier repair:

- The Evidence tab's success badge counted only HTTP errors. A truncated source could therefore appear under a positive badge, and its warning panel was omitted. The tab now uses the same missing/failed/partial-source checks as other views, always renders applicable warnings and distinguishes loaded rows from a separately queried source total.
- Empty authority-history, revoke/suspend and BOC-3 panels used the same no-record text after failed or missing sources. They now distinguish an unavailable source, a partial loaded window and a successful empty query. Summary's current-authority text also separates unavailable evidence from a confirmed no-status result.
- SMS calculation guards correctly withheld rejected arithmetic, but users could not see why a comparison was rejected. The view now gives concise, deduplicated reasons for date, weight, severity, identifier, carrier identity, classification and official-output problems. Unavailable/inconsistent official output is distinct from a successful query with no applicable public row. Complete input/output issue codes remain in the replay objects and retained CI results.

No formula, time window, count, source selection, carrier report or CSS changed. A numeric mismatch without a validation error is still a numeric mismatch; the repair does not relabel it as a source failure. The warnings do not establish common monthly source alignment or historical validity. A successful empty query remains a statement about returned records, not a clean-carrier finding.

Tests execute the actual renderers and cover complete/partial/missing Evidence sweeps, failed/missing/partial/empty authority history, retained official values alongside rejected SMS date inputs, deduplicated rejection messages, failed official populations, conflicting overlapping measures and successful empty SMS output. Live deployment verification also exercises the relevant normal views and browser-only source-failure simulations. PR #17 remains separate.
