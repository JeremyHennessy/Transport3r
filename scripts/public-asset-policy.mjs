/** Public path boundary, not a secret/content scanner.
 * Compiled filenames are necessary but never sufficient build authorization:
 * release-manifest also requires the exact in-memory Vite output inventory.
 * Static input files must be individually reviewed here, never extension-globbed.
 */
export const PUBLIC_METADATA = new Set(['data/source-health.json', 'data/source-schemas.json']);
const GENERATED_APP_ASSET = /^assets\/(?:index|maplibre-gl(?:-worker)?)-[A-Za-z0-9_-]{8}\.(?:js|css)(?:\.map)?$/;

export function assertPublicAsset(path) {
  if (typeof path !== 'string' || !path || path.includes('\\') || path.split('/').some(p => !p || p === '.' || p === '..')) {
    throw new Error(`Invalid public asset path: ${path}`);
  }
  if (path === 'index.html' || PUBLIC_METADATA.has(path) || GENERATED_APP_ASSET.test(path)) return;
  throw new Error(`Unexpected or private artifact cannot enter public Pages: ${path}`);
}

export function assertPublicDirectory(path) {
  if (path !== 'assets' && path !== 'data') throw new Error(`Unexpected public asset directory: ${path}`);
}

export function assertReviewedStaticAsset(path) {
  if (!PUBLIC_METADATA.has(path)) throw new Error(`Unreviewed static public asset: ${path}`);
}
