import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const result=await build({stdin:{contents:"export * from './src/evidenceCoverage'; export * from './src/carrierEvidence';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
const slice=(rows=[],extra={})=>({sourceId:'fx4q-ay7w',rows,total:null,truncated:false,scope:'carrier',...extra});
const ev=(slices={},errors={})=>({dotNumber:'1',mode:'safety',loadedAt:'2026-09-09T12:00:00Z',registry:{sources:[],generated_at:'2026-09-01T00:00:00Z'},slices,errors});
test('coverage distinguishes successful empty, partial empty and unavailable without inventing zeros',()=>{
 const report=app.coverageRows(ev({inspections:slice(),violations:slice([],{truncated:true})},{crash:'HTTP 503'}));
 assert.deepEqual(report.map(r=>r.status),['empty','partial','unavailable','unavailable','unavailable']);
 assert.equal(report[0].requestTotal,0);assert.equal(report[1].requestTotal,null);assert.equal(report.at(-1).loaded,null);
});
test('carrier totals and dependent window totals remain scoped and capped independently',()=>{
 const report=app.coverageRows(ev({inspections:slice([{insp_date:'20260101'}],{total:1500,truncated:true}),violations:slice([],{scope:'loaded_inspections'})}));
 assert.equal(report[0].requestTotal,1500);assert.equal(report[0].loaded,1);assert.equal(report[0].status,'partial');
 assert.equal(report[1].scope,'loaded_inspections');assert.equal(report[1].acquiredAt,null);
});
test('ranges reject conflicting or invalid dates while sparse valid history is preserved',()=>{
 const range=app.loadedDateRange([{insp_date:'20260101'},{insp_date:'20260901'},{insp_date:'20260230'},{},{insp_date:'20260101',inspection_date:'20260102'}],['INSP_DATE','INSPECTION_DATE']);
 assert.deepEqual(range,{start:'2026-01-01',end:'2026-09-01',valid:2,missing:1,invalid:1,conflicting:1});
});
test('export keeps old acquisition and catalog dates separate and exposure warnings reproducible',()=>{
 const evidence=ev({inspections:slice([{insp_date:'20260901'}],{acquiredAt:'2026-09-02T00:00:00Z'})});
 const report=app.coverageReport(evidence,{mcs150_date:'20160101',status_code:'I',total_drivers:'0'});
 assert.equal(report.sources[0].acquiredAt,'2026-09-02T00:00:00Z');assert.equal(report.sources[0].metadataCapturedAt,'2026-09-01T00:00:00Z');
 assert.equal(report.exposure.drivers,'0');assert.equal(report.exposure.powerUnits,null);assert.equal(report.exposure.reviewNotes.length,2);assert.equal(report.riskScore,null);
});
