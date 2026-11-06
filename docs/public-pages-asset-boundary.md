# Public Pages asset boundary

`npm run build` runs TypeScript validation and `scripts/build-public.mjs`. The build inspects the entire static `public/` input tree before compilation. Only `data/source-health.json` and `data/source-schemas.json` are individually reviewed static files. Additional files, directories and symlinks fail closed, including harmless-looking JavaScript, source maps, images and fonts. A hash-looking copied filename is not an exception.

Vite's automatic public-directory copy is disabled. The release builder obtains the actual generated bundle inventory from Vite's returned output, then compares every generated on-disk path, byte length and SHA-256 with that in-memory inventory before writing the release manifest. Hash-shaped filenames alone are never sufficient to authorize build output. Missing, replaced and extra generated files are rejected. The two reviewed metadata files are copied explicitly, not by directory glob.

The hosted verifier checks the same restricted current application filename shape and exact manifest hashes/entry references. The build is the generation-provenance boundary: hosted verification cannot recover compiler provenance from an arbitrary remote file alone. Existing historical main manifests remain verifiable without weakening the new build's inventory requirement.

This is not a secret/content classifier. Private data must never be imported into reviewed frontend modules or allowed metadata. New static files, chunk naming conventions, images/fonts or source inputs require explicit review and regression coverage. A passing filename check does not authorize private hosting or insurer data publication.

Run `node --test scripts/public-assets.test.mjs scripts/release.test.mjs` and the normal production build. Synthetic tests cover copied ordinary assets, forged hashed names, extra/missing/replaced outputs, symlinks, private data and blocked hosted downloads. The synthetic API/browser build uses the same build boundary; it cannot bypass it with a direct manifest call.
