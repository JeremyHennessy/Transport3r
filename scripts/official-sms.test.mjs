import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {readFile} from 'node:fs/promises';
const compiled=await build({entryPoints:['src/officialSms.ts'],bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const keys=['smsABProperty','smsCProperty','smsABPass','smsCPass'];
const ids=['4y6x-dmck','h9zy-gjn8','m3ry-qcip','h3zn-uid9'];
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const evidence=(outputs={},dot='1')=>({dotNumber:dot,errors:{},slices:Object.fromEntries(keys.map((key,i)=>[key,{sourceId:ids[i],rows:outputs[key]??[],truncated:false}]))});
test('public values retain zero and reject missing, malformed and nonnumeric sentinels',()=>{
  assert.equal(app.officialNumeric({v:'.24'},'v'),.24);
  assert.equal(app.officialNumeric({v:'0'},'v'),0);
  for(const v of ['',null,'NA','-1','1e2','4%'])assert.equal(app.officialNumeric({v},'v'),null);
  assert.equal(app.officialPercentile({v:'0%'},'v'),0);
  assert.equal(app.officialPercentile({v:'4%'},'v'),4);
  for(const v of ['101%','-1%','NA','%',''])assert.equal(app.officialPercentile({v},'v'),null);
});
test('real passenger fixtures expose published percentiles including zero',async()=>{
  const fixture=JSON.parse(await readFile('scripts/fixtures/sms-passenger-outputs.json','utf8')).carriers[0];
  const view=app.officialSmsView(evidence(fixture.outputs,fixture.dot_number));
  assert.equal(view.sourceId,fixture.expected_source);assert.equal(view.status,'available');
  assert.equal(view.basics[0].percentile,0);assert.equal(view.basics[4].percentile,4);
  assert.equal(view.basics[4].measure,.69);
});
test('missing rows, failed populations and partial replay inputs stay distinct',()=>{
  assert.equal(app.officialSmsView(evidence()).status,'empty');
  const ev=evidence({smsABProperty:[{dot_number:'1',veh_maint_measure:'0',veh_maint_pct:'99%'}]});
  ev.errors.smsInspection='failed';let view=app.officialSmsView(ev);
  assert.equal(view.status,'available');assert.equal(view.basics[4].measure,0);assert.equal(view.basics[4].percentile,null);
  ev.errors.smsCPass='failed';assert.equal(app.officialSmsView(ev).status,'unavailable');
});
test('batch uses four typed queries and safely isolates carrier values, duplicates and missing rows',async()=>{
  const original=globalThis.fetch,requests=[];
  globalThis.fetch=async input=>{const url=new URL(input);requests.push(url);return Response.json(url.pathname.includes(ids[0])?[{dot_number:'1',hos_driv_measure:'7'},{dot_number:'2',hos_driv_measure:'0'}]:[]);};
  try{
    const result=await app.loadOfficialSmsBatch(registry,['1','2','3','1']);
    assert.equal(requests.length,4);assert.ok(requests.every(url=>url.searchParams.get('$where')==="dot_number in ('1','2','3')"));
    assert.equal(app.officialSmsView(result['1']).basics[1].measure,7);
    assert.equal(app.officialSmsView(result['2']).basics[1].measure,0);
    assert.equal(app.officialSmsView(result['3']).status,'empty');
    globalThis.fetch=async input=>Response.json(String(input).includes(ids[0])?[{dot_number:'1'},{dot_number:'1'}]:[]);
    assert.equal(app.officialSmsView((await app.loadOfficialSmsBatch(registry,['1']))['1']).status,'unavailable');
    globalThis.fetch=async()=>Response.json([{dot_number:'999'}]);
    assert.equal(app.officialSmsView((await app.loadOfficialSmsBatch(registry,['1']))['1']).status,'unavailable');
    await assert.rejects(app.loadOfficialSmsBatch(registry,["1' OR true"]));
  }finally{globalThis.fetch=original;}
});
