# Integrated open-data candidate validation

## Change boundary

This candidate combines the map/table and snapshot/VIN changes with the existing
inspection-child integrity corrections from PR #69 and selected dependency-audit
checks from PR #71. It is not a merge into protected main or an accepted nationwide
release. Earlier passing checks apply only to their own recorded source revisions.

PR #69 source revision: `3e76b6d932f8e5f608d7e8d7a2e7096908c3d8f9`.
The three imported files are byte-identical to that revision:

- `scripts/inspection_children.py`
- `scripts/test_inspection_children.py`
- `scripts/test_preflight_ceiling_priority.py`

They retain strict global/per-page bounds, original source identities, publisher
stability, per-batch high-water counts and permanent-error precedence. A proven
hard-limit breach cannot become retryable because a different request timed out.
No fixture, dropped row or weakened gate substitutes for real-source acceptance.

PR #71 source revision: `b71f3377bc95e06f6f24a674a2ada81b03c087ba`.
The fail-closed audit classifier, its regression tests, optional-platform URL
checks, build-target checks and read-only audit workflow are reused. The MapLibre
package manifest, lockfile and compatible build settings are preserved. A clean
scan of PR #71's older dependency graph does not certify this larger graph: the
new candidate must pass its own registry audit. No temporary dependency/source
writer or automatic package substitution is included.

## Reviewer correction

The snapshot export validator now checks nested slice publication, retrieval time
and query scope as well as outer provenance, row identity and counts. Three
independent tampering regressions failed before the correction and pass after it.
This prevents an archive from carrying contradictory nested acquisition metadata.

## Verified prior candidate browser evidence

At source `481af280a4fef6fe4ca2969b06a87863d8bf8580`, workflow
`42708720937` had a successful `review` job (129472294691), including actual built
UI checks for release recovery, integrity API, local private workflow, maps/table,
and same-snapshot reports plus VIN-specific findings. Artifact 13715785469 ZIP
SHA-256 is `e00d9a1999b274d97e24f440fc6e1c5fba5d0bcab0cfde6ba155b3bf6248a635`.
All 299 archived source files matched the tested tree. Four snapshot/VIN screenshot
hashes and nine map/table screenshot hashes were verified; the actual report and
VIN desktop/mobile images were inspected.

The separate `current-release-browser` job failed on the existing main release's
desktop carrier directory. Its retained screenshot shows an FMCSA request timeout;
35 other route/viewport checks passed. Artifact 13715026477 ZIP SHA-256 is
`be52509e189580da0af851f545401e4343ca122f7d358edf8ca73548fafad3d8`.
The full workflow remains failed; a successful candidate job does not overwrite
that outcome. The live site had not received the candidate changes.

## Remaining release requirements

Run all tests, the actual current-lockfile registry audit, the accepted real-source
cohort validation and the built-browser checks on this integrated head. Resolve
independent review findings before protected merge, then verify the hosted full
commit and relevant screens. An old-main diagnostic is not proof that a new PR was
deployed. Request/render success is not nationwide data, private tenant, fleet
ownership, repaired-recall, actuarial or CAB-parity acceptance.

The directory timeout/freshness work in PR #67 and source metadata in #68 remain
separate open changes unless explicitly reconciled into a subsequent revision.
Do not report them as deployed merely because this candidate's tests pass.
