import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile, rm, symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {assertPublicAsset, assertPublicDirectory} from './public-asset-policy.mjs';
import {createManifest, sha256} from './release-manifest.mjs';
import {verifyRelease} from './verify-hosted.mjs';

const commit='a'.repeat(40);
async function buildFixture(t) {
  const root=await mkdtemp(join(tmpdir(),'t3-public-assets-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  await mkdir(join(root,'assets')); await mkdir(join(root,'data'));
  await writeFile(join(root,'index.html'),'<div id="root"></div><script src="/Transport3r/assets/app.js"></script><link href="/Transport3r/assets/app.css">');
  await writeFile(join(root,'assets/app.js'),'Know the carrier before you price the risk; Runtime recovery');
  await writeFile(join(root,'assets/app.css'),'body{}');
  await writeFile(join(root,'data/source-health.json'),JSON.stringify({generated_at:'SYNTHETIC',sources:Array(36).fill({})}));
  await writeFile(join(root,'data/source-schemas.json'),JSON.stringify({generated_at:'SYNTHETIC',source_count:36,field_count:810}));
  return root;
}

test('accepts only explicitly reviewed public metadata and ordinary compiled assets',()=>{
  for(const path of ['index.html','data/source-health.json','data/source-schemas.json','assets/index-ABC123.js',
                    'assets/index-ABC123.js.map','assets/index-ABC123.css','assets/logo.svg','assets/font.woff2']) {
    assert.doesNotThrow(()=>assertPublicAsset(path));
  }
  for(const path of ['assets','data']) assert.doesNotThrow(()=>assertPublicDirectory(path));
});

test('rejects raw datasets, databases, private workspaces, local configuration and misleading assets',()=>{
  for(const path of ['workspace.sqlite','data/policies.json','data/claims.csv','data/integrity.json','local_workspace/app.js',
                    '.env','warehouse/source.duckdb','assets/claims.js','assets/private-workspace.js.map','assets/session.json',
                    '/index.html','../index.html','assets/../index.html','assets//app.js','assets\\app.js','assets/nested/app.js',
                    'assets/app.js?secret','assets/%2e%2e.js','release-manifest.json']) {
    assert.throws(()=>assertPublicAsset(path),/public|private|Pages/);
  }
  for(const path of ['warehouse','private','assets/nested','data/raw']) assert.throws(()=>assertPublicDirectory(path));
});

test('normal reviewed bundle still produces a verifiable exact release',async t=>{
  const root=await buildFixture(t); const manifest=await createManifest(root,commit);
  const result=await verifyRelease('https://example.org/Transport3r/',commit,async url=>{
    const path=url.pathname.replace('/Transport3r/','');
    return new Response(await readFile(join(root,path)));
  });
  assert.equal(result.verified_files,5); assert.equal(manifest.commit,commit);
});

test('build refuses copied private data before writing a release manifest',async t=>{
  const root=await buildFixture(t); await writeFile(join(root,'data/claims.json'),'SYNTHETIC PRIVATE FIXTURE ONLY');
  await assert.rejects(createManifest(root,commit),/Unexpected or private artifact/);
  await assert.rejects(readFile(join(root,'release-manifest.json')),/ENOENT/);
});

test('build refuses unexpected directories, even when they are empty',async t=>{
  const root=await buildFixture(t); await mkdir(join(root,'private'));
  await assert.rejects(createManifest(root,commit),/Unexpected public asset directory/);
});

test('build refuses symlinks rather than reading or publishing their targets',async t=>{
  const root=await buildFixture(t);
  await symlink(join(root,'index.html'),join(root,'assets/link.js'));
  await assert.rejects(createManifest(root,commit),/Symlink/);
});

test('hosted verification rejects a private manifest entry without downloading its bytes',async t=>{
  const root=await buildFixture(t); const manifest=await createManifest(root,commit);
  manifest.files['data/policies.json']={bytes:7,sha256:sha256('PRIVATE')};
  const fetched=[];
  await assert.rejects(verifyRelease('https://example.org/Transport3r/',commit,async url=>{
    const path=url.pathname.replace('/Transport3r/',''); fetched.push(path);
    return new Response(path==='release-manifest.json'?JSON.stringify(manifest):await readFile(join(root,path)));
  }),/Unexpected or private artifact/);
  assert.ok(!fetched.includes('data/policies.json'));
});
