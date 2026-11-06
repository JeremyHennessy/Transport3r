import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, mkdir, readFile, writeFile, rm, symlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {assertPublicAsset, assertPublicDirectory} from './public-asset-policy.mjs';
import {createManifest, sha256} from './release-manifest.mjs';
import {verifyRelease} from './verify-hosted.mjs';
import {reviewedStaticInputs, generatedInventory} from './build-public.mjs';

const commit='a'.repeat(40);
async function buildFixture(t) {
  const root=await mkdtemp(join(tmpdir(),'t3-public-assets-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  await mkdir(join(root,'assets')); await mkdir(join(root,'data'));
  const bodies={
    'index.html':'<div id="root"></div><script src="/Transport3r/assets/index-TEST1234.js"></script><link href="/Transport3r/assets/index-TEST5678.css">',
    'assets/index-TEST1234.js':'Know the carrier before you price the risk; Runtime recovery',
    'assets/index-TEST5678.css':'body{}',
  };
  for(const [path,body] of Object.entries(bodies)) await writeFile(join(root,path),body);
  await writeFile(join(root,'data/source-health.json'),JSON.stringify({generated_at:'SYNTHETIC',sources:Array(36).fill({})}));
  await writeFile(join(root,'data/source-schemas.json'),JSON.stringify({generated_at:'SYNTHETIC',source_count:36,field_count:810}));
  const inventory=generatedInventory({output:Object.entries(bodies).map(([fileName,source])=>({type:'asset',fileName,source}))});
  return {root,inventory};
}
async function publicFixture(t) {
  const root=await mkdtemp(join(tmpdir(),'t3-public-input-'));
  t.after(()=>rm(root,{recursive:true,force:true}));
  await mkdir(join(root,'data'));
  await writeFile(join(root,'data/source-health.json'),'{}');
  await writeFile(join(root,'data/source-schemas.json'),'{}');
  return root;
}

test('only reviewed metadata and current generated hashed application paths are eligible',()=>{
  for(const path of ['index.html','data/source-health.json','data/source-schemas.json','assets/index-ABC123xy.js',
                    'assets/index-ABC123xy.js.map','assets/index-ABC123xy.css']) assert.doesNotThrow(()=>assertPublicAsset(path));
  for(const path of ['assets','data']) assert.doesNotThrow(()=>assertPublicDirectory(path));
});

test('rejects raw data, private files, and ordinary but unreviewed script/image/font paths',()=>{
  for(const path of ['workspace.sqlite','data/policies.json','data/claims.csv','data/integrity.json','local_workspace/app.js',
                    '.env','warehouse/source.duckdb','assets/claims.js','assets/private-workspace.js.map','assets/session.json',
                    '/index.html','../index.html','assets/../index.html','assets//app.js','assets\\app.js','assets/nested/app.js',
                    'assets/app.js?secret','assets/%2e%2e.js','release-manifest.json','assets/customer-data.js','assets/debug.svg',
                    'assets/app.js.map','assets/logo.png','assets/font.woff2','assets/index-ABC123xy.svg']) {
    assert.throws(()=>assertPublicAsset(path),/public|private|Pages/);
  }
  for(const path of ['warehouse','private','assets/nested','data/raw']) assert.throws(()=>assertPublicDirectory(path));
});

test('normal actual generated inventory produces an exact verifiable release',async t=>{
  const {root,inventory}=await buildFixture(t); const manifest=await createManifest(root,commit,inventory);
  const result=await verifyRelease('https://example.org/Transport3r/',commit,async url=>new Response(await readFile(join(root,url.pathname.replace('/Transport3r/','')))));
  assert.equal(result.verified_files,5); assert.equal(manifest.commit,commit);
});

test('build refuses copied private data before writing a release manifest',async t=>{
  const {root,inventory}=await buildFixture(t); await writeFile(join(root,'data/claims.json'),'SYNTHETIC PRIVATE FIXTURE ONLY');
  await assert.rejects(createManifest(root,commit,inventory),/Unexpected or private artifact/);
  await assert.rejects(readFile(join(root,'release-manifest.json')),/ENOENT/);
});

test('build refuses unexpected directories, even when empty',async t=>{
  const {root,inventory}=await buildFixture(t); await mkdir(join(root,'private'));
  await assert.rejects(createManifest(root,commit,inventory),/Unexpected public asset directory/);
});

test('build refuses symlinks rather than reading or publishing targets',async t=>{
  const {root,inventory}=await buildFixture(t); await symlink(join(root,'index.html'),join(root,'assets/index-ABC123xy.js'));
  await assert.rejects(createManifest(root,commit,inventory),/Symlink/);
});

test('hosted verification rejects a private manifest entry without fetching it',async t=>{
  const {root,inventory}=await buildFixture(t); const manifest=await createManifest(root,commit,inventory);
  manifest.files['data/policies.json']={bytes:7,sha256:sha256('PRIVATE')}; const fetched=[];
  await assert.rejects(verifyRelease('https://example.org/Transport3r/',commit,async url=>{
    const path=url.pathname.replace('/Transport3r/',''); fetched.push(path);
    return new Response(path==='release-manifest.json'?JSON.stringify(manifest):await readFile(join(root,path)));
  }),/Unexpected or private artifact/);
  assert.ok(!fetched.includes('data/policies.json'));
});

test('public input rejects extra copied scripts, maps, images, fonts and even forged hashed names',async t=>{
  const root=await publicFixture(t); assert.equal((await reviewedStaticInputs(root)).size,2);
  for(const path of ['customer-data.js','debug.svg','index-ABC123xy.js','source.js.map','sample.png','type.woff2']){
    await writeFile(join(root,path),'SYNTHETIC');
    await assert.rejects(reviewedStaticInputs(root),/Unreviewed static public asset/);
    await rm(join(root,path));
  }
  await mkdir(join(root,'assets')); await writeFile(join(root,'assets/index-ABC123xy.js'),'SYNTHETIC');
  await assert.rejects(reviewedStaticInputs(root),/Unreviewed static public directory/);
});

test('public input rejects symlinks and missing reviewed metadata',async t=>{
  const root=await publicFixture(t); await rm(join(root,'data/source-health.json'));
  await assert.rejects(reviewedStaticInputs(root),/Missing reviewed/);
  await symlink(join(root,'data/source-schemas.json'),join(root,'data/source-health.json'));
  await assert.rejects(reviewedStaticInputs(root),/Symlink/);
});

test('hash-looking extra output is not authorized without real compiler inventory membership',async t=>{
  const {root,inventory}=await buildFixture(t);
  await writeFile(join(root,'assets/index-AbCd1234.js'),'SYNTHETIC UNREVIEWED');
  await assert.rejects(createManifest(root,commit,inventory),/not the exact generated/);
});

test('generated file changed after build fails byte-for-byte authorization',async t=>{
  const {root,inventory}=await buildFixture(t); await writeFile(join(root,'assets/index-TEST1234.js'),'SYNTHETIC REPLACEMENT');
  await assert.rejects(createManifest(root,commit,inventory),/not the exact generated/);
});

test('missing compiler output and missing compiler inventory both fail closed',async t=>{
  const {root,inventory}=await buildFixture(t); await rm(join(root,'assets/index-TEST1234.js'));
  await assert.rejects(createManifest(root,commit,inventory),/inventory differs/);
  await assert.rejects(createManifest(root,commit),/inventory is required/);
});

test('compiler inventory rejects duplicate, incomplete or out-of-policy output',()=>{
  assert.throws(()=>generatedInventory({}),/Expected completed/);
  assert.throws(()=>generatedInventory({output:[]}),/Incomplete/);
  assert.throws(()=>generatedInventory({output:[{type:'asset',fileName:'assets/debug.svg',source:'SYNTHETIC'}]}),/Unexpected/);
  assert.throws(()=>generatedInventory({output:[{type:'asset',fileName:'index.html',source:'a'},{type:'asset',fileName:'index.html',source:'b'}]}),/Duplicate/);
});
