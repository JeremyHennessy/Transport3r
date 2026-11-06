# Private coverage-document checklists

This change extends the existing **single-owner, loopback-only** insurance review workspace. It does not create multi-tenant hosting, upload documents, import claims, determine coverage, or expose private information through GitHub Pages or the public evidence API.

## Workflow

Save an exact account/policy/USDOT review in the private workspace. Select **Requested documents** on that saved review. The eight supported coverage lines each have four versioned analyst prompts. They are suggestions to review, not mandatory policy or legal requirements.

An untouched item is **Not requested**, not complete. Requested items require a due date. Received and reviewed items require both a received date and an HTTPS evidence reference. Reviewed and not-applicable items require a substantive rationale. Receiving a document does not automatically review it, change the parent review, establish coverage, or turn missing loss runs into zero claims.

Only references and notes are saved. Put actual documents in approved private storage first; this app never fetches the reference. Do not put credentials in URLs. Evidence references are not claimed to have been checked by the software.

## Integrity and access boundaries

- Existing authenticated session, strict loopback Host and same-origin JSON controls apply to all new routes.
- Every write loads the existing review and checks its exact account/policy/USDOT against the saved private portfolio; callers cannot assign those identifiers through the document API.
- The requested revision must match the stored revision. A stale browser tab cannot overwrite a newer decision.
- SQLite writes and append-only change history are committed in the same immediate transaction. Identical saves do not create duplicate revisions.
- Templates are versioned as `COVERAGE_CHECKLIST_1`. Dates, status, field names, requirement keys and evidence links are validated. Unsupported coverage decisions and risk-score fields are rejected.
- History is readable only inside the authenticated private workspace. There is no delete-history endpoint or document endpoint in the public source service.

## Routes

`GET /api/insurance-requirements?review_id=<saved-review>` returns a checklist with explicit unknown/unrequested defaults.

`POST /api/insurance-requirement` accepts `review_id`, `requirement_key`, `status`, `due_date`, `received_on`, `evidence_url`, `notes`, integer `expected_revision`, and the exact current `expected_template_version`. The server records the authenticated reviewer.

`GET /api/insurance-requirement-history?review_id=<saved-review>&requirement_key=<key>` returns the saved versions, never document contents.

## Verification

`python -m unittest discover -s scripts -p 'test_coverage_requirements.py' -v`

`python scripts/validate_private_browser.py /path/to/new-synthetic-review-evidence`

Unit/HTTP tests and the browser gate use synthetic records only. The browser gate exercises request, receipt and review, both responsive widths, and history. Passing these checks is not acceptance of real insurer data, access-control review for remote hosting, or production deployment.

## Template upgrades

Document identity is stable for an exact saved review and requirement key. Existing version-derived IDs are retained, not replaced. Template updates leave earlier records and their append-only histories unchanged until an analyst explicitly saves against the current template version and current revision. Prior-template completed items remain visible but do not count toward current completion until re-reviewed. A stale template or revision is rejected rather than silently migrated by a browser save.

Removed prompts remain read-only historical items with reachable history. They are not part of current checklist totals and cannot accept new writes while retired. A new prompt key starts unrequested; it does not inherit another prompt's review. No template change determines coverage or interprets missing claims as zero.
