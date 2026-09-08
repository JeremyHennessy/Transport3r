import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

const compiled = await build({ stdin: { contents: "export * from './src/carrierEvidence'; export * from './src/evidenceLifecycle'; export * from './src/EvidenceStatus'; export * from './src/CarrierRouteApp'; export * from './src/smsReplay';", resolveDir: process.cwd(), loader: 'tsx' }, bundle: true, write: false, format: 'esm', platform: 'node', define: { 'import.meta.env.BASE_URL': '"/Transport3r/"' } });
const r = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const slice = (rows = [], truncated = false) => ({ sourceId: 'test', rows, total: null, truncated });
const evidence = (slices = {}, mode = 'summary', errors = {}) => ({ slices, mode, errors, dotNumber: '1', loadedAt: '2026-09-08T22:00:00Z', registry: { sources: [] } });
const allSlices = Object.fromEntries(Object.keys(r.SOURCE_IDS).map((key) => [key, slice()]));
const render = (Component, props) => renderToStaticMarkup(createElement(Component, props));

test('captured rescinded orders remain historical even when USDOT status is ACTIVE', async () => {
  const fixture = JSON.parse(await readFile('scripts/fixtures/rescinded-orders.json', 'utf8'));
  assert.ok(fixture.rows.some((row) => row.status === 'ACTIVE'));
  for (const row of fixture.rows) assert.equal(r.newEntrantOrderState(row, '2026-09-08'), 'RESCINDED');
});
test('order lifecycle distinguishes unrescinded, future, inconsistent and invalid dates', () => {
  const at = '2026-09-08';
  assert.equal(r.newEntrantOrderState({ oos_date: '2025-01-01', status: 'INACTIVE' }, at), 'ISSUED_NO_RESCISSION_RECORDED');
  assert.equal(r.newEntrantOrderState({ oos_date: '2025-01-01', rescind_date: '2026-10-01' }, at), 'RESCISSION_SCHEDULED');
  assert.equal(r.newEntrantOrderState({ oos_date: '2026-10-01' }, at), 'FUTURE_ISSUE');
  for (const row of [{oos_date:'bad'}, {oos_date:'2025-01-01',rescind_date:'bad'}, {oos_date:'2025-01-01',rescind_date:'2024-01-01'}]) assert.equal(r.newEntrantOrderState(row, at), 'UNKNOWN');
});
test('filing changes preserve documented event direction and effective timing', () => {
  for (const [source, expected] of [['cancelled','CANCELLED'],['replaced','REPLACED'],['name change','NAME_CHANGE'],['transferred','TRANSFERRED']]) {
    assert.deepEqual(r.filingHistoryEvent({ filing_status_reason: source, cancl_effective_date: '20260101' }, '2026-09-08'), { reason: expected, timing: 'EFFECTIVE' });
  }
  assert.deepEqual(r.filingHistoryEvent({filing_status_reason:'replaced',cancl_effective_date:'20261001'}, '2026-09-08'), {reason:'REPLACED',timing:'SCHEDULED'});
  assert.deepEqual(r.filingHistoryEvent({}, '2026-09-08'), {reason:'UNKNOWN',timing:'UNKNOWN'});
});
test('MOTUS maximum amounts retain unresolved source units and never substitute underlying limits', () => {
  assert.equal(r.MOTUS_COVERAGE_UNIT_STATUS,'UNRESOLVED');
  assert.equal(r.motusMaximumCoverageLabel({max_cov_amount:'1000'}),'1,000 (source amount)');
  assert.equal(r.motusMaximumCoverageLabel({max_cov_amount:'750000.00'}),'750,000 (source amount)');
  assert.equal(r.motusMaximumCoverageLabel({underl_lim_amount:'500',max_cov_amount:'1000'}),'1,000 (source amount)');
  assert.equal(r.motusMaximumCoverageLabel({underl_lim_amount:'500'}),'—');
  assert.equal(r.motusMaximumCoverageLabel({max_cov_amount:'-1'}),'—');
});
test('missing crash fields are unknown and known fatal events are retained', () => {
  assert.deepEqual(r.severeCrashCounts(evidence()), {fatal:null,injury:null,tow:null,incomplete:true});
  assert.deepEqual(r.severeCrashCounts(evidence({crash:slice()})), {fatal:0,injury:0,tow:0,incomplete:false});
  const result = r.severeCrashCounts(evidence({crash:slice([{fatalities:'1'},{}])}));
  assert.equal(result.fatal,1); assert.equal(result.injury,null); assert.equal(result.incomplete,true);
});
test('aggregates distinguish complete zero, unavailable and partial lower bounds', () => {
  const keys=['motusCarrierDelta','motusInsuranceDelta'];
  assert.deepEqual(r.aggregateRows(evidence(),keys),{loaded:0,complete:false,label:'—'});
  assert.deepEqual(r.aggregateRows(evidence({motusCarrierDelta:slice([{}])}),keys),{loaded:1,complete:false,label:'1+'});
  assert.deepEqual(r.aggregateRows(evidence({motusCarrierDelta:slice(),motusInsuranceDelta:slice()}),keys),{loaded:0,complete:true,label:'0'});
  assert.equal(r.observedVinCountLabel(evidence()),'—');
  assert.equal(r.observedVinCountLabel(evidence({units:slice()})),'0');
});
test('summary renders missing severity as unavailable and never a clear review', () => {
  const html=render(r.Summary,{carrier:{dotNumber:'1',raw:{}},evidence:evidence()});
  assert.ok(html.includes('Summary evidence is incomplete or unavailable'));
  assert.ok(html.includes('— fatality-involved'));
  assert.ok(!html.includes('No hard-review flags derived'));
});
test('rescinded-only orders do not generate an unrescinded-order review flag', () => {
  const e=evidence({...allSlices,newEntrantOos:slice([{oos_date:'2025-01-01',rescind_date:'2025-02-01',status:'ACTIVE'}])});
  assert.equal(r.orderSummary(e).review,null);
  assert.ok(r.orderSummary(e).text.startsWith('1 rescinded'));
  const authority=render(r.Authority,{evidence:{...e,mode:'authority'}});
  assert.ok(authority.includes('1 rescinded'));
  assert.ok(authority.includes('USDOT status does not establish order effect'));
});
test('insurance renderer distinguishes replacement from cancellation and missing feed', () => {
  const e=evidence({...allSlices,motusInsuranceHistoryDelta:slice([{filing_status_reason:'replaced',cancl_effective_date:'20260101'}])},'insurance');
  const html=render(r.Insurance,{evidence:e});
  assert.ok(html.includes('0 cancelled, 1 replaced'));
  assert.ok(html.includes('do not establish a coverage gap'));
  assert.ok(render(r.Insurance,{evidence:evidence({},'insurance')}).includes('History-change evidence unavailable'));
});
test('partial sources and Fleet failure render explicit warnings', () => {
  const html=render(r.EvidenceStatus,{evidence:evidence({inspections:slice([],true),units:slice()},'fleet')});
  assert.ok(html.includes('partial'));
  const fleet=render(r.FleetEvidenceFailure,{error:'Schema request failed'});
  assert.ok(fleet.includes('Inspection-unit evidence unavailable'));
  assert.ok(fleet.includes('Schema request failed'));
  assert.ok(!fleet.includes('No individual vehicles were returned'));
});
test('failed SMS inputs suppress numerical replay and no-denominator cases are not comparisons', () => {
  const rows=r.replayCarrierInspectionMeasures(evidence({smsInspection:slice([{unique_id:'1',fatigued_insp:'Y',time_weight:'1'}])},'sms',{smsViolation:'HTTP 503'}));
  assert.ok(rows.every((row)=>row.calculatedMeasure===null && row.status==='PARTIAL_DATA'));
  assert.equal(r.replaySummary([{officialMeasure:0,truncatedInput:false,status:'NO_DENOMINATOR'}]).validationCandidates,0);
});
