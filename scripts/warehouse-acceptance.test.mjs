import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {syntheticAudit,syntheticEvidence} from './fixtures/warehouse-audit-fixture.mjs';
const result=await build({stdin:{contents:"export * from './src/warehouseAcceptance'",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {verifyWarehouseAudit,reconcileWarehouseAudit}=await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
test('complete carrier evidence requires the exact independently audited warehouse',()=>{
 const evidence=syntheticEvidence(),{report,health}=syntheticAudit(evidence);
 assert.equal(verifyWarehouseAudit(evidence,report,health).warehouse_sha256,evidence.warehouse_sha256);
});
for(const [label,mutate] of [
 ['warehouse hash',e=>e.warehouse_sha256='c'.repeat(64)],
 ['cut identity',e=>e.cut_id='different'],
 ['cut time',e=>e.cut_available_at='2026-10-24T00:00:00Z'],
 ['source hash',e=>e.sources[0].source_sha256='c'.repeat(64)],
 ['source publisher time',e=>e.sources[0].source_rows_updated_at=2],
 ['source retrieval time',e=>e.sources[0].source_available_at='2026-10-22T00:00:00Z'],
 ['mapping totals',e=>e.completeness_receipt.mapping_totals.unresolved=4],
 ['carrier count',e=>e.sources[0].carrier_rows=999],
 ['duplicate source',e=>e.sources[1]=structuredClone(e.sources[0])],
 ['missing source',e=>e.sources.pop()],
])test(`rejects unmatched ${label}`,()=>{
 const evidence=syntheticEvidence(),{report,health}=syntheticAudit(evidence);mutate(evidence);
 assert.throws(()=>verifyWarehouseAudit(evidence,report,health));
});
test('receipt without a deep passing audit does not release complete evidence',()=>{
 const evidence=syntheticEvidence(),{report,health}=syntheticAudit(evidence);
 for(const value of [null,{status:'PASS'},{...report,deep_exact_duplicates_checked:false},{...report,release_ready:false}]){
  assert.throws(()=>verifyWarehouseAudit(evidence,value,health));
 }
 assert.throws(()=>verifyWarehouseAudit(evidence,report,{...health,independent_audit:'NOT_INSTALLED'}));
});
test('audit HTTP requests omit credentials and bind actual health and audit replies',async t=>{
 const evidence=syntheticEvidence(),{report,health}=syntheticAudit(evidence);const requests=[];
 t.mock.method(globalThis,'fetch',async (url,options)=>{requests.push({url,options});return Response.json(url.endsWith('/healthz')?health:report);});
 await reconcileWarehouseAudit('https://evidence.test',evidence,new AbortController().signal);
 assert.equal(requests.length,2);assert.ok(requests.every(r=>r.options.credentials==='omit'&&r.options.cache==='no-store'));
});
for(const mode of ['unavailable','oversize','invalid-json','missing-audit'])test(`audit HTTP fails closed: ${mode}`,async t=>{
 const evidence=syntheticEvidence(),{health}=syntheticAudit(evidence);
 t.mock.method(globalThis,'fetch',async url=>url.endsWith('/healthz')?Response.json(health):
  mode==='unavailable'?new Response('Unavailable',{status:503}):mode==='oversize'?new Response(' '.repeat(2*1024*1024+1)):
  mode==='invalid-json'?new Response('{broken'):Response.json({status:'NOT_INSTALLED'}));
 await assert.rejects(reconcileWarehouseAudit('https://evidence.test',evidence,new AbortController().signal));
});

test('pre-aborted caller sends no audit requests',async t=>{
 const controller=new AbortController();controller.abort();let calls=0;
 t.mock.method(globalThis,'fetch',async()=>{calls++;throw Error('not allowed');});
 await assert.rejects(reconcileWarehouseAudit('https://evidence.test',syntheticEvidence(),controller.signal),{name:'AbortError'});
 assert.equal(calls,0);
});
test('oversized streaming audit is cancelled before remaining bytes are consumed',async t=>{
 const evidence=syntheticEvidence(),{health}=syntheticAudit(evidence);let cancelled=false,pulls=0;
 const body=new ReadableStream({pull(controller){pulls++;controller.enqueue(new Uint8Array(1024*1024+1));},cancel(){cancelled=true;}},{highWaterMark:0});
 t.mock.method(globalThis,'fetch',async url=>url.endsWith('/healthz')?Response.json(health):new Response(body));
 await assert.rejects(reconcileWarehouseAudit('https://evidence.test',evidence,new AbortController().signal),/size limit/);
 assert.equal(cancelled,true);assert.equal(pulls,2);
});
test('invalid UTF-8 and oversized Content-Length are rejected',async t=>{
 const evidence=syntheticEvidence(),{health}=syntheticAudit(evidence);
 for(const response of [new Response(new Uint8Array([255,254])),new Response('{}',{headers:{'Content-Length':'999999999'}})]){
  const mock=t.mock.method(globalThis,'fetch',async url=>url.endsWith('/healthz')?Response.json(health):response);
  await assert.rejects(reconcileWarehouseAudit('https://evidence.test',evidence,new AbortController().signal));mock.mock.restore();
 }
});
