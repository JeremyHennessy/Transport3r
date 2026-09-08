import { test } from 'node:test';
import assert from 'node:assert/strict';
import { verifyRelease } from './verify-hosted.mjs';
import { sha256 } from './release-manifest.mjs';

const commit = 'a'.repeat(40);
function fixture() {
  const files = {
    'index.html': '<div id="root"></div><script src="/Transport3r/assets/app.js"></script><link href="/Transport3r/assets/app.css">',
    'assets/app.js': 'Know the carrier before you price the risk; Runtime recovery',
    'assets/app.css': 'body{}',
    'data/source-health.json': JSON.stringify({ generated_at: '2026-09-08', sources: Array(36).fill({}) }),
    'data/source-schemas.json': JSON.stringify({ generated_at: '2026-09-08', source_count: 36, field_count: 810 }),
  };
  const manifest = { schema_version: 1, commit, source_metadata: { health_generated_at: '2026-09-08', schemas_generated_at: '2026-09-08' },
    files: Object.fromEntries(Object.entries(files).map(([path, body]) => [path, { sha256: sha256(body), bytes: Buffer.byteLength(body) }])) };
  return { files, manifest, get: async (url) => {
    const path = url.pathname.replace('/Transport3r/', '');
    const body = path === 'release-manifest.json' ? JSON.stringify(manifest) : files[path];
    return new Response(body ?? '', { status: body === undefined ? 404 : 200 });
  } };
}
test('accepts exact commit, built entry points and all artifact hashes', async () => {
  assert.equal((await verifyRelease('https://example.com/Transport3r/', commit, fixture().get)).verified_files, 5);
});
test('rejects a successful but stale deployment', async () => {
  await assert.rejects(verifyRelease('https://example.com/Transport3r/', 'b'.repeat(40), fixture().get), /Served commit/);
});
test('rejects mixed release files even when the manifest is current', async () => {
  const f = fixture(); f.files['assets/app.js'] += 'stale';
  await assert.rejects(verifyRelease('https://example.com/Transport3r/', commit, f.get), /hash mismatch/);
});
test('rejects root-published development HTML even with a valid hash', async () => {
  const f = fixture(); f.files['index.html'] = '<div id="root"></div><script src="/src/main.tsx"></script>';
  f.manifest.files['index.html'] = { sha256: sha256(f.files['index.html']), bytes: Buffer.byteLength(f.files['index.html']) };
  await assert.rejects(verifyRelease('https://example.com/Transport3r/', commit, f.get), /not a built application/);
});
test('fails on unavailable files', async () => {
  const f = fixture(); delete f.files['assets/app.css'];
  await assert.rejects(verifyRelease('https://example.com/Transport3r/', commit, f.get), /HTTP 404/);
});
