import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const code=await build({stdin:{contents:"export * from './src/reportModel';export * from './src/insightModel';export * from './src/eventGeography';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(code.outputFiles[0].text).toString('base64')}`);
const window={dot:'1',window:{start:'2026-01-01',end:'2026-09-09'},acquiredAt:'2026-09-09',sources:[]};
const ev={dotNumber:'1',mode:'summary',loadedAt:'2026-09-09',census:{dot_number:'1',legal_name:'Carrier <test>',power_units:'0',total_drivers:'0'},registry:{sources:[]},slices:{},errors:{}};
test('brief retains zero exposure and missing activity and rejects mixed carrier identity',()=>{
 const model=app.reportModel(ev,window);assert.equal(model.metrics[0][1],'0');assert.equal(model.metrics[4][1],'Unavailable');assert.ok(model.view.limitation.includes('unavailable'));
 assert.throws(()=>app.reportModel(ev,{...window,dot:'2'}));assert.throws(()=>app.reportModel({...ev,census:{dot_number:'2'}},window));
});
test('geography never substitutes carrier or license state for event location',()=>{
 const geo=app.eventGeography({...window,sources:[{id:'fx4q-ay7w',slice:{rows:[{dot_number:'1',inspection_id:'10',county_code_state:'TX',report_state:'OK'},{dot_number:'1',inspection_id:'11',report_state:'CA'},{dot_number:'2',inspection_id:'12',report_state:'CA'}]}},{id:'aayw-vxb3',slice:{rows:[{dot_number:'1',crash_id:'20',state:'VA'},{dot_number:'1',crash_id:'21',crash_carrier_state:'TX',vehicle_lic_state:'TX',report_state:'TX'}]}}]});
 assert.equal(geo.rejected,1);assert.equal(geo.unlocated,1);assert.deepEqual(geo.events.map(e=>e.state),['TX','CA','VA']);assert.equal(geo.events[1].precision,'reporting jurisdiction only');assert.equal(geo.events[0].id,'10');
});
test('timeline uses explicit lifecycle event dates and retains source classes',()=>{
 const events=app.evidenceTimeline({...ev,slices:{motusAuthHistory:{rows:[{status_change_date:'20260801',op_auth_status:'REVOKED',change_date:'20260909'}]},motusInsuranceHistory:{rows:[{effective_date:'20260101',cancl_effective_date:'20260731',filing_status_reason:'replaced'}]}}},['motusAuthHistory','motusInsuranceHistory']);
 assert.equal(events.length,3);assert.equal(events[0].date,'2026-08-01');assert.ok(!events.some(e=>e.date==='2026-09-09'));
});
test('unavailable sources do not enter charts and unknown OOS flags remain unknown',()=>{
 assert.equal(app.dailyActivity({...ev,errors:{inspections:'failed'},slices:{inspections:{rows:[{insp_date:'20260101'}]}}},'inspections'),null);
 const oos=app.oosLoaded({...ev,slices:{violations:{rows:[{out_of_service_indicator:'Y'},{out_of_service_indicator:''},{out_of_service_indicator:'N'}],truncated:true}}});assert.deepEqual(oos,{yes:1,unknown:1,partial:true});
});
