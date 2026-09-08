import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { readdir, readFile, writeFile } from 'node:fs/promises';
import { resolve, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

export const sha256 = (body) => createHash('sha256').update(body).digest('hex');

export async function createManifest(directory, commit) {
  if (!/^[a-f0-9]{40}$/.test(commit)) throw new Error('A full Git commit SHA is required');
  const files = {};
  async function walk(folder) {
    for (const entry of await readdir(folder, { withFileTypes: true })) {
      const path = resolve(folder, entry.name);
      if (entry.isDirectory()) await walk(path);
      else {
        const key = relative(directory, path).replaceAll('\\', '/');
        if (key === 'release-manifest.json') continue;
        const body = await readFile(path);
        files[key] = { sha256: sha256(body), bytes: body.length };
      }
    }
  }
  await walk(directory);
  const health = JSON.parse(await readFile(resolve(directory, 'data/source-health.json'), 'utf8'));
  const schemas = JSON.parse(await readFile(resolve(directory, 'data/source-schemas.json'), 'utf8'));
  const manifest = {
    schema_version: 1,
    commit,
    built_at: new Date().toISOString(),
    // These identify the bundled metadata cut, not historical carrier-record snapshots.
    source_metadata: { health_generated_at: health.generated_at, schemas_generated_at: schemas.generated_at,
      source_count: schemas.source_count, field_count: schemas.field_count },
    files: Object.fromEntries(Object.entries(files).sort(([a], [b]) => a.localeCompare(b))),
  };
  await writeFile(resolve(directory, 'release-manifest.json'), `${JSON.stringify(manifest, null, 2)}\n`);
  return manifest;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const head = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
  if (process.env.GITHUB_SHA && process.env.GITHUB_SHA !== head) throw new Error('Checkout differs from GITHUB_SHA');
  const manifest = await createManifest(resolve('dist'), head);
  console.log(`Release manifest: ${manifest.commit}, ${Object.keys(manifest.files).length} files`);
}
