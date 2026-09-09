import test from 'node:test';
import assert from 'node:assert/strict';
import { queryLiveSource } from './live-source-retry.mjs';

test('raw metadata fetch retries transport errors, timeout and transient HTTP status',async()=>{
 for(const message of ['fetch failed','Request timed out after 30s','HTTP 503','HTTP 429']){
  let calls=0;const result=await queryLiveSource(async()=>{if(++calls===1)throw new Error(message);return {rowsUpdatedAt:123};},{wait:async()=>{}});
  assert.equal(calls,2);assert.deepEqual(result.attempts.map(a=>a.status),['FAIL','PASS']);assert.equal(result.slice.rowsUpdatedAt,123);
 }
});
test('raw metadata validation and permanent HTTP failures are never retried',async()=>{
 for(const message of ['HTTP 400','HTTP 404','Unexpected token in JSON','Source changed during acquisition']){
  let calls=0;await assert.rejects(queryLiveSource(async()=>{calls++;throw new Error(message);},{wait:async()=>{}}),{message});assert.equal(calls,1);
 }
});

test('live source retry retains transient failures and uses a fresh successful observation', async () => {
  let calls = 0; const delays = [];
  const result = await queryLiveSource(async () => {
    calls++;
    if (calls === 1) throw new Error('fx4q-ay7w request failed: fetch failed');
    if (calls === 2) return { rows: [1], total: null };
    return { rows: [2], total: 1000 };
  }, { requireTotal: true, wait: async ms => delays.push(ms) });
  assert.deepEqual(result.slice, { rows: [2], total: 1000 });
  assert.deepEqual(result.attempts.map(a => a.status), ['FAIL', 'FAIL', 'PASS']);
  assert.deepEqual(delays, [1000, 2000]);
});

test('live source retry fails closed after three unavailable observations', async () => {
  let calls = 0;
  await assert.rejects(queryLiveSource(async () => { calls++; return { total: null }; }, { requireTotal: true, wait: async () => {} }), error => {
    assert.equal(error.attempts.length, 3);
    return /Source total unavailable/.test(error.message);
  });
  assert.equal(calls, 3);
});

test('live source retry does not retry invalid payloads, HTTP 400 or identity failures', async () => {
  for (const message of ['source returned a non-array payload', 'source returned HTTP 400', 'Inspection identity mismatch']) {
    let calls = 0;
    await assert.rejects(queryLiveSource(async () => { calls++; throw new Error(message); }), { message });
    assert.equal(calls, 1);
  }
});

test('live source retry accepts an explicit zero total and retries HTTP 503', async () => {
  let calls = 0;
  const result = await queryLiveSource(async () => {
    if (++calls === 1) throw new Error('source returned HTTP 503');
    return { total: 0, rows: [] };
  }, { requireTotal: true, wait: async () => {} });
  assert.equal(result.slice.total, 0);
  assert.equal(calls, 2);
});
