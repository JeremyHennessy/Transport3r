import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';
const compiled=await build({stdin:{contents:"export * from './src/completeEvidence';export * from './src/CompleteData';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"','import.meta.env.VITE_EVIDENCE_API_URL':'""'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const signal=()=>new AbortController().signal;
test('complete daily records keep recent-event summaries newest first without losing undated rows',()=>{const rows=[{insp_date:'20240101'},{insp_date:'20260901'},{other:'undated'}];assert.deepEqual(app.recentDailyRows('fx4q-ay7w',rows),[rows[1],rows[0],rows[2]]);assert.deepEqual(rows[0],{insp_date:'20240101'});});
function fixture(t,{total=5001,change=false,bad=false,duplicate=false,early=false}={}){
 let publications=0;const offsets=[];
 t.mock.method(globalThis,'fetch',async input=>{const url=new URL(input),id=url.pathname.split('/').at(-1).replace('.json','');
  if(url.pathname.includes('/api/views/'))return Response.json({id,tableId:1,columns:[],rowsUpdatedAt:change?++publications:1});
  if(url.searchParams.get('$select').includes('count'))return Response.json([{count:String(total)}]);
  const offset=Number(url.searchParams.get('$offset'));offsets.push(offset);
  return Response.json(early&&offset?[]:Array.from({length:Math.min(5000,total-offset)},(_,i)=>({dot_number:bad?'2':'1',transport_row_id:String(duplicate?i:offset+i)})));
 });return offsets;
}
test('complete pagination loads beyond old 500 and 5000 row caps with stable identities',async t=>{const offsets=fixture(t);const result=await app.completeQuery('fx4q-ay7w',['dot_number=1'],r=>r.dot_number==='1',signal());assert.equal(result.rows.length,5001);assert.equal(result.total,5001);assert.equal(result.truncated,false);assert.deepEqual(offsets,[0,5000]);assert.ok(!('transport_row_id' in result.rows[0]));});
for(const [name,options,pattern] of [['publication changes',{change:true},/changed/],['foreign carrier',{bad:true},/identity/],['repeated row identity',{duplicate:true},/identity/],['early end of source',{early:true},/pagination/]])test(`complete acquisition rejects ${name}`,async t=>{fixture(t,options);await assert.rejects(app.completeQuery('fx4q-ay7w',['dot_number=1'],r=>r.dot_number==='1',signal()),pattern);});
test('empty source is verified as zero without a fictitious row request',async t=>{const offsets=fixture(t,{total:0});const result=await app.completeQuery('fx4q-ay7w',['dot_number=1'],()=>true,signal());assert.equal(result.total,0);assert.deepEqual(offsets,[]);});
test('all 36 carrier sources complete with exact padded DOT and parent joins',async t=>{
 const queried=[];
 t.mock.method(globalThis,'fetch',async input=>{
  if(String(input).includes('source-schemas.json'))return Response.json(registry);
  const url=new URL(input),id=url.pathname.split('/').at(-1).replace('.json','');
  if(url.pathname.includes('/api/views/'))return Response.json({id,tableId:1,columns:[],rowsUpdatedAt:1});
  const where=url.searchParams.get('$where');queried.push({id,where});
  const rows=id==='az4n-8mr2'?[{dot_number:'3706'}]:id==='fx4q-ay7w'?[{dot_number:'3706',inspection_id:'7'}]:id==='wt8s-2hbx'?[{inspection_id:'7'}]:id==='6eyk-hxee'?[{dot_number:'00003706',docket_number:'MC00123'}]:id==='ypjt-5ydn'?[{prefix_docket_number:'MC00123'}]:[];
  return Response.json(url.searchParams.get('$select').includes('count')?[{count:String(rows.length)}]:rows.map((r,i)=>({...r,transport_row_id:`${id}:${i}`})));
 });
 const full=await app.acquireCompleteCarrier('3706',signal());assert.deepEqual(full.errors,{});assert.equal(Object.keys(full.slices).length,36);assert.equal(full.completeAll,true);assert.equal(full.slices.units.rows.length,1);assert.ok(queried.some(q=>q.where==="dot_number in ('3706','00003706')"));assert.ok(queried.some(q=>q.where==="prefix_docket_number in ('MC00123')"));
});
test('verified warehouse adapter requires one Census identity, all 36 sources and a receipt',async t=>{
 const sources=registry.sources.map(source=>({source_id:source.id,carrier_rows:source.id==='az4n-8mr2'?1:0,status:source.id==='az4n-8mr2'?'ROWS_RETURNED':'NO_ROWS_RETURNED',scope:'ALL_RESOLVED_ROWS_FOR_USDOT_IN_VERIFIED_NATIONWIDE_CUT',source_available_at:'2026-10-23T00:00:00Z',source_rows_updated_at:1,source_sha256:'b'.repeat(64),rows:source.id==='az4n-8mr2'?[{dot_number:'3706'}]:[]}));
 const payload={dot_number:'3706',cut_id:'cut-1',cut_available_at:'2026-10-23T00:00:00Z',identity_contract:'FMCSA_CARRIER_IDENTITY_1',source_count:36,carrier_rows:1,warehouse_sha256:'a'.repeat(64),sources,completeness_receipt:{status:'VERIFIED',sources_expected:36,sources_returned:36,unresolved_rows_excluded_from_carrier_assignment:true,mapping_totals:{resolved:100,identified_only:2,unresolved:3},sms_release_binding:'UNVERIFIED',historical_feature_validity:'NOT_CERTIFIED'}};
 const progress=[];t.mock.method(globalThis,'fetch',async input=>String(input).includes('source-schemas.json')?Response.json(registry):Response.json(payload));
 const result=await app.acquireWarehouseCarrier('3706',signal(),value=>progress.push(value),'https://warehouse.example');
 assert.equal(result.completeAll,true);assert.equal(result.slices.census.rows.length,1);assert.equal(result.completenessReceipt.status,'VERIFIED');assert.equal(result.completenessReceipt.unresolvedRowsExcluded,true);assert.deepEqual(result.completenessReceipt.mappingTotals,{resolved:100,identifiedOnly:2,unresolved:3});assert.equal(progress.at(-1).cutId,'cut-1');
});
test('warehouse adapter rejects a valid-looking receipt with inconsistent aggregate rows',async t=>{
 const sources=registry.sources.map(source=>({source_id:source.id,carrier_rows:source.id==='az4n-8mr2'?1:0,status:source.id==='az4n-8mr2'?'ROWS_RETURNED':'NO_ROWS_RETURNED',scope:'ALL_RESOLVED_ROWS_FOR_USDOT_IN_VERIFIED_NATIONWIDE_CUT',source_available_at:'2026-10-23T00:00:00Z',source_rows_updated_at:1,source_sha256:'b'.repeat(64),rows:source.id==='az4n-8mr2'?[{dot_number:'3706'}]:[]}));
 const payload={dot_number:'3706',cut_id:'cut-1',cut_available_at:'2026-10-23T00:00:00Z',identity_contract:'FMCSA_CARRIER_IDENTITY_1',source_count:36,carrier_rows:2,warehouse_sha256:'a'.repeat(64),sources,completeness_receipt:{status:'VERIFIED',sources_expected:36,sources_returned:36,unresolved_rows_excluded_from_carrier_assignment:true,mapping_totals:{resolved:1,identified_only:0,unresolved:0},sms_release_binding:'UNVERIFIED',historical_feature_validity:'NOT_CERTIFIED'}};
 t.mock.method(globalThis,'fetch',async input=>String(input).includes('source-schemas.json')?Response.json(registry):Response.json(payload));
 await assert.rejects(app.acquireWarehouseCarrier('3706',signal(),()=>{},'https://warehouse.example'),/carrier total/);
});
test('full result preserves explicit errors and marks fallback previews partial',()=>{
 const preview={dotNumber:'1',slices:{inspections:{rows:[{}],truncated:false}},errors:{}},full={dotNumber:'1',slices:{},errors:{inspections:'HTTP 503'},completeAll:false};
 const merged=app.mergeComplete(preview,full,'safety');assert.equal(merged.completeAttempted,true);assert.equal(merged.slices.inspections.truncated,true);assert.equal(merged.completeAll,false);
});
