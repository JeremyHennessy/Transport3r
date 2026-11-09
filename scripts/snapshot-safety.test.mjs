import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const built=await build({stdin:{contents:"export * from './src/snapshotSafety';export * from './src/reportModel';export * from './src/safetyWindow';export * from './src/eventGeography';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const selected={start:'2026-01-01',end:'2026-11-08'};
function fixture(){
 const slice=(sourceId,rows)=>({sourceId,rows,total:rows.length,truncated:false,scope:'carrier',acquiredAt:'2026-11-08T00:00:00Z',sourcePublication:JSON.stringify(['accepted-cut','b'.repeat(64),1])});
 return {dotNumber:'1',mode:'evidence',completeAll:true,loadedAt:'2026-11-09T00:00:00Z',registry:{sources:[]},census:{dot_number:'1',legal_name:'SYNTHETIC'},errors:{},slices:{
  inspections:slice('fx4q-ay7w',[{inspection_id:'1',dot_number:'1',insp_date:'20260101',county_code_state:'TX'},{inspection_id:'2',dot_number:'1',insp_date:'20261108',county_code_state:'TX'}]),
  crash:slice('aayw-vxb3',[])},
 completenessReceipt:{backend:'verified_nationwide_warehouse',status:'VERIFIED',cutId:'accepted-cut',cutAvailableAt:'2026-11-08T12:00:00Z',warehouseSha256:'a'.repeat(64),sourcesExpected:36,sourcesReturned:36}};
}
test('accepted daily window selects exact retained rows without any network request or mutation',t=>{
 t.mock.method(globalThis,'fetch',()=>{throw Error('Unexpected live request');});
 const e=fixture(),before=JSON.stringify(e),w=app.safetyWindowFromEvidence(e,selected);
 assert.equal(w.provenance.kind,'accepted_warehouse');assert.equal(w.sources[0].slice.total,2);
 assert.equal(w.sources[1].slice.total,0);assert.equal(w.sources[0].slice.rows[0],e.slices.inspections.rows[0]);
 assert.equal(w.acquiredAt,e.loadedAt);assert.equal(JSON.stringify(e),before);
 assert.doesNotThrow(()=>app.reportModel(e,w));assert.equal(app.reportArchive(e,w).window.provenance.warehouseSha256,'a'.repeat(64));
});
test('inclusive selection preserves source lineage and out-of-window accounting',()=>{
 const e=fixture(),w=app.safetyWindowFromEvidence(e,{start:'2026-11-08',end:'2026-11-08'});
 assert.equal(w.sources[0].slice.rows.length,1);assert.equal(w.sources[0].accounting.outsideWindow,1);
 assert.equal(w.sources[0].sourcePublication,e.slices.inspections.sourcePublication);
});
test('missing invalid future and foreign rows are counted without creating reassuring zeroes',()=>{
 const e=fixture();e.slices.inspections.rows.push({dot_number:'1'}, {dot_number:'1',insp_date:'20260230'},
 {dot_number:'1',insp_date:'20261109'}, {dot_number:'2',insp_date:'20260101'});e.slices.inspections.total=6;
 const w=app.safetyWindowFromEvidence(e,selected),s=w.sources[0];
 assert.deepEqual(s.accounting,{inputRows:6,selectedRows:2,outsideWindow:0,missingDates:1,invalidDates:1,afterCutDates:1,rejectedIdentities:1});
 assert.equal(s.slice.total,null);assert.equal(s.slice.truncated,true);
 assert.equal(app.reportModel(e,w).metrics.find(([label])=>label==='Window inspections')[1],'2+');
 assert.ok(app.windowMonths(s.slice).every(month=>!month.complete));
});
test('dates beyond the retained cut are explicitly incomplete, not a zero-event period',()=>{
 const w=app.safetyWindowFromEvidence(fixture(),{start:'2026-11-09',end:'2026-11-10'});
 assert.equal(w.provenance.windowExtendsBeyondCut,true);
 assert.equal(w.sources[0].slice.total,null);assert.equal(w.sources[0].slice.rows.length,0);
 assert.match(app.safetyProvenanceText(w),/later observations are unavailable/);
});
test('UTC boundary rather than timestamp text decides the last observable day',()=>{
 const e=fixture();e.completenessReceipt.cutAvailableAt='2026-11-08T23:30:00-04:00';
 e.slices.inspections.rows.push({dot_number:'1',insp_date:'20261109'});e.slices.inspections.total++;
 const w=app.safetyWindowFromEvidence(e,{start:'2026-11-09',end:'2026-11-09'});
 assert.equal(w.provenance.windowExtendsBeyondCut,false);assert.equal(w.sources[0].slice.total,1);
});
test('partial live evidence stays partial and never claims a verified warehouse',()=>{
 const e=fixture();delete e.completenessReceipt;e.completeAll=false;e.slices.inspections.truncated=true;
 const w=app.safetyWindowFromEvidence(e,selected);assert.equal(w.provenance.kind,'retained_evidence');
 assert.equal(w.provenance.cutId,null);assert.equal(w.sources[0].slice.total,null);
});
test('missing source remains unavailable instead of becoming an empty source',()=>{
 const e=fixture();delete e.slices.crash;
 const s=app.safetyWindowFromEvidence(e,selected).sources[1];assert.ok(s.error);assert.equal(s.slice,undefined);
});
for(const [label,mutate] of [
 ['cut',e=>e.slices.inspections.sourcePublication=JSON.stringify(['different','b'.repeat(64),1])],
 ['hash',e=>e.slices.inspections.sourcePublication=JSON.stringify(['accepted-cut','bad',1])],
 ['timestamp',e=>e.slices.inspections.sourcePublication=JSON.stringify(['accepted-cut','b'.repeat(64),-1])],
 ['count',e=>e.slices.inspections.total=999],['partial',e=>e.slices.inspections.truncated=true],
 ['source',e=>e.slices.inspections.sourceId='another'],
])test(`warehouse source fails closed on ${label} mismatch`,()=>{
 const e=fixture();mutate(e);const w=app.safetyWindowFromEvidence(e,selected);
 assert.ok(w.sources[0].error);assert.equal(w.sources[0].slice,undefined);
});
for(const [label,mutate] of [
 ['status',e=>e.completenessReceipt.status='PARTIAL'],['missing cut',e=>e.completenessReceipt.cutId=null],
 ['warehouse hash',e=>e.completenessReceipt.warehouseSha256='bad'],['incomplete',e=>e.completeAll=false],
 ['source coverage',e=>e.completenessReceipt.sourcesReturned=35],['timezone',e=>e.completenessReceipt.cutAvailableAt='2026-11-08'],
])test(`invalid accepted receipt rejects report: ${label}`,()=>{
 const e=fixture();mutate(e);assert.throws(()=>app.safetyWindowFromEvidence(e,selected));
});
for(const [label,mutate] of [
 ['cut',w=>w.provenance.cutId='different'],['rows',w=>w.sources[0].slice.rows[0].insp_date='20260102'],
 ['totals',w=>w.sources[0].slice.total=999],['duplicate source',w=>w.sources[1]=structuredClone(w.sources[0])],
 ['accounting',w=>w.sources[0].accounting.selectedRows=100],['date window',w=>w.sources[0].slice.eventWindow.end='2026-10-01'],
])test(`report and export both reject tampered ${label}`,()=>{
 const e=fixture(),w=structuredClone(app.safetyWindowFromEvidence(e,selected));mutate(w);
 assert.throws(()=>app.reportModel(e,w));assert.throws(()=>app.reportArchive(e,w));
});
test('archive can be serialized and checked again without relying on object reference identity',()=>{
 const e=fixture(),w=app.safetyWindowFromEvidence(e,selected),copy=JSON.parse(JSON.stringify(app.reportArchive(e,w)));
 assert.doesNotThrow(()=>app.reportModel(copy.evidence,copy.window));
});
test('strict daily dates reject wrong encoding and invalid calendar days',()=>{
 for(const value of ['02292024','20260229','20260230','2026-01-01','00000000',null,20260101])assert.equal(app.dailyCalendarDate(value),null);
 assert.equal(app.dailyCalendarDate('20240229'),'2024-02-29');
});
test('padded source USDOTs retain raw values but match the same carrier in maps',()=>{
 const e=fixture();e.slices.inspections.rows[0].dot_number='0001';
 const w=app.safetyWindowFromEvidence(e,selected);assert.equal(w.sources[0].slice.total,2);
 assert.equal(app.eventGeography(w).rejected,0);assert.equal(e.slices.inspections.rows[0].dot_number,'0001');
});
