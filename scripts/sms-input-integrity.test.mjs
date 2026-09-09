import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({stdin:{contents: "export * from './src/smsReplay';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const r = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const inspection = (extra={}) => ({unique_id:'i1',insp_date:'15-MAY-26',dot_number:'1',fatigued_insp:'true',subt_alcohol_insp:'true',time_weight:'3',...extra});
const violation = (extra={}) => ({unique_id:'i1',insp_date:'15-MAY-26',dot_number:'1',basic_desc:'Hours-of-Service Compliance',time_weight:'3',total_severity_wght:'5',...extra});
const replay = (i=[inspection()],v=[violation()]) => r.replayInspectionMeasure(i,v,'hos');

test('valid SMS arithmetic and per-inspection severity cap are preserved',()=>{
  const result=replay([inspection()],[violation({total_severity_wght:'20'}),violation({total_severity_wght:'20'})]);
  assert.equal(result.numerator,90); assert.equal(result.denominator,3); assert.equal(result.calculatedMeasure,30);
  assert.equal(result.cappedInspections,1); assert.deepEqual(result.inputIssues,[]);
});
test('blank, negative, invalid and out-of-range inspection weights cannot become zero',()=>{
  for(const time_weight of ['',undefined,'bad','-1','0','4','1.5','0x3','3e0']) {
    const result=replay([inspection({time_weight})]);
    assert.equal(result.calculatedMeasure,null); assert.equal(result.denominator,null); assert.ok(result.inputIssues.length);
  }
});
test('duplicate or missing parent IDs invalidate replay',()=>{
  for(const rows of [[inspection(),inspection()],[inspection({unique_id:''})]]) {
    assert.equal(replay(rows).calculatedMeasure,null);
  }
});
test('orphan and non-relevant parent violations cannot contribute to numerator',()=>{
  assert.equal(replay(undefined,[violation({unique_id:'other'})]).calculatedMeasure,null);
  assert.equal(replay([inspection({fatigued_insp:undefined})]).calculatedMeasure,null);
});
test('missing and conflicting violation weights invalidate replay',()=>{
  for(const time_weight of ['',undefined,'bad','2']) assert.equal(replay(undefined,[violation({time_weight})]).calculatedMeasure,null);
});
test('malformed supplied totals cannot silently fall back; zero severity remains valid',()=>{
  for(const total_severity_wght of ['bad','-1']) assert.equal(replay(undefined,[violation({total_severity_wght,severity_weight:'5',oos_weight:'0'})]).calculatedMeasure,null);
  assert.equal(replay(undefined,[violation({total_severity_wght:'0'})]).calculatedMeasure,0);
  assert.equal(replay(undefined,[violation({total_severity_wght:undefined,severity_weight:'2',oos_weight:'2'})]).calculatedMeasure,4);
  assert.equal(replay(undefined,[violation({total_severity_wght:undefined,severity_weight:'2'})]).calculatedMeasure,null);
});
test('controlled-substances fallback retains the existing no-OOS-increment rule',()=>{
  const result=r.replayInspectionMeasure([inspection()],[violation({basic_desc:'Controlled Substances/Alcohol',total_severity_wght:undefined,severity_weight:'4',oos_weight:undefined})],'controlledSubstances');
  assert.equal(result.calculatedMeasure,4); assert.deepEqual(result.inputIssues,[]);
});
test('unclassified violations and explicit invalid relevance flags remain unknown',()=>{
  assert.equal(replay(undefined,[violation({basic_desc:undefined})]).calculatedMeasure,null);
  assert.equal(replay([inspection({fatigued_insp:'unknown'})],[]).calculatedMeasure,null);
  assert.equal(replay([inspection({fatigued_insp:undefined})],[]).calculatedMeasure,null);
  assert.deepEqual(replay([inspection({fatigued_insp:undefined})],[]).inputIssues,[]);
});
test('carrier contamination and invalid rows never enter match statistics',()=>{
  const slice=(rows)=>({rows,total:rows.length,truncated:false,sourceId:'test'});
  const evidence={dotNumber:'1',errors:{},slices:{smsInspection:slice([inspection()]),smsViolation:slice([violation({dot_number:'2'})]),smsABProperty:slice([{hos_driv_measure:'5'}])}};
  const results=r.replayCarrierInspectionMeasures(evidence);
  assert.ok(results.every(x=>x.status==='PARTIAL_DATA' && x.calculatedMeasure===null && x.numerator===null));
  assert.equal(r.replaySummary(results).validationCandidates,0);
});

test('missing and impossible event dates invalidate replay on either input source',()=>{
  for(const insp_date of [undefined,'','00000000','31-APR-26','29-FEB-25','2026-02-30','nonsense']) {
    for(const [inspections,violations] of [[[inspection({insp_date})],[violation()]],[[inspection()],[violation({insp_date})]]]) {
      const result=replay(inspections,violations);
      assert.equal(result.calculatedMeasure,null);
      assert.equal(result.denominator,null);
      assert.ok(result.inputIssues.some(issue=>issue.includes('_DATE:')));
    }
  }
});

test('a linked violation on a different day fails even when time weights agree',()=>{
  const result=replay(undefined,[violation({insp_date:'16-MAY-26'})]);
  assert.deepEqual(result.inputIssues,['CONFLICTING_INSPECTION_VIOLATION_DATE:i1']);
  assert.equal(result.numerator,null);
  assert.equal(result.calculatedMeasure,null);
  const slice=rows=>({rows,total:rows.length,truncated:false,sourceId:'test'});
  const evidence={dotNumber:'1',errors:{},slices:{smsInspection:slice([inspection()]),smsViolation:slice([violation({insp_date:'16-MAY-26'})]),smsABProperty:slice([{dot_number:'1',hos_driv_measure:'5'}]),smsCProperty:slice([]),smsABPass:slice([]),smsCPass:slice([])}};
  const results=r.replayCarrierInspectionMeasures(evidence);
  assert.ok(results.every(result=>result.status==='PARTIAL_DATA' && result.delta===null));
  assert.equal(r.replaySummary(results).validationCandidates,0);
});

test('equivalent source date formats retain the event calendar day across offsets',()=>{
  for(const insp_date of ['15-MAY-26','20260515','05/15/2026','2026-05-15','2026-05-15T00:00:00.000','2026-05-15T00:00:00+14:00','2026-05-15T23:00:00-04:00']) {
    assert.deepEqual(replay(undefined,[violation({insp_date})]).inputIssues,[]);
    assert.equal(replay(undefined,[violation({insp_date})]).calculatedMeasure,5);
  }
  assert.deepEqual(replay([inspection({insp_date:'29-FEB-24'})],[violation({insp_date:'20240229'})]).inputIssues,[]);
});

test('sparse event history is diagnostic, not proof of a missing month or a reason to reweight',()=>{
  const inspections=[inspection({insp_date:'30-JUN-25',time_weight:'1'}),inspection({unique_id:'i2',insp_date:'01-JAN-26',time_weight:'2'})];
  const violations=[violation({insp_date:'30-JUN-25',time_weight:'1'})];
  const coverage=r.inspectSmsInputDates(inspections,violations);
  assert.deepEqual(coverage.inspectionDates,{rows:2,validDates:2,earliest:'2025-06-30',latest:'2026-01-01'});
  assert.deepEqual(coverage.issues,[]);
  const result=replay(inspections,violations);
  assert.equal(result.denominator,3); assert.equal(result.numerator,5);
  assert.deepEqual(r.inspectSmsInputDates([],[]).inspectionDates,{rows:0,validDates:0,earliest:null,latest:null});
});

