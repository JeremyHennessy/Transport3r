import { createHash } from 'node:crypto';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { assertPublicAsset, assertPublicDirectory, PUBLIC_METADATA } from './public-asset-policy.mjs';

export const sha256 = (body) => createHash('sha256').update(body).digest('hex');

export async function createManifest(directory, commit, generated) {
  if (!/^[a-f0-9]{40}$/.test(commit)) throw new Error('A full Git commit SHA is required');
  if (!(generated instanceof Map) || !generated.size) throw new Error('The actual generated bundle inventory is required');
  const files = {};
  const observed = new Set();
  async function walk(folder) {
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      const path = resolve(folder, entry.name);
      const key = relative(directory, path).replaceAll('\\', '/');
      if (entry.isSymbolicLink()) throw new Error(`Symlink is not a public build asset: ${key}`);
      if (entry.isDirectory()) {
        assertPublicDirectory(key);
        await walk(path);
      } else {
        if (!entry.isFile()) throw new Error(`Unsupported build artifact: ${key}`);
        if (key === 'release-manifest.json') continue;
        assertPublicAsset(key);
        const body = await readFile(path);
        const record = { sha256: sha256(body), bytes: body.length };
        if (!PUBLIC_METADATA.has(key)) {
          const expected = generated.get(key);
          if (!expected || expected.sha256 !== record.sha256 || expected.bytes !== record.bytes) {
            throw new Error(`File is not the exact generated bundle output: ${key}`);
          }
          observed.add(key);
        }
        files[key] = record;
      }
    }
  }
  await walk(directory);
  if (observed.size !== generated.size || [...generated.keys()].some(path => !observed.has(path))) {
    throw new Error('Generated application inventory differs from packaged files');
  }
  const health = JSON.parse(await readFile(resolve(directory, 'data/source-health.json'), 'utf8'));
  const schemas = JSON.parse(await readFile(resolve(directory, 'data/source-schemas.json'), 'utf8'));
  const identity = JSON.parse(await readFile(resolve('data/fmcsa_source_contract.json'), 'utf8'));
  const temporal = JSON.parse(await readFile(resolve('data/temporal_policy.json'), 'utf8'));
  const manifest = {
    schema_version: 1,
    commit,
    built_at: new Date().toISOString(),
    // These identify the bundled metadata cut, not historical carrier-record snapshots.
    source_metadata: { health_generated_at: health.generated_at, schemas_generated_at: schemas.generated_at,
      source_count: schemas.source_count, field_count: schemas.field_count,
      identity_contract: identity.identity_contract, temporal_contract: temporal.contract,
      sms_release_binding: 'UNVERIFIED', tri_v0_1: temporal.model_release?.tri_v0_1 },
    files: Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b))),
  };
  await writeFile(resolve(directory, 'release-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  return manifest;
}
