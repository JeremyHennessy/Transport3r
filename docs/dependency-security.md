# Build dependency security remediation

Reviewed November 9, 2026. Existing pins Vite 6.0.5 and esbuild 0.24.0 predate
maintainer-published development-server security fixes. This is not a finding of
an exploited production static site. Do not expose a development server to clients.

Primary references:
- https://github.com/vitejs/vite/security/advisories/GHSA-p9ff-h696-f583
- https://github.com/vitejs/vite/security/advisories/GHSA-8g5g-mxqh-grgj
- https://github.com/evanw/esbuild/security/advisories/GHSA-67mh-4wv8-2f99
- https://github.com/evanw/esbuild/releases/tag/v0.28.2

The target retains the existing Vite major version: Vite 6.4.5 and esbuild 0.28.2,
with the esbuild override also preventing an older nested development-server copy.
Actual compatibility and the complete dependency graph require registry resolution,
full unit/build/browser tests, exact-head review and a real npm vulnerability scan.

## Reproducible resolution and acceptance

The dependency workflow audits the current reviewed lockfile across production and
development dependencies. Any reported issue, invalid response, command error or
network failure is not accepted. A candidate is resolved in an isolated directory
from explicit reviewed target pins, with lifecycle scripts disabled. Its generated
package/lockfile and dependency archive are retained, not silently substituted for
production inputs. Candidate success does not make the current lockfile pass.

After inspecting the candidate and its audit results, commit its exact package files
and run the normal repository checks. Once the reviewed manifest has the target
pins, the workflow audits that committed lockfile without generating a replacement.
No deployed bundle is rebuilt from unreviewed package mutations. Protect the security
audit as a required check through the normal repository settings process.

The first local npm-audit attempt could not reach registry.npmjs.org (EAI_AGAIN);
it was recorded as unavailable, not vulnerability-free. A clean remote audit and
successful tests are still required before calling the dependency remediation done.
