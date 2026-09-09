import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';

// Execute production TypeScript, including shared caches and dependent query loading.
const compiled = await build({ stdin: { contents: "export * from './src/datahub'; export * from './src/carrierEvidence'; export * from './src/smsReplay';", resolveDir: process.cwd(), loader: 'ts' }, bundle: true, write: false, format: 'esm', platform: 'node', define: { 'import.meta.env.BASE_URL': '"/Transport3r/"' } });
const runtime = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry = JSON.parse(await readFile('public/data/source-schemas.json', 'utf8'));
const live = JSON.parse(await readFile('scripts/fixtures/daily-safety-3938496.json', 'utf8'));
const slice = (rows, sourceId = '876r-jsdb', truncated = false) => ({ rows, sourceId, total: null, truncated });

test('real captured violation fields produce four OOS rows and preserve unit/description', () => {
  assert.equal(runtime.oosViolationCount({ slices: { violations: slice(live.violations.rows) }, errors: {} }), 4);
  assert.ok(live.violations.rows.some((row) => runtime.readValue(row, [...runtime.VIOLATION_FIELD_ALIASES.description])));
  assert.ok(live.violations.rows.some((row) => runtime.readValue(row, [...runtime.VIOLATION_FIELD_ALIASES.unit])));
});
test('missing and unrecognized OOS evidence remain unknown; successful empty slice is zero loaded rows', () => {
  assert.equal(runtime.oosViolationCount({ slices: {}, errors: {} }), null);
  assert.equal(runtime.oosViolationCount({ slices: { violations: slice([{}]) }, errors: {} }), null);
  assert.equal(runtime.oosViolationCount({ slices: { violations: slice([]) }, errors: {} }), 0);
  assert.equal(runtime.rowCountLabel(undefined), '—');
  assert.equal(runtime.rowCountLabel(slice([{}, {}], 'x', true)), '2+');
});
test('daily, legacy, ISO and named dates agree and reject invalid calendar dates', () => {
  for (const raw of ['20240830', '08302024', '2024-08-30', '08/30/2024', '30-AUG-24', '2024-08-30T00:00:00.000']) {
    assert.equal(runtime.parseDateValue(raw)?.toISOString(), '2024-08-30T00:00:00.000Z', raw);
  }
  for (const raw of ['20240230', '20230229', '2024-02-30', '20241301', '00000000', '0', 'garbage']) assert.equal(runtime.parseDateValue(raw), null, raw);
  assert.equal(runtime.parseDateValue('20240229')?.getUTCDate(), 29);
  assert.equal(runtime.parseDateValue(live.inspections.rows[0].insp_date)?.getUTCFullYear(), 2024);
});
function mockData(t, records, failSource, countResponse) {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (input) => {
    const url = new URL(String(input), 'http://local');
    if (url.pathname.endsWith('source-schemas.json')) return Response.json(registry);
    const id = url.pathname.split('/').pop().replace('.json', '');
    calls.push({ id, where: url.searchParams.get('$where'), offset: Number(url.searchParams.get('$offset') ?? 0), limit: Number(url.searchParams.get('$limit')), order: url.searchParams.get('$order') });
    if (id === failSource) return new Response('', { status: 503 });
    const call = calls.at(-1);
    let rows = records[id] ?? [];
    if (url.searchParams.has('$select')) return countResponse instanceof Response ? countResponse : Response.json(countResponse ?? [{count:String(rows.length)}]);
    if (call.where.includes(' in (')) {
      const ids = call.where.match(/in \((.*)\)/)[1].replaceAll("'", '').split(',');
      rows = rows.filter((row) => ids.includes(String(row.inspection_id)));
    }
    return Response.json(rows.slice(call.offset, call.offset + call.limit));
  });
  return calls;
}
test('queries all 500 parent IDs, paginates child rows, and forwards caller cap', async (t) => {
  const ids = Array.from({ length: 500 }, (_, i) => String(i + 1));
  const records = ids.flatMap((id) => Array.from({ length: 12 }, () => ({ inspection_id: id })));
  const calls = mockData(t, { '876r-jsdb': records });
  const result = await runtime.queryByDotOrInspectionIds(registry, '876r-jsdb', '1', ids, { limit: 1300, maxInspectionIds: 500 });
  assert.equal(result.rows.length, 6000);
  assert.equal(result.truncated, false);
  assert.ok(calls.some((call) => call.offset === 1000));
  assert.ok(calls.every((call) => call.order === ':id'));
  const capped = await runtime.queryByDotOrInspectionIds(registry, '876r-jsdb', '1', ids, { limit: 100, maxInspectionIds: 500 });
  assert.equal(capped.rows.length, 500);
  assert.equal(capped.total, null);
  assert.equal(capped.truncated, true);
});
test('duplicate parent IDs do not imply truncation; omitted distinct IDs do', async (t) => {
  mockData(t, { '876r-jsdb': [{ inspection_id: '1' }, { inspection_id: '2' }] });
  const complete = await runtime.queryByInspectionIds(registry, '876r-jsdb', ['1', '1']);
  assert.equal(complete.truncated, false);
  const partial = await runtime.queryByInspectionIds(registry, '876r-jsdb', ['1', '2'], { maxInspectionIds: 1 });
  assert.equal(partial.truncated, true);
  assert.equal(partial.total, null);
});
test('exact row limit is complete only after lookahead; larger source is partial', async (t) => {
  mockData(t, { 'fx4q-ay7w': [{ inspection_id: '1' }, { inspection_id: '2' }] });
  assert.equal((await runtime.queryByDot(registry, 'fx4q-ay7w', '1', { limit: 2 })).truncated, false);
  assert.equal((await runtime.queryByDot(registry, 'fx4q-ay7w', '1', { limit: 1 })).truncated, true);
});

test('large-carrier source totals remain distinct from bounded loaded rows', async (t) => {
  mockData(t, {'fx4q-ay7w':Array.from({length:501},(_,i)=>({inspection_id:String(i+1)}))},undefined,[{count:'30685'}]);
  const result=await runtime.queryByDot(registry,'fx4q-ay7w','80806',{limit:500,includeTotal:true});
  assert.equal(result.rows.length,500); assert.equal(result.total,30685); assert.equal(result.truncated,true);
  assert.equal(runtime.rowCountLabel(result),'30,685');
  assert.equal(runtime.loadedRowCountLabel(result),'500');
  assert.equal(runtime.inspectionCountDetail(result),'Full available history · 500 recent rows loaded');
});

test('malformed, failed or contradictory counts never override the observed inspection window', async (t) => {
  for(const countResponse of [[{count:null}],[{count:''}],[{count:'-1'}],[{count:'1.5'}],[{count:'9007199254740992'}],[{count:'500'}],[],new Response('',{status:503})]) {
    await t.test(String(JSON.stringify(countResponse)),async t=>{
      mockData(t,{'fx4q-ay7w':Array.from({length:501},(_,i)=>({inspection_id:String(i+1)}))},undefined,countResponse);
      const result=await runtime.queryByDot(registry,'fx4q-ay7w','80806',{limit:500,includeTotal:true});
      assert.equal(result.total,null); assert.equal(result.rows.length,500); assert.equal(result.truncated,true);
      assert.equal(runtime.rowCountLabel(result),'500+');
      assert.match(runtime.inspectionCountDetail(result),/total unavailable/);
    });
  }
});

test('confirmed empty source counts remain a complete zero',async t=>{
  mockData(t,{},undefined,[{count:'0'}]);
  const result=await runtime.queryByDot(registry,'fx4q-ay7w','1',{includeTotal:true});
  assert.equal(result.total,0); assert.equal(result.truncated,false); assert.equal(runtime.rowCountLabel(result),'0');
});
test('failed parent does not turn dependent queries into empty successes', async (t) => {
  const calls = mockData(t, {}, 'fx4q-ay7w');
  const result = await runtime.loadCarrierEvidence('901', 'safety');
  assert.ok(result.errors.inspections);
  for (const key of ['violations', 'citations', 'specialStudies']) {
    assert.ok(result.errors[key]); assert.equal(result.slices[key], undefined);
  }
  assert.ok(!calls.some((call) => ['876r-jsdb', 'qbt8-7vic', '5qik-smay'].includes(call.id)));
});
test('truncated parent marks child coverage partial and source-mode cache preserves that state', async (t) => {
  mockData(t, { 'fx4q-ay7w': Array.from({ length: 501 }, (_, i) => ({ inspection_id: String(i + 1) })) });
  const result = await runtime.loadCarrierEvidence('902', 'safety');
  assert.equal(result.slices.inspections.rows.length, 500);
  assert.equal(result.slices.violations.truncated, true);
  assert.equal(result.slices.violations.total, null);
  const again = await runtime.loadCarrierEvidence('902', 'summary');
  assert.equal(again.slices.violations.truncated, true);
  assert.ok(again.slices.motusInsuranceHistoryDelta);
});
test('legacy bridge failure remains a historical filing error', async (t) => {
  const calls = mockData(t, {}, '6eyk-hxee');
  const result = await runtime.loadCarrierEvidence('903', 'evidence');
  assert.ok(result.errors.legacyInsurance);
  assert.equal(result.slices.legacyInsurance, undefined);
  assert.ok(!calls.some((call) => call.id === 'ypjt-5ydn'));
});
test('SMS replay never reports a match after a required source failure', () => {
  const result = runtime.replayCarrierInspectionMeasures({ slices: { smsInspection: slice([]) }, errors: { smsViolation: 'HTTP 503' } });
  assert.ok(result.every((row) => row.status === 'PARTIAL_DATA'));
});
