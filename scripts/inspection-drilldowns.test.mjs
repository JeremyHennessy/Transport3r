import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';

const compiled = await build({stdin:{contents:"export * from './src/inspectionEvidence';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const {loadInspectionEvidence,observedVinRows} = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const parent={inspection_id:'900001',dot_number:'1',insp_date:'20230901',report_number:'OLD-REPORT'};
const unit={inspection_id:'900001',insp_unit_vehicle_id_number:'3C63RRGLXNG286232'};

function mock(t,records={},failed){
  const calls=[];
  t.mock.method(globalThis,'fetch',async input=>{
    const url=new URL(String(input),'http://local');
    if(url.pathname.endsWith('source-schemas.json'))return Response.json(registry);
    const sid=url.pathname.split('/').at(-1).replace('.json','');calls.push({sid,where:url.searchParams.get('$where')});
    if(sid===failed)return new Response('',{status:503});
    const rows=records[sid]??[];const offset=Number(url.searchParams.get('$offset')??0),limit=Number(url.searchParams.get('$limit'));
    return Response.json(rows.slice(offset,offset+limit));
  });
  return calls;
}

test('direct lookup queries a deep inspection ID and all four child families',async t=>{
  const calls=mock(t,{'fx4q-ay7w':[parent],'wt8s-2hbx':[unit]});
  const e=await loadInspectionEvidence('1','900001');
  assert.deepEqual(e.errors,{});assert.equal(e.inspectionId,'900001');
  assert.equal(e.slices.units.rows.length,1);assert.equal(e.slices.inspections.scope,'inspection');
  assert.equal(calls.length,5);assert.ok(calls.every(c=>c.where.includes('900001')));
  assert.equal(e.slices.specialStudies.total,0);
});

test('unrelated carrier parent is hidden and children are never queried',async t=>{
  const calls=mock(t,{'fx4q-ay7w':[{...parent,dot_number:'2'}]});
  const e=await loadInspectionEvidence('1','900001');
  assert.match(e.errors.inspections,/does not belong/);assert.equal(e.slices.inspections,undefined);assert.equal(calls.length,1);
});

test('missing or ambiguous parent preserves unavailable child evidence',async t=>{
  for(const rows of [[],[parent,parent]]){
    const calls=mock(t,{'fx4q-ay7w':rows});
    const e=await loadInspectionEvidence('1','900001');
    assert.equal(calls.length,1);assert.match(e.errors.units,/Parent inspection/);assert.equal(e.slices.units,undefined);
    t.mock.restoreAll();
  }
});

test('failed and unrelated child sources cannot masquerade as empty success',async t=>{
  mock(t,{'fx4q-ay7w':[parent],'wt8s-2hbx':[{...unit,inspection_id:'999'}]},'876r-jsdb');
  const e=await loadInspectionEvidence('1','900001');
  assert.match(e.errors.units,/unrelated/);assert.match(e.errors.violations,/503/);
  assert.equal(e.slices.units,undefined);assert.equal(e.slices.violations,undefined);
  assert.equal(e.slices.citations.total,0);
});

test('large child response is explicitly partial at its bound',async t=>{
  mock(t,{'fx4q-ay7w':[parent],'876r-jsdb':Array.from({length:5001},()=>({inspection_id:'900001'}))});
  const e=await loadInspectionEvidence('1','900001');
  assert.equal(e.slices.violations.rows.length,5000);assert.equal(e.slices.violations.truncated,true);assert.equal(e.slices.violations.total,null);
});

test('VIN observations require a matching unambiguous parent in the same carrier',()=>{
  const slice=rows=>({rows,truncated:false});
  const e={dotNumber:'1',errors:{},slices:{inspections:slice([parent]),units:slice([unit,{...unit,inspection_id:'999'},{...unit,dot_number:'2'}])}};
  const r=observedVinRows(e,unit.insp_unit_vehicle_id_number.toLowerCase());
  assert.equal(r.rows.length,1);assert.equal(r.rejected,2);
  e.slices.inspections.rows.push(parent);
  assert.equal(observedVinRows(e,unit.insp_unit_vehicle_id_number).rows.length,0);
});

test('invalid inspection route identifiers issue no source request',async t=>{
  const calls=mock(t);
  await assert.rejects(()=>loadInspectionEvidence('1',"1 OR 1=1"),/identifiers/);
  assert.equal(calls.length,0);
});
