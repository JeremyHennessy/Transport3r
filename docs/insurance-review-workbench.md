# Insurance review casework — local-only v1

The public Carrier 360 Insurance page provides evidence-by-coverage summaries. A separate **private local** workbench holds analyst decisions and insurer policy metadata. The two must never be conflated.

## Workflow

1. Start the password-protected loopback private workspace per `docs/local-private-workspace.md`.
2. Save an `INSURER_PORTFOLIO_1` account/policy/USDOT (USDOT exact matching, no inferred ownership).
3. Select **Review insurance lines** next to that policy or open the Insurance reviews section.
4. Select one of the eight insurance lines, record evidence request state, factual rationale, optional source link, analyst-entered source cut reference and due date.
5. Save. The local SQLite store retains the current state and a **separate append-only audit history**. The signed-in owner is recorded as reviewer.
6. Resolve requested evidence; change review state. A status of **reviewed** means an analyst reviewed the note; it is not a bind, decline, license, insurance effectiveness or legal coverage decision.

## Storage and API

- Local SQLite: `workspace.sqlite`, tables `insurance_reviews` and `insurance_review_history`.
- `POST /api/insurance-review` validates an existing portfolio account/policy/USDOT, eight permitted lines, four review states, 10–8,000 character notes, optional HTTP(S) evidence reference, optional ISO due date. Unknown fields rejected.
- `GET /api/state` includes up to 500 most recently updated private insurance reviews.
- `GET /api/insurance-review-history?id=...` retrieves the append-only decision history of a saved case.
- Existing session authentication, loopback Host checks, same-origin JSON mutation rules and security headers apply to every new route.
- Private data is not accessible through the GitHub Pages app. **Do not copy SQLite databases into `public/`, `dist/`, artifacts, logs or production static assets.**

## Evidence quality and limitations

- A cut reference entered by an analyst is a note, **not independent proof** that a source was acquired or matched.
- The public FMCSA filings can support review but do not establish in-force coverages, contract amounts or even a specific insured policy.
- No pricing, composite carrier risk, fraud decision, loss probability or coverage determination is computed by this module.
- Local SQLite files rely on OS/disk access control, not app-level encryption; never expose localhost service to the Internet.
- For multi-user insurers, implement a separately authenticated, encrypted, isolated hosted service before collecting policy data.

## Acceptance gates

- `python -m unittest discover -s scripts -p 'test_*.py'`
- `node --check local_workspace/app.js`
- `npm test`, `npm run typecheck`, `npm run build`
- API tests confirm only the authenticated owner can write, origin check blocks cross-site writes, linked USDOT matches an existing policy, and history persists prior versions.
- Browser review of the **local private** form in a controlled test environment. No real insured records in screenshots.
