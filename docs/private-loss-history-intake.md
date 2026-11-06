# Private loss-history intake foundation

This is a **local operator CLI and tested storage module**, not a public endpoint, automatic loss-run extractor, claims adjudication tool, actuarial model or approved multi-tenant service. It is not yet connected to the private browser UI. No actual insurer records have been supplied for acceptance.

## Boundaries

Keep the input, existing workspace portfolio and new `loss-history.sqlite` outside the repository, `public` and `dist`. The command makes no network requests and uploads nothing. A new database has owner-only POSIX permissions (0600); existing group/world-accessible databases are rejected on POSIX. OS account access, Windows ACLs, encryption, backup, retention and operational authorization remain deployment responsibilities. This CLI does not reuse browser login sessions: it is restricted by access to the private files on the operator's machine.

## Explicit normalized input

Use UTF-8 JSON, at most 2 MB and 5,000 nonempty claim observations. The top-level fields must be exactly:

| Field | Required meaning |
|---|---|
| `schema` | `PRIVATE_LOSS_HISTORY_1` |
| `source_id` | Stable, reviewed insurer/source namespace; not a carrier name |
| `document_reference` | Private source reference; do not put credentials in it |
| `valuation_date` | Actual YYYY-MM-DD valuation date, not a future date |
| `permission_confirmed` | Explicit `true` only when the operator has permission to process these records |
| `amount_basis` | `GROSS_INDEMNITY_EXCLUDING_EXPENSES_AND_RECOVERIES` |
| `claims` | Nonempty array of the observations below |

Each observation must supply exactly `claim_id`, `account_id`, `policy_id`, `dot_number`, `coverage_line`, `loss_date`, `reported_date`, `status`, `currency`, `paid_minor` and `outstanding_minor`.

Account/policy IDs must match the saved portfolio **exactly**, including meaningful whitespace; USDOT must match that saved policy. No name matching, fuzzy matching or ownership inference is performed. Use the app's existing eight coverage-line identifiers. Supported reported statuses are `open`, `closed` and `reopened`.

Dates satisfy loss <= reported <= valuation. The initial screening supports a loss within the saved policy period, with the end date exclusive. Out-of-period claims, including claims requiring claims-made/retroactive-date interpretation, go to manual review; this is not a denial or a coverage finding. Unknown coverage lines, ambiguous policies, unknown/different currency and conflicting reported values also block the batch rather than being silently changed.

Amounts are nonnegative integer minor units in the explicitly named policy currency, or JSON `null` when unknown. They mean cumulative gross indemnity paid and outstanding indemnity reserves; normalize expenses, recoveries, net amounts or other bases separately before intake. No currency conversion occurs. Explicit zero stays zero; null stays unknown. Unknown fields such as claimant names, injury narratives, or scores are rejected rather than silently stored.

## Preview, review and commit

Preview does not create a loss-history database:

```sh
python scripts/private_loss_history.py --workspace /srv/transport3r-private --input /srv/transport3r-private/loss-history.json
```

Inspect every row-number reason and reconcile the source. Any unmatched, invalid or conflicting row blocks the **whole batch**. Fix the private input or the saved portfolio through its authorized review workflow, then preview again. Do not force an identity or substitute zero for unknown data to obtain a passing receipt.

Commit requires the exact preview fingerprint and the local reviewer's name:

```sh
python scripts/private_loss_history.py --workspace /srv/transport3r-private --input /srv/transport3r-private/loss-history.json --commit --reviewer "Authorized local reviewer" --expected-preview <PREVIEW_SHA256>
```

The fingerprint binds the exact input bytes and the complete saved portfolio snapshot. Changed input or portfolio requires renewed approval. Retain the original private input: its receipt SHA proves which normalized file was read, **not** that the upstream insurer document was independently authenticated.

## Accounting and immutable history

Every input row is counted as one unique candidate, one exact repeated normalized observation, or one row requiring review. Commit is atomic. Same-valuation conflicts roll back all writes, and reimporting the same approved input adds neither duplicate observations nor history. A new file can refer to an already stored observation without duplicating it. Later valuations append separate immutable observations; they never overwrite earlier reported amounts or silently reassign the claim.

Summaries cover one explicitly selected batch/valuation. They do not sum all historical snapshots as separate losses. Currency and coverage line remain separate groups. `known_sum` is an exact decimal string of minor units and is accompanied by `unknown_count`; it is not a complete total where values are unknown. An empty loss-run declaration is a different evidence type and is not inferred from an empty list. The importer always reports `population_complete: false`, no actuarial score and no coverage determination.

The ledger stores a frozen historical policy identity. A future live portfolio join must revalidate that identity; importing a ledger does not authorize later automatic remapping. Corrections to conflicting historical claim identities/valuations need a separately reviewed amendment mechanism, not an overwrite.

## Still separate

Private browser/API integration, operational installation, actual insurer-file reconciliation, complete loss-run attestations, corrections/amendments, multi-user authorization, and claims-model validation are not completed by these synthetic unit/CLI tests. No production claim observations are bundled into public Pages, source fixtures or release artifacts.
