# Public Pages asset boundary

The release builder and hosted verifier both enforce `scripts/public-asset-policy.mjs`. Only the built HTML, two reviewed public FMCSA metadata JSON files, and recognized compiled asset filenames are accepted. The builder rejects symlinks and unexpected directories before opening those files. A failed build never reaches the existing Pages upload/deploy steps.

Private workspace code, raw source downloads, DuckDB/SQLite databases, policy/claims JSON or CSV, credentials/configuration files, private audit receipts and unreviewed datasets must not be placed in `public/` or `dist/`. Installing a real read-only source API is a separate deployment with its own accepted data and access controls. Private insurer data must never be mounted into that public-source service.

The policy is a preventative file-packaging control, **not a content classifier or a proof that arbitrary JavaScript contains no secrets**. It cannot replace source review, dependency review, correct data classification or access control. New public paths require an explicit reviewed policy change and tests. Do not rename private data to an allowed extension to publish it.

Run `node --test scripts/public-assets.test.mjs`. Tests cover a normal release, copied private data, unexpected folders, symlinks, forbidden/traversal filenames, and refusal to download forbidden entries from a hosted manifest. All private-data test values are synthetic.
