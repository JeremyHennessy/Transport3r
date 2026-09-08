import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { sha256 } from './release-manifest.mjs';

export async function verifyRelease(pageUrl, expectedSha, get = fetch) {
  if (!/^[a-f0-9]{40}$/.test(expectedSha ?? '')) throw new Error('EXPECTED_SHA must be a full commit SHA');
  const base = new URL(pageUrl.endsWith('/') ? pageUrl : `${pageUrl}/`);
  const cacheKey = `${expectedSha}-${Date.now()}`;
  async function load(path) {
    const url = new URL(path, base);
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname)) throw new Error(`Asset outside project: ${path}`);
    url.searchParams.set('release_check', cacheKey);
    const response = await get(url, { cache: 'no-store', signal: AbortSignal.timeout(20000) });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return Buffer.from(await response.arrayBuffer());
  }
  const manifest = JSON.parse((await load('release-manifest.json')).toString());
  if (manifest.schema_version !== 1 || manifest.commit !== expectedSha) throw new Error(`Served commit ${manifest.commit} differs from ${expectedSha}`);
  const bodies = new Map();
  for (const [path, record] of Object.entries(manifest.files ?? {})) {
    if (!path || path.startsWith('/') || path.split('/').includes('..')) throw new Error(`Invalid manifest path: ${path}`);
    const body = await load(path);
    if (body.length !== record.bytes || sha256(body) !== record.sha256) throw new Error(`Artifact hash mismatch: ${path}`);
    bodies.set(path, body);
  }
  const html = bodies.get('index.html')?.toString() ?? '';
  if (!html.includes('<div id="root"></div>') || html.includes('/src/main.tsx')) throw new Error('Hosted page is not a built application');
  const scripts = [...html.matchAll(/src="([^"]+\.js)"/g)].map((m) => m[1]);
  const styles = [...html.matchAll(/href="([^"]+\.css)"/g)].map((m) => m[1]);
  if (!scripts.length || !styles.length) throw new Error('Missing compiled JS/CSS');
  for (const reference of [...scripts, ...styles]) {
    const url = new URL(reference, base);
    const key = url.pathname.slice(base.pathname.length);
    if (url.origin !== base.origin || !url.pathname.startsWith(base.pathname) || !bodies.has(key)) throw new Error(`Unverified entry asset: ${reference}`);
  }
  const scriptText = scripts.map((ref) => bodies.get(new URL(ref, base).pathname.slice(base.pathname.length)).toString()).join('\n');
  for (const marker of ['Know the carrier before you price the risk', 'Runtime recovery']) {
    if (!scriptText.includes(marker)) throw new Error(`App marker missing: ${marker}`);
  }
  const health = JSON.parse(bodies.get('data/source-health.json')?.toString() ?? '{}');
  const schemas = JSON.parse(bodies.get('data/source-schemas.json')?.toString() ?? '{}');
  if (health.sources?.length !== 36 || schemas.source_count !== 36 || !(schemas.field_count > 0)) throw new Error('Invalid bundled source contract');
  if (health.generated_at !== manifest.source_metadata?.health_generated_at || schemas.generated_at !== manifest.source_metadata?.schemas_generated_at) throw new Error('Source metadata cut differs from manifest');
  return { commit: manifest.commit, verified_files: bodies.size, source_count: schemas.source_count, field_count: schemas.field_count };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const attempts = Number(process.env.VERIFY_ATTEMPTS ?? 12);
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try {
      console.log(JSON.stringify(await verifyRelease(process.env.PAGE_URL ?? '', process.env.EXPECTED_SHA), null, 2));
      break;
    } catch (error) {
      if (attempt === attempts) throw error;
      console.warn(`Release check ${attempt}/${attempts}: ${error.message}`);
      await new Promise((done) => setTimeout(done, 5000));
    }
  }
}
