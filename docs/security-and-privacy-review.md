# Security and privacy review

Scope: engineering self-review and synthetic/HTTP regression tests of this branch. This is not
an independent penetration test, tenant-isolation certification or actual host acceptance.

## Enforced in this execution

The local loss API requires the existing authenticated owner, exact loopback Host and same-origin
JSON. Duplicate JSON keys, nonfinite JSON, unexpected request fields and oversized input are
rejected. Original file bytes are transferred as bounded canonical base64 so byte-order marks
and hashes are preserved. No source values are written to access logs.

A nonwriting preview signs the exact input/portfolio fingerprint, owner and session using an
in-memory server HMAC secret with a ten-minute expiry. Approval requires an explicit true value.
Changed files/portfolios, expired or wrong-session signatures and caller-supplied reviewer
fields are rejected. Logout revokes the session. Server restart invalidates outstanding approvals.
Imports reuse the existing atomic ledger and immutable valuation rules.

Portfolio and claim imports share a SQLite write lock across processes. The portfolio is reread
under that lock. Policies with saved claims cannot silently change USDOT, currency or coverage
period through the shared importer. Legitimate amendments require a future reviewed migration;
the guard does not decide contractual coverage.

Private loss summaries use a read-only connection, retain exact decimal-string minor-unit sums
and unknown counts, and include batch/source/portfolio hashes and reviewer/time. They do not
expose raw narratives or claimant data, infer a complete loss run, combine currencies or sum
repeated valuations. Exports require an explicit user click; browser memory is cleared on
logout/file change and no private browser persistence was added.

Public carrier evidence requires an installed independent deep audit; frontend health/audit and
carrier responses must match exactly. Transfers for audit metadata are bounded while streaming.
Public source installation never reuses the private loss database. Public asset allowlists remain
unchanged; the local loss JavaScript is appended only by the private loopback server.

## Explicitly not certified

The current private server has one owner. It does not implement tenant roles, SSO/MFA, per-tenant
storage, production encryption, external notification delivery or high availability. Do not expose
it beyond loopback. POSIX file modes are not proof of Windows ACLs or encrypted disk. Filesystem
access to an operator-owned directory remains a privileged boundary.

No actual insurer source document, claim, user account or private deployment was supplied.
Synthetic checks are not insurer consent, claims adjudication, real security approval or actuarial
acceptance. No paid host or external network access policy was configured.

Required next security work: independently designed multi-user authorization and isolation,
SSO/MFA integration, reviewed encrypted storage and backup key management, tenant-scoped audit /
export / retention / deletion, application and infrastructure penetration tests, incident recovery
and operating ownership. Preserve the existing public/private boundary while doing that work.
