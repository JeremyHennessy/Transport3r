import test from 'node:test';
import assert from 'node:assert/strict';
import {sourceRetryDelay,transientSourceFailure,queryLiveSource} from './live-source-retry.mjs';
test('wrapped permanent HTTP errors are not treated as transient request failures',()=>{
 for(const message of ['az4n-8mr2 request failed: HTTP 400','az4n-8mr2 request failed: HTTP 404','source request failed: identity mismatch','HTTP 501'])assert.equal(transientSourceFailure(message),false);
 assert.equal(transientSourceFailure('az4n-8mr2 request failed: HTTP 429 (retry-after 5000ms)'),true);
});
test('outer evidence retries respect bounded Retry-After and dependent source errors',()=>{
 assert.equal(sourceRetryDelay(['az4n request failed: HTTP 429 (retry-after 5000ms)','Parent inspections unavailable; child evidence was not queried.'],1),5000);
 assert.equal(sourceRetryDelay(['HTTP 429 (retry-after 90000ms)'],1),null);
 assert.equal(sourceRetryDelay(['HTTP 429','Foreign carrier row'],1),null);
 assert.equal(sourceRetryDelay(['Parent inspections unavailable; child evidence was not queried.'],1),null);
});
test('every failed retry is retained and permanent failures have one attempt',async()=>{
 const waits=[];let n=0;
 const result=await queryLiveSource(async()=>{if(++n<3)throw Error('source request failed: HTTP 429 (retry-after 3000ms)');return {total:0};},{wait:async ms=>{waits.push(ms);}});
 assert.equal(result.attempts.length,3);assert.deepEqual(waits,[3000,3000]);assert.equal(result.slice.total,0);
 await assert.rejects(queryLiveSource(async()=>{throw Error('source request failed: HTTP 404');},{wait:async()=>assert.fail('Must not retry')}),error=>error.attempts.length===1);
});
