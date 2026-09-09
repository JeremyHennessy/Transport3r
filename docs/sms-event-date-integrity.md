# SMS event dates and possible window gaps

The replay now rejects missing or invalid `INSP_DATE` values in either SMS input source and conflicting event dates on an inspection and its linked violation. These records previously could produce a numeric match because arithmetic checked their published time weights but not their dates. A date integrity failure now produces `PARTIAL_DATA`, null arithmetic and no match/mismatch statistic. It does not relabel the failure as a numeric mismatch.

The check uses the existing strict calendar parser. Equivalent supported representations compare as the same source calendar day, including ISO representations with a timezone offset. It does not use the viewer's timezone. The runtime regression retains valid-date counts and earliest/latest event dates for each carrier's inspection and violation rows, together with explicit date issues.

## Interpreting gaps

- An interval without an inspection is not itself evidence of lost rows. Sparse but valid event histories remain eligible for replay.
- An inspection date, a portal upload watermark, a query capture time and an SMS calculation snapshot date describe different things.
- A changed source marker during acquisition fails the existing [query-window gate](sms-query-cut-consistency.md). Stable markers and matching parent dates still do not prove that all sources belong to one monthly snapshot.
- The replay retains the published `TIME_WEIGHT`. It does not reweight or discard rows relative to today's date, the latest event, or an assumed month end.
- Exact monthly alignment remains `NOT_VERIFIED`, with no inferred snapshot date. A date discrepancy is evidence of inconsistent inputs; its upstream cause still requires investigation.

The [FMCSA data dissemination program](https://www.fmcsa.dot.gov/registration/fmcsa-data-dissemination-program) describes monthly SMS input snapshots and later output publication. That publication lag makes source alignment a reasonable hypothesis when measures disagree, but it is not proof of the cause for a particular carrier.

## Verification

Regression cases cover missing/invalid dates in each source, conflicting parent/child dates despite identical weights, calendar equivalence across source formats and offsets, leap days, sparse histories and successful empty inputs. Date failures cannot enter comparison statistics. The existing passenger and no-denominator fixtures retain their expected behavior.

The retained September 9, 2026 UTC sample has 16 carriers, 61 matching numeric comparisons and three unavailable denominator cases. All input dates parse and all linked dates agree. No observed numeric mismatch in that sample is explained by a date gap. This sample is an engineering check, not full-population validation. Browser presentation, labels and CSS are unchanged.
