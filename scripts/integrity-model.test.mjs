import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';

const compiled=await build({stdin:{contents:"export * from './src/integrityModel.ts';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {validateIntegrity,validateRelease,evidenceApiBase,loadIntegrity,GLOBAL_CHECKS,SOURCE_CHECKS}=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'));
const catalog=JSON.parse(await readFile('data/fmcsa_sources.json','utf8'));
const truth=names=>Object.fromEntries(names.map(name=>[name,true]));
const now=Date.parse('2026-11-06T16:00:00Z');
function fixture(){
 const sources=catalog.map(source=>{
  const n=source.id==='az4n-8mr2'?2:source.id==='fx4q-ay7w'?3:0;
  return {source:source.id,sha256:'a'.repeat(64),available_at:'2026-11-06T12:00:00Z',rows_updated_at:1,
   published:n,acquired:n,warehouse:n,actual_raw:n,actual_mapping:n,actual_joined:n,distinct_mapping_rows:n,
   missing_mapping_rows:0,orphan_mapping_rows:0,identity_mapping_disagreements:0,mapping_status:n?{RESOLVED:n}:{},
   exact_duplicate_rows:0,distinct_source_rows:n,checks:truth(SOURCE_CHECKS)};
 });
 const report={schema_version:'TRANSPORT3R_WAREHOUSE_AUDIT_2',status:'PASS',release_ready:true,audited_at:'2026-11-06T15:00:00Z',
  warehouse_sha256:'b'.repeat(64),identity_contract:'FMCSA_CARRIER_IDENTITY_1',scope:'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES',
  cut_id:'SYNTHETIC-UNIT-TEST',cut_available_at:'2026-11-06T13:00:00Z',source_count:36,raw_rows:5,receipt_rows:5,census_carriers:2,
  deep_exact_duplicates_checked:true,duplicate_rule:'EXACT_ORIGINAL_SOURCE_COLUMNS_V2',checks:truth(GLOBAL_CHECKS),sources,failures:[]};
 const health={status:'ok',independent_audit:'PASS',warehouse_sha256:report.warehouse_sha256,cut_id:report.cut_id,
  cut_available_at:report.cut_available_at,sources:36,identity_contract:report.identity_contract};
 return {report,health};
}
test('all registered sources, exact zero and raw-row grain are retained',()=>{
 const {report,health}=fixture(),value=validateIntegrity(report,health,now);
 assert.equal(value.sources.length,36);assert.equal(value.raw_rows,5);assert.equal(value.census_carriers,2);
 assert.equal(value.sources.find(s=>s.source==='aayw-vxb3').actual_raw,0);
});
for(const [name,change] of [
 ['failed receipt',r=>r.status='FAIL'],['shallow audit',r=>r.deep_exact_duplicates_checked=false],
 ['unreleased audit',r=>r.release_ready=false],['old schema',r=>r.schema_version='TRANSPORT3R_WAREHOUSE_AUDIT_1'],
 ['future audit',r=>r.audited_at='2030-01-01T00:00:00Z'],['missing timezone',r=>r.audited_at='2026-11-06T15:00:00'],
 ['impossible calendar date',r=>r.audited_at='2026-02-30T15:00:00Z'],
 ['missing global check',r=>delete r.checks.immutable_file],['failed global check',r=>r.checks.aggregate_rows=false],
 ['missing source',r=>r.sources.pop()],['duplicate source',r=>r.sources[1]=structuredClone(r.sources[0])],
 ['incorrect acquired rows',r=>r.sources[0].acquired+=1],['boolean row count',r=>r.sources[0].published=true],
 ['failed per-source check',r=>r.sources[0].checks.identity_mapping=false],
 ['wrong carrier assignment',r=>r.sources[0].identity_mapping_disagreements=1],
 ['orphan mapping',r=>r.sources[0].orphan_mapping_rows=1],
 ['invalid status',r=>r.sources[0].mapping_status={UNKNOWN:1}],
 ['bad duplicate accounting',r=>r.sources[0].exact_duplicate_rows+=1],
 ['false aggregate',r=>r.raw_rows+=1],['unsafe integer',r=>r.census_carriers=Number.MAX_SAFE_INTEGER+1],
 ['more carriers than Census rows',r=>r.census_carriers=99],
 ['source after cut',r=>r.sources[0].available_at='2026-11-06T14:00:00Z']
])test(name+' cannot certify a warehouse',()=>{const {report,health}=fixture();change(report);assert.throws(()=>validateIntegrity(report,health,now));});
for(const key of ['warehouse_sha256','cut_id','cut_available_at','sources','identity_contract','independent_audit'])
 test('health mismatch '+key+' fails closed',()=>{const {report,health}=fixture();health[key]='OTHER';assert.throws(()=>validateIntegrity(report,health,now));});
test('arbitrary private fields cannot be exported',()=>{
 const {report,health}=fixture();report.client_policy='PRIVATE CANARY';report.sources[0].local_path='PRIVATE CANARY';
 assert.ok(!JSON.stringify(validateIntegrity(report,health,now)).includes('PRIVATE CANARY'));
});
test('API URL allows HTTPS and explicit loopback only, without credentials',()=>{
 assert.equal(evidenceApiBase(''),null);
 assert.equal(evidenceApiBase('https://evidence.example/api/'),'https://evidence.example/api');
 assert.equal(evidenceApiBase('http://127.0.0.1:8787/'),'http://127.0.0.1:8787');
 for(const bad of ['http://example.com','https://user:pass@example.com','https://example.com/?token=x','https://example.com/#x','javascript:alert(1)']) assert.throws(()=>evidenceApiBase(bad));
});
test('release commit and saved source-probe date stay distinct from live health',()=>{
 const result=validateRelease({schema_version:1,commit:'c'.repeat(40),built_at:'2026-11-06T10:00:00Z',source_metadata:{source_count:36,field_count:810,health_generated_at:'2026-10-23T12:00:00Z'}});
 assert.equal(result.metadataAt,'2026-10-23T12:00:00Z');assert.equal(result.sources,36);
 assert.throws(()=>validateRelease({schema_version:1,commit:'not-a-sha',source_metadata:{}}));
});
test('HTTP failure never turns into known zero counts and requests omit credentials',async()=>{
 const original=globalThis.fetch, calls=[];
 globalThis.fetch=async(url,options)=>{calls.push({url,options});return new Response('{}',{status:503});};
 try{await assert.rejects(loadIntegrity('https://evidence.example',new AbortController().signal),/HTTP 503/);
  assert.equal(calls.length,2);assert.ok(calls.every(c=>c.options.credentials==='omit'&&c.options.cache==='no-store'));
 }finally{globalThis.fetch=original;}
});
