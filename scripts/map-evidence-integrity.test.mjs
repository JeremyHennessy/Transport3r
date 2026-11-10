import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const built=await build({stdin:{contents:"export * from './src/openGeography';export * from './src/snapshotSafety';export * from './src/eventGeography';export * from './src/RecentEventMap';export {createElement} from 'react';export {renderToStaticMarkup} from 'react-dom/server';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,platform:'node',format:'esm',banner:{js:"import{createRequire}from'node:module';const require=createRequire("+JSON.stringify(import.meta.url)+");"}});
const app=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const options={inspections:true,crashes:true,includeReporting:true,start:'',end:''};
const fixture=(row,kind='inspection')=>({dotNumber:'3706',mode:'summary',loadedAt:'2026-11-09T00:00:00Z',registry:{sources:[]},errors:{},slices:{
 inspections:{sourceId:'fx4q-ay7w',rows:kind==='inspection'?[row]:[],total:kind==='inspection'?1:0,truncated:false},
 crash:{sourceId:'aayw-vxb3',rows:kind==='crash'?[row]:[],total:kind==='crash'?1:0,truncated:false}}});
const record=()=>({dot_number:'3706',inspection_id:'10',insp_date:'20260102',county_code_state:'TX'});
for(const raw of [undefined,null,'',' ', '0','-3706','3706.0','1 OR 1=1','999']) {
 test(`missing or invalid carrier identity cannot enter map: ${String(raw)}`,()=>{
  const e=fixture({...record(),dot_number:raw});const before=JSON.stringify(e);
  const value=app.safetyGeography(e,options);
  assert.equal(value.rejected,1);assert.equal(value.mapped,0);assert.equal(value.considered,0);
  assert.equal(JSON.stringify(e),before);
 });
}
test('present padded USDOT alias is accepted without rewriting source values',()=>{
 const row={...record(),dot_number:undefined,USDOT_NUMBER:' 0003706 '};
 const value=app.safetyGeography(fixture(row),options);
 assert.equal(value.mapped,1);assert.equal(value.rejected,0);assert.equal(row.USDOT_NUMBER,' 0003706 ');
});
for(const kind of ['inspection','crash'])test(`${kind} daily dates do not guess MMDDYYYY`,()=>{
 const row=kind==='inspection'?{...record(),insp_date:'01022026'}:{dot_number:'3706',crash_id:'11',report_date:'01022026',state:'TX'};
 const e=fixture(row,kind),undated=app.safetyGeography(e,options);
 assert.equal(undated.invalidDates,1);assert.equal(undated.records[0].date,'');
 const dated=app.safetyGeography(e,{...options,start:'2026-01-01',end:'2026-01-31'});
 assert.equal(dated.mapped,0);assert.equal(dated.invalidDates,1);assert.equal(dated.outsideWindow,0);
});
for(const code of [undefined,'','ZZ','ON',' ca '])test(`fallback honors supported event-state membership: ${String(code)}`,()=>{
 const value=app.safetyGeography(fixture({...record(),county_code_state:code,report_state:' ny '}),options);
 const isEvent=code===' ca ';
 assert.equal(value.mapped,1);assert.equal(value.records[0].state,isEvent?'CA':'NY');
 assert.equal(value.records[0].precision,isEvent?'event state':'reporting jurisdiction');
 assert.equal(value.regions[0].reporting,isEvent?0:1);
 const excluded=app.safetyGeography(fixture({...record(),county_code_state:code,report_state:'NY'}),{...options,includeReporting:false});
 assert.equal(excluded.mapped,isEvent?1:0);assert.equal(excluded.reportingExcluded,isEvent?0:1);
});
test('unsupported event and reporting codes remain unlocated rather than falsely excluded',()=>{
 const value=app.safetyGeography(fixture({...record(),county_code_state:'ZZ',report_state:'ZZ'}),{...options,includeReporting:false});
 assert.equal(value.unlocated,1);assert.equal(value.reportingExcluded,0);assert.equal(value.mapped,0);
});
test('crash evidence does not invent a reporting-jurisdiction fallback absent from its contract',()=>{
 const value=app.safetyGeography(fixture({dot_number:'3706',crash_id:'11',report_date:'20260102',state:'ZZ',report_state:'TX'},'crash'),options);
 assert.equal(value.unlocated,1);assert.equal(value.mapped,0);
});
test('conflicting carrier aliases fail closed across all daily-map consumers',()=>{
 const row={...record(),USDOT_NUMBER:'999'};
 assert.equal(app.dailyCarrierMatches(row,'3706'),false);
 assert.equal(app.safetyGeography(fixture(row),options).mapped,0);
 const report={dot:'3706',window:{start:'2026-01-01',end:'2026-12-31'},sources:[{id:'fx4q-ay7w',slice:{rows:[row]}}]};
 assert.equal(app.eventGeography(report).events.length,0);
});
test('unknown source family cannot masquerade as daily inspections',()=>{
 const e=fixture(record());e.slices.inspections.sourceId='wrong-source';
 const result=app.safetyGeography(e,options);assert.equal(result.mapped,0);assert.deepEqual(result.unavailable,['inspections']);
});
test('legacy Atlas rendering also excludes rows without carrier identity',()=>{
 const html=app.renderToStaticMarkup(app.createElement(app.RecentEventMap,{evidence:fixture({...record(),dot_number:undefined})}));
 assert.match(html,/0 inspections/);assert.doesNotMatch(html,/TX: 1 loaded events/);
});
test('legacy Atlas rendering uses strict daily dates in retained drilldown records',()=>{
 const html=app.renderToStaticMarkup(app.createElement(app.RecentEventMap,{evidence:fixture({...record(),insp_date:'01022026'})}));
 assert.match(html,/1 unknown\/invalid dates/);
});
