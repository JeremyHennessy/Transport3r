import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
// Hook-using components and the renderer must share the same React instance.
const sharedReact = {name:'shared-react',setup(build){build.onResolve({filter:/^react(?:\/|$)/},args=>({path:pathToFileURL(require.resolve(args.path)).href,external:true}));}};
const compiled = await build({ stdin: { contents: "export * from './src/carrierEvidence'; export * from './src/evidenceLifecycle'; export * from './src/EvidenceStatus'; export * from './src/CarrierRouteApp'; export * from './src/smsReplay';", resolveDir: process.cwd(), loader: 'tsx' }, bundle: true, write: false, format: 'esm', platform: 'node', plugins:[sharedReact], define: { 'import.meta.env.BASE_URL': '"/Transport3r/"' } });
const r = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const slice = (rows = [], truncated = false) => ({ sourceId: 'test', rows, total: null, truncated });
const evidence = (slices = {}, mode = 'summary', errors = {}) => ({ slices, mode, errors, dotNumber: '1', loadedAt: '2026-09-08T22:00:00Z', registry: { sources: [] } });
const allSlices = Object.fromEntries(Object.keys(r.SOURCE_IDS).map((key) => [key, slice()]));
const render = (Component, props) => renderToStaticMarkup(createElement(Component, props));

test('Evidence reports partial and missing sources even without HTTP errors',()=>{
  const carrier=r.carrierFromRow({dot_number:'1',legal_name:'Example'});
  const partial=evidence({...allSlices,inspections:{...slice([{}],true),total:900}},'evidence');
  const html=render(r.Evidence,{carrier,evidence:partial});
  assert.match(html,/sources? incomplete or unavailable/);
  assert.ok(html.includes('Loaded evidence is partial'));
  assert.ok(html.includes('1 rows loaded'));
  assert.ok(!html.includes('Loaded without source errors'));
  delete partial.slices.motusCarrier;
  assert.ok(render(r.Evidence,{carrier,evidence:partial}).includes('Source evidence was not returned.'));
  const complete=render(r.Evidence,{carrier,evidence:evidence({...allSlices},'evidence')});
  assert.ok(complete.includes('Loaded without source errors'));
  assert.ok(!complete.includes('sources incomplete or unavailable'));
});

test('authority empty states distinguish failed, missing, partial and confirmed-empty sources',()=>{
  for(const kind of ['failed','missing','partial','empty']) {
    const ev=evidence({...allSlices},'authority');
    for(const key of ['motusAuthHistory','motusRevokeSuspend','motusBoc3']) {
      if(kind==='failed') {delete ev.slices[key];ev.errors[key]='HTTP 503';}
      if(kind==='missing') delete ev.slices[key];
      if(kind==='partial') ev.slices[key]=slice([],true);
    }
    const html=render(r.Authority,{evidence:ev});
    const expected=kind==='empty'?'No BOC-3 rows returned for this USDOT.':kind==='partial'?'No rows in the loaded window; source coverage is partial.':'Source unavailable; record absence cannot be determined.';
    assert.ok(html.includes(expected),kind);
    if(kind!=='empty') assert.ok(!html.includes('No BOC-3 rows returned for this USDOT.'));
  }
  const ev=evidence({...allSlices},'summary',{motusCarrier:'HTTP 503'});
  delete ev.slices.motusCarrier;
  assert.equal(r.authorityStatusLabel(ev),'Current MOTUS authority unavailable');
});

test('SMS displays a deduplicated date rejection reason without losing valid official values',()=>{
  const ev=evidence({...allSlices,smsABProperty:slice([{dot_number:'1',hos_driv_measure:'5'}]),smsInspection:slice([{dot_number:'1',unique_id:'i',insp_date:'2026-05-15',time_weight:'3',fatigued_insp:'true'}]),smsViolation:slice([{dot_number:'1',unique_id:'i',insp_date:'2026-05-16',time_weight:'3',basic_desc:'Hours-of-Service Compliance',total_severity_wght:'5'}])},'sms');
  const replays=r.replayCarrierInspectionMeasures(ev);
  const messages=r.smsReplayMessages(replays);
  assert.deepEqual(messages,['Inspection dates are missing, invalid or inconsistent between linked rows.']);
  assert.equal(replays[0].officialMeasure,5); assert.equal(replays[0].calculatedMeasure,null);
  const html=render(r.Sms,{evidence:ev});
  assert.ok(html.includes('SMS replay could not be fully validated'));
  assert.equal(html.split(messages[0]).length-1,1);
  assert.ok(html.includes('PARTIAL_DATA'));
});

test('SMS distinguishes unavailable or conflicting outputs from successful absence',()=>{
  const empty=evidence({...allSlices},'sms');
  assert.ok(render(r.Sms,{evidence:empty}).includes('No applicable public SMS output row returned.'));
  assert.deepEqual(r.smsReplayMessages(r.replayCarrierInspectionMeasures(empty)),[]);
  const failed=evidence({...allSlices},'sms',{smsABProperty:'HTTP 503'});
  delete failed.slices.smsABProperty;
  const html=render(r.Sms,{evidence:failed});
  assert.ok(html.includes('Official SMS output is unavailable or inconsistent.'));
  assert.ok(html.includes('One or more official SMS output sources are incomplete or unavailable.'));
  assert.ok(!html.includes('No applicable public SMS output row returned.'));
  const conflict=evidence({...allSlices,smsABProperty:slice([{dot_number:'1',hos_driv_measure:'1'}]),smsABPass:slice([{dot_number:'1',hos_driv_measure:'2'}])},'sms');
  assert.ok(render(r.Sms,{evidence:conflict}).includes('Overlapping official SMS outputs contain conflicting measures.'));
});

test('large-carrier driver exposure preserves Census totals and report date',async()=>{
  const carriers=JSON.parse(await readFile('scripts/fixtures/large-carrier-census.json','utf8'));
  for(const row of carriers) {
    const carrier=r.carrierFromRow(row);
    assert.equal(carrier.drivers,row.total_drivers);
    assert.equal(carrier.powerUnits,row.power_units);
    const html=render(r.CarrierHeader,{carrier,route:{kind:'section',dotNumber:carrier.dotNumber,section:'safety'}});
    assert.ok(html.includes(Number(row.total_drivers).toLocaleString()));
    assert.ok(html.includes('Company Census · MCS-150'));
    assert.equal(carrier.mcs150Date,row.mcs150_date);
    if(row.status_code==='I') assert.ok(html.includes('Inactive registration'));
  }
});

test('Safety uses the full source count while Summary preserves its loaded-inspection label',()=>{
  const inspections={...slice(Array.from({length:500},(_,i)=>({inspection_id:String(i)})),true),total:30685};
  const carrier=r.carrierFromRow({dot_number:'80806',legal_name:'J B HUNT TRANSPORT INC',total_drivers:'24116'});
  const ev=evidence({...allSlices,inspections},'safety');
  const safety=render(r.Safety,{carrier,evidence:ev});
  assert.ok(safety.includes('30,685'));
  assert.ok(safety.includes('Full available history · 500 recent rows loaded'));
  const summary=render(r.Summary,{carrier,evidence:{...ev,mode:'summary'}});
  assert.ok(summary.includes('Loaded inspections</span><strong>500</strong>'));
  assert.ok(!summary.includes('30,685'));
});

test('empty inspection source is not presented as proof of no carrier inspections',()=>{
  const carrier=r.carrierFromRow({dot_number:'265752',legal_name:'FEDEX GROUND PACKAGE SYSTEM INC',status_code:'I'});
  const html=render(r.Safety,{carrier,evidence:evidence({...allSlices,inspections:{...slice(),total:0}},'safety')});
  assert.ok(html.includes('No rows returned for this USDOT; not proof of no inspections'));
});

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
