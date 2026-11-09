import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const built=await build({stdin:{contents:"export * from './src/vinUnitEvidence';export * from './src/inspectionEvidence';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {vinUnitEvidence,observedVinRows}=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const VIN='3C63RRGLXNG286232',OTHER='3C63RRGLXPG628183';
function fixture(){
 const slice=(sourceId,rows)=>({sourceId,rows,total:rows.length,truncated:false,acquiredAt:'2026-11-09T00:00:00Z',sourcePublication:'retained-fixture'});
 return {dotNumber:'1',loadedAt:'2026-11-09T00:00:00Z',errors:{},slices:{
  inspections:slice('fx4q-ay7w',[{inspection_id:'10',dot_number:'1',insp_date:'20260101'},{inspection_id:'20',dot_number:'1',insp_date:'20260201'}]),
  units:slice('wt8s-2hbx',[{inspection_id:'10',insp_unit_id:'101',insp_unit_number:'1',insp_unit_vehicle_id_number:VIN},
   {inspection_id:'10',insp_unit_id:'102',insp_unit_number:'2',insp_unit_vehicle_id_number:OTHER},
   {inspection_id:'20',insp_unit_id:'201',insp_unit_number:'1',insp_unit_vehicle_id_number:VIN}]),
  violations:slice('876r-jsdb',[{inspection_id:'10',insp_violation_id:'1001',insp_unit_id:'101',insp_viol_unit:'1',viol_code:'393.9',out_of_service_indicator:'Y',defect_verification_id:'99'},
   {inspection_id:'10',insp_violation_id:'1002',insp_unit_id:'102',insp_viol_unit:'2',viol_code:'393.75',out_of_service_indicator:'N'},
   {inspection_id:'20',insp_violation_id:'1003',insp_unit_id:'201',insp_viol_unit:'1',viol_code:'393.9'}])}};
}
function conserve(result){assert.equal(result.linked.length+result.otherVinRows+result.unassignedRows+result.duplicateRows,result.inputRows);}
test('vehicle findings use inspection plus unit ID and do not fan trailer findings onto tractor',()=>{
 const e=fixture(),before=JSON.stringify(e),r=vinUnitEvidence(e,VIN.toLowerCase());
 assert.deepEqual(r.linked.map(x=>x.id),['1001','1003']);assert.equal(r.otherVinRows,1);assert.equal(r.unassignedRows,0);
 assert.equal(r.linked[0].method,'unit_id');assert.equal(r.linked[0].defectVerificationCode,'99');
 assert.equal(r.linked[0].outOfService,true);assert.equal(r.linked[1].outOfService,null);
 assert.equal(r.linked[0].sourcePublication,'retained-fixture');
 assert.deepEqual(r.repeatedCodes,[{code:'393.9',inspectionCount:2}]);assert.equal(r.repairStatusEstablished,false);
 assert.equal(r.recallStatusEstablished,false);assert.equal(JSON.stringify(e),before);conserve(r);
});
test('unit-number fallback requires unique same-inspection units and complete lookup',()=>{
 const e=fixture();delete e.slices.violations.rows[0].insp_unit_id;
 const r=vinUnitEvidence(e,VIN);assert.equal(r.linked[0].method,'unique_unit_number');conserve(r);
 e.slices.units.truncated=true;const partial=vinUnitEvidence(e,VIN);
 assert.equal(partial.reasons.INCOMPLETE_UNIT_NUMBER_LOOKUP,1);assert.equal(partial.partial,true);conserve(partial);
});
for(const [name,mutate,reason] of [
 ['foreign parent',e=>e.slices.inspections.rows[0].dot_number='2','UNVERIFIED_INSPECTION_PARENT'],
 ['ambiguous parent',e=>e.slices.inspections.rows.push({...e.slices.inspections.rows[0],dot_number:'2'}),'UNVERIFIED_INSPECTION_PARENT'],
 ['missing parent',e=>e.slices.inspections.rows.shift(),'UNVERIFIED_INSPECTION_PARENT'],
 ['foreign violation',e=>e.slices.violations.rows[0].dot_number='2','CONFLICTING_CARRIER_ID'],
 ['foreign unit',e=>e.slices.units.rows[0].dot_number='2','CONFLICTING_UNIT_CARRIER'],
 ['missing explicit unit',e=>e.slices.violations.rows[0].insp_unit_id='999','UNIT_REFERENCE_NOT_FOUND'],
 ['invalid explicit unit',e=>e.slices.violations.rows[0].insp_unit_id='invalid','INVALID_EXPLICIT_UNIT_ID'],
 ['other inspection unit ID',e=>e.slices.violations.rows[0].insp_unit_id='201','UNIT_REFERENCE_NOT_FOUND'],
 ['conflicting number',e=>e.slices.violations.rows[0].insp_viol_unit='2','CONFLICTING_UNIT_REFERENCES'],
 ['duplicate unit ID',e=>e.slices.units.rows.push({...e.slices.units.rows[0]}),'AMBIGUOUS_UNIT_REFERENCE'],
 ['invalid unit VIN',e=>e.slices.units.rows[0].insp_unit_vehicle_id_number='UNKNOWN','MISSING_OR_INVALID_UNIT_VIN'],
 ['missing violation identity',e=>delete e.slices.violations.rows[0].insp_violation_id,'MISSING_VIOLATION_ID'],
])test(`does not attribute ${name}`,()=>{
 const e=fixture();mutate(e);const r=vinUnitEvidence(e,VIN);
 assert.ok(r.reasons[reason]>0);assert.ok(!r.linked.some(row=>row.id==='1001'));conserve(r);
});
test('driver-only or unspecified unit cannot be converted into a vehicle finding',()=>{
 const e=fixture();delete e.slices.violations.rows[0].insp_unit_id;e.slices.violations.rows[0].insp_viol_unit='D';
 const r=vinUnitEvidence(e,VIN);assert.equal(r.reasons.NO_SUPPORTED_VEHICLE_REFERENCE,1);conserve(r);
});
test('conflicting explicit ID never falls back to an otherwise matching unit number',()=>{
 const e=fixture();e.slices.violations.rows[0].insp_unit_id='102';
 const r=vinUnitEvidence(e,VIN);assert.equal(r.reasons.CONFLICTING_UNIT_REFERENCES,1);conserve(r);
});
test('reused unit number is ambiguous even when another candidate has missing VIN',()=>{
 const e=fixture();delete e.slices.violations.rows[0].insp_unit_id;
 e.slices.units.rows.push({inspection_id:'10',insp_unit_number:'1'});
 const r=vinUnitEvidence(e,VIN);assert.equal(r.reasons.AMBIGUOUS_UNIT_REFERENCE,1);conserve(r);
});
test('exact duplicate observations are accounted for; conflicts reject all candidates',()=>{
 const e=fixture();e.slices.violations.rows.push({...e.slices.violations.rows[0]});
 const r=vinUnitEvidence(e,VIN);assert.equal(r.duplicateRows,1);assert.equal(r.linked.length,2);conserve(r);
 e.slices.violations.rows.at(-1).out_of_service_indicator='N';const conflict=vinUnitEvidence(e,VIN);
 assert.equal(conflict.reasons.CONFLICTING_VIOLATION_ID,2);assert.equal(conflict.duplicateRows,0);
 assert.ok(!conflict.linked.some(row=>row.id==='1001'));conserve(conflict);
});
test('failure or missing source is not displayed as zero defects',()=>{
 for(const kind of ['missing','failed','wrong-source']){
  const e=fixture();if(kind==='missing')delete e.slices.violations;
  else if(kind==='failed')e.errors.violations='upstream unavailable';else e.slices.violations.sourceId='sms';
  const r=vinUnitEvidence(e,VIN);assert.equal(r.sourceAvailable,false);assert.equal(r.inputRows,null);
  assert.equal(r.partial,true);assert.equal(r.linked.length,0);
 }
});
test('unknown OOS and defect codes remain unknown rather than implying repaired or clear',()=>{
 const e=fixture();e.slices.violations.rows[0].out_of_service_indicator='unexpected';
 e.slices.violations.rows[0].defect_verification_id='unexpected';
 const r=vinUnitEvidence(e,VIN);assert.equal(r.linked[0].outOfService,null);
 assert.equal(r.linked[0].defectVerificationCode,'unexpected');assert.equal(r.repairStatusEstablished,false);
});
test('invalid requested VIN cannot match all missing identifiers',()=>{
 for(const vin of ['', 'UNKNOWN',"' OR true",'3C63RRGLXNG28623I']){
  const r=vinUnitEvidence(fixture(),vin);assert.equal(r.vin,null);assert.equal(r.linked.length,0);conserve(r);
 }
});
test('one parent shared by foreign and matching carrier is ambiguous for observed VIN rows too',()=>{
 const e=fixture();e.slices.inspections.rows.push({...e.slices.inspections.rows[0],dot_number:'2'});
 const r=observedVinRows(e,VIN);assert.ok(!r.rows.some(row=>row.inspectionId==='10'));assert.equal(r.rejected,1);
});
test('source IDs and source fields are not modified to force a match',()=>{
 const e=fixture();e.slices.units.rows[0].insp_unit_id='00101';e.slices.violations.rows[0].insp_viol_unit='01';
 const before=JSON.stringify(e);const r=vinUnitEvidence(e,VIN);assert.equal(r.linked.length,2);
 assert.equal(JSON.stringify(e),before);conserve(r);
});
