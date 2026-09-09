import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {readFile} from 'node:fs/promises';
const compiled=await build({stdin:{contents:"export * from './src/carrierEvidence'; export * from './src/smsReplay';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const row=(extra={})=>({dot_number:'1',hos_driv_measure:'.5',...extra});
const slice=(rows=[])=>({rows,total:rows.length,truncated:false,sourceId:'test'});
const evidence=(rows={})=>({dotNumber:'1',errors:{},slices:{...Object.fromEntries(app.SMS_OUTPUT_KEYS.map(key=>[key,slice(rows[key])])),smsInspection:slice([{dot_number:'1',unique_id:'i',insp_date:'15-MAY-26',fatigued_insp:'true',time_weight:'2'}]),smsViolation:slice([{dot_number:'1',unique_id:'i',insp_date:'15-MAY-26',basic_desc:'Hours-of-Service Compliance',time_weight:'2',total_severity_wght:'0.5'}])}});
test('general output is selected only after all populations have completed',()=>{
  const ev=evidence({smsABProperty:[row()]});
  assert.equal(app.officialSmsSourceId(ev),'4y6x-dmck');
  assert.equal(app.replayCarrierInspectionMeasures(ev)[0].status,'MATCH');
  delete ev.slices.smsCPass;
  assert.equal(app.officialSmsSourceId(ev),null);
  const replay=app.replayCarrierInspectionMeasures(ev)[0];
  assert.equal(replay.status,'PARTIAL_DATA'); assert.equal(replay.officialMeasure,null);
  assert.equal(replay.calculatedMeasure,.5); assert.equal(app.replaySummary([replay]).validationCandidates,0);
});
test('passenger-specific AB and C rows win over their overlapping general rows',()=>{
  for(const [general,passenger,id] of [['smsABProperty','smsABPass','m3ry-qcip'],['smsCProperty','smsCPass','h3zn-uid9']]) {
    const ev=evidence({[general]:[row({hos_driv_measure:'0.50'})],[passenger]:[row({hos_driv_basic_alert:'N'})]});
    assert.equal(app.officialSmsSourceId(ev),id);
    assert.equal(app.officialSmsRows(ev)[0].hos_driv_basic_alert,'N');
    assert.equal(app.replayCarrierInspectionMeasures(ev)[0].status,'MATCH');
  }
});
test('AB and C membership conflicts cannot silently select a population',()=>{
  const ev=evidence({smsABProperty:[row()],smsCPass:[row()]});
  assert.ok(app.selectOfficialSmsOutput(ev).issues.includes('CONFLICTING_SMS_OPERATION_POPULATIONS'));
  assert.deepEqual(app.officialSmsRows(ev),[]);
});
test('duplicate rows and wrong or missing carrier IDs invalidate official output',()=>{
  for(const rows of [[row(),row()],[row({dot_number:'2'})],[row({dot_number:undefined})]]) {
    const ev=evidence({smsABProperty:rows});
    assert.equal(app.officialSmsSourceId(ev),null);
    assert.equal(app.replayCarrierInspectionMeasures(ev)[0].status,'PARTIAL_DATA');
  }
});
test('failed or truncated populations cannot be treated as a successful absence',()=>{
  for(const kind of ['failed','truncated']) {
    const ev=evidence({smsABProperty:[row()]});
    if(kind==='failed') ev.errors.smsABPass='request failed'; else ev.slices.smsABPass.truncated=true;
    assert.equal(app.selectOfficialSmsOutput(ev).row,null);
  }
});
test('conflicting overlapping measures are unavailable, not silently preferred',()=>{
  const ev=evidence({smsABProperty:[row()],smsABPass:[row({hos_driv_measure:'1'})]});
  assert.ok(app.selectOfficialSmsOutput(ev).issues.includes('CONFLICTING_SMS_MEASURE:hos_driv_measure'));
});
test('successful empty populations and missing official measures remain distinct from zero',()=>{
  const empty=evidence();
  assert.deepEqual(app.selectOfficialSmsOutput(empty).issues,[]);
  assert.equal(app.replayCarrierInspectionMeasures(empty)[0].status,'NO_OFFICIAL');
  for(const value of ['',undefined,'bad','-1','0x1','1e2']) {
    assert.equal(app.replayCarrierInspectionMeasures(evidence({smsABProperty:[row({hos_driv_measure:value})]}))[0].officialMeasure,null);
  }
  assert.equal(app.replayCarrierInspectionMeasures(evidence({smsABProperty:[row({hos_driv_measure:'0'})]}))[0].officialMeasure,0);
});
test('captured real AB/C passenger rows select the matching passenger source',async()=>{
  const fixture=JSON.parse(await readFile(new URL('./fixtures/sms-passenger-outputs.json',import.meta.url),'utf8'));
  for(const carrier of fixture.carriers) {
    const ev=evidence(carrier.outputs); ev.dotNumber=carrier.dot_number;
    assert.equal(app.officialSmsSourceId(ev),carrier.expected_source);
    assert.deepEqual(app.selectOfficialSmsOutput(ev).issues,[]);
  }
  const edge=fixture.no_driver_denominator_example;
  const ev=evidence(edge.outputs); ev.dotNumber=edge.dot_number;
  ev.slices.smsInspection=slice(edge.inspections); ev.slices.smsViolation=slice(edge.violations);
  const results=app.replayCarrierInspectionMeasures(ev);
  for(const result of results.slice(0,3)) {
    assert.equal(result.officialMeasure,0); assert.equal(result.calculatedMeasure,null);
    assert.equal(result.denominator,0); assert.equal(result.status,'NO_DENOMINATOR');
  }
  assert.equal(app.replaySummary(results).validationCandidates,1);
});
