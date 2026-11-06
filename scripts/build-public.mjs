/** Build only generated code and individually reviewed public metadata.
 * No files copied from public/ are authorized merely by a filename/extension.
 */
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {lstat, readdir, readFile, mkdir, writeFile} from 'node:fs/promises';
import {resolve, relative, dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from 'vite';
import {assertPublicAsset, assertReviewedStaticAsset, PUBLIC_METADATA} from './public-asset-policy.mjs';
import {createManifest} from './release-manifest.mjs';

const hash = body => createHash('sha256').update(body).digest('hex');

export async function reviewedStaticInputs(directory) {
  // Inspect the whole input tree: even an empty unexpected directory is refused.
  const root = await lstat(directory);
  if (!root.isDirectory() || root.isSymbolicLink()) throw new Error('Public input root must be a real directory');
  const files = new Map();
  async function walk(folder) {
    for (const entry of await readdir(folder, {withFileTypes:true})) {
      const path = resolve(folder,entry.name), key = relative(directory,path).replaceAll('\\','/');
      if (entry.isSymbolicLink()) throw new Error(`Symlink is not a reviewed static public asset: ${key}`);
      if (entry.isDirectory()) {
        if (key !== 'data') throw new Error(`Unreviewed static public directory: ${key}`);
        await walk(path);
      } else {
        if (!entry.isFile()) throw new Error(`Unsupported static public asset: ${key}`);
        assertReviewedStaticAsset(key);
        files.set(key,await readFile(path));
      }
    }
  }
  await walk(directory);
  if (files.size !== PUBLIC_METADATA.size || [...PUBLIC_METADATA].some(path => !files.has(path))) {
    throw new Error('Missing reviewed static source metadata');
  }
  return files;
}

export function generatedInventory(result) {
  const results = Array.isArray(result) ? result : [result], files = new Map();
  for (const group of results) {
    if (!Array.isArray(group?.output)) throw new Error('Expected completed Vite bundle output');
    for (const item of group.output) {
      const path = item.fileName;
      assertPublicAsset(path);
      if (PUBLIC_METADATA.has(path) || files.has(path)) throw new Error(`Duplicate or non-generated bundle output: ${path}`);
      const source = item.type === 'chunk' ? item.code : item.type === 'asset' ? item.source : null;
      if (!(typeof source === 'string' || source instanceof Uint8Array)) throw new Error(`Invalid generated output: ${path}`);
      const body = Buffer.from(source);
      files.set(path,{sha256:hash(body),bytes:body.length});
    }
  }
  if (!files.has('index.html') || ![...files.keys()].some(path => path.endsWith('.js')) || ![...files.keys()].some(path => path.endsWith('.css'))) {
    throw new Error('Incomplete generated application inventory');
  }
  return files;
}

export async function buildPublic(commit, directory = resolve('dist')) {
  const staticFiles = await reviewedStaticInputs(resolve('public'));
  // Vite's public-directory copy is disabled. Authorization below comes from the
  // actual returned compiler output, not a receipt found alongside copied files.
  const result = await build({build:{copyPublicDir:false, outDir:directory}});
  const generated = generatedInventory(result);
  for (const [path,body] of staticFiles) {
    const target = resolve(directory,path);
    await mkdir(dirname(target),{recursive:true});
    await writeFile(target,body);
  }
  return createManifest(directory,commit,generated);
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const head = execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim();
  if (process.env.GITHUB_SHA && process.env.GITHUB_SHA !== head) throw new Error('Checkout differs from GITHUB_SHA');
  const manifest = await buildPublic(head);
  console.log(`Release manifest: ${manifest.commit}, ${Object.keys(manifest.files).length} files`);
}
