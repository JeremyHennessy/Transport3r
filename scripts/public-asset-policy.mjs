/** Explicit public build boundary; private workspaces and raw data are not Pages assets.
 *
 * This rejects unexpected files before reading/packaging them. It is not a
 * content classifier, a secret scanner, or authorization for private API hosting.
 * Add a new public path only through review of this policy and its regression tests.
 */
const METADATA = new Set(['index.html', 'data/source-health.json', 'data/source-schemas.json']);
const COMPILED_ASSET = /^assets\/[A-Za-z0-9][A-Za-z0-9_.-]*\.(?:js|css|js\.map|css\.map|svg|png|jpg|jpeg|webp|ico|woff|woff2)$/;
const PRIVATE_FILENAME = /(?:^|[_.-])(?:private|workspace|portfolio|policy|policies|claim|claims|insured|insurer|secret|secrets|credential|credentials|token|tokens|session|sessions|audit|warehouse)(?:[_.-]|$)/i;

export function assertPublicAsset(path) {
  if (typeof path !== 'string' || !path || path.includes('\\') || path.split('/').some(p => !p || p === '.' || p === '..')) {
    throw new Error(`Invalid public asset path: ${path}`);
  }
  if (METADATA.has(path)) return;
  if (COMPILED_ASSET.test(path) && !PRIVATE_FILENAME.test(path.slice('assets/'.length))) return;
  throw new Error(`Unexpected or private artifact cannot enter public Pages: ${path}`);
}

export function assertPublicDirectory(path) {
  if (path !== 'assets' && path !== 'data') throw new Error(`Unexpected public asset directory: ${path}`);
}
