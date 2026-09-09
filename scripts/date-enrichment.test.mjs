import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {build} from 'esbuild';
const compiled=await build({stdin:{contents:"export * from './src/eventWindow';export * from './src/datahub';export * from './src/safetyWindow';export * from './src/vinSpecifications';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const window={start:'2024-02-01',end:'2024-02-29'},vin='3C63RRGLXPG628183';
test('date windows reject invalid, reversed, excessive and injected dates',()=>{
 for(const selected of [{start:'2023-02-29',end:'2023-03-01'},{start:'2024-03-01',end:'2024-02-29'},{start:'2020-01-01',end:'2024-01-01'},{start:"2024-01-01' OR true",end:'2024-02-01'}])assert.throws(()=>app.validateEventWindow(selected));
 assert.deepEqual(app.validateEventWindow(window),window);
});
test('date row and count queries share inclusive source-side bounds',async t=>{
 const calls=[];t.mock.method(globalThis,'fetch',async input=>{const url=new URL(input);calls.push(url);return Response.json(url.searchParams.has('$select')?[{count:'1'}]:[{dot_number:'1',insp_date:'20240229',inspection_id:'2'}]);});
 const slice=await app.queryByDot(registry,'fx4q-ay7w','1',{eventWindow:window,includeTotal:true});
 assert.equal(slice.total,1);assert.deepEqual(slice.eventWindow,window);assert.equal(calls.length,2);
 for(const url of calls)assert.equal(url.searchParams.get('$where'),"dot_number=1 AND insp_date between '20240201' and '20240229'");
});
test('date windows reject SMS text encoding and unrelated or invalid daily rows',async t=>{
 await assert.rejects(app.queryByDot(registry,'rbkj-cgst','1',{eventWindow:window}),/No verified date-window mapping/);
 for(const row of [{dot_number:'2',insp_date:'20240215'},{dot_number:'1',insp_date:'20240230'},{dot_number:'1',insp_date:'20240301'}]){
  t.mock.method(globalThis,'fetch',async()=>Response.json([row]));await assert.rejects(app.queryByDot(registry,'fx4q-ay7w','1',{eventWindow:window}),/invalid date or unrelated/);t.mock.restoreAll();
 }
});
test('monthly empty cells stay lower bounds when detail is partial',()=>{
 const rows=app.windowMonths({sourceId:'fx4q-ay7w',rows:[{insp_date:'20240229'}],eventWindow:{start:'2024-01-15',end:'2024-03-02'},truncated:true,total:5000});
 assert.deepEqual(rows.map(r=>[r.month,r.loaded,r.complete]),[['2024-01',0,false],['2024-02',1,false],['2024-03',0,false]]);
});
test('changed source fails independently without turning errors into empty counts',async t=>{
 const reads={};t.mock.method(globalThis,'fetch',async input=>{const url=new URL(input),id=url.pathname.split('/').at(-1).replace('.json','');if(url.pathname.includes('/api/views/')){reads[id]=(reads[id]??0)+1;return Response.json({id,rowsUpdatedAt:id==='fx4q-ay7w'?reads[id]:1,viewLastModified:1});}return Response.json(url.searchParams.has('$select')?[{count:'0'}]:[]);});
 const result=await app.loadSafetyWindow(registry,'1',window);
 assert.match(result.sources[0].error,/Source changed/);assert.equal(result.sources[0].slice,undefined);assert.equal(result.sources[1].slice.total,0);
});
test('VIN decoder retains warning codes and does not invent missing specifications',()=>{
 const result=app.decodeSpecification({Results:[{VIN:vin,ErrorCode:'1',ErrorText:'Check digit',Model:'3500',GVWR:''}]},vin);
 assert.equal(result.warning,true);assert.equal(result.message,'Check digit');assert.deepEqual(result.fields,[{key:'Model',label:'Model',value:'3500'}]);
 assert.equal(app.decodeSpecification({Results:[{VIN:vin,ErrorCode:'0',ModelYear:'2023'}]},vin).warning,false);
});
test('VIN decoder rejects foreign, ambiguous, missing status and malformed identities',()=>{
 for(const Results of [[],[{},{}],[{VIN:'3AKJHHDR1NCMS1700',ErrorCode:'0'}],[{VIN:vin}]])assert.throws(()=>app.decodeSpecification({Results},vin));
 for(const value of ['PARTIAL','3C63RRGLXPG62818I',"';DROP TABLE"])assert.throws(()=>app.normalizedVin(value));
});
test('VIN lookup transmits only normalized observed VIN and retains provenance',async t=>{
 let requested;t.mock.method(globalThis,'fetch',async input=>{requested=String(input);return Response.json({Results:[{VIN:vin,ErrorCode:'0',Make:'RAM'}]});});
 const result=await app.loadVinSpecifications(vin.toLowerCase());assert.equal(requested,`https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/${vin}?format=json`);assert.equal(result.url,requested);assert.ok(result.acquiredAt);
});
