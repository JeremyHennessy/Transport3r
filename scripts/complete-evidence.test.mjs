import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';
const compiled=await build({stdin:{contents:"export * from './src/completeEvidence';export * from './src/CompleteData';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const signal=()=>new AbortController().signal;
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
test('full result preserves explicit errors and marks fallback previews partial',()=>{
 const preview={dotNumber:'1',slices:{inspections:{rows:[{}],truncated:false}},errors:{}},full={dotNumber:'1',slices:{},errors:{inspections:'HTTP 503'},completeAll:false};
 const merged=app.mergeComplete(preview,full,'safety');assert.equal(merged.completeAttempted,true);assert.equal(merged.slices.inspections.truncated,true);assert.equal(merged.completeAll,false);
});
