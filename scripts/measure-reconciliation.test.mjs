import {test} from 'node:test';
import assert from 'node:assert/strict';
import {compareMeasureSnapshots as compare} from './compare-measure-snapshots.mjs';
const sample={dotNumber:'80806',sourceId:'fx4q-ay7w',sourceCut:'sha256:retained-test-cut',windowStart:'2024-09-01',windowEnd:'2026-08-31',dateField:'insp_date',grain:'distinct inspection_id',filters:'USDOT only',measures:{inspections:20,drivers:null}};
test('mismatched windows, grain or source cuts are not numerical discrepancies',()=>{
 for(const field of ['sourceCut','windowEnd','dateField','grain','filters'])assert.equal(compare(sample,{...sample,[field]:'different'}).status,'NOT_COMPARABLE');
 assert.equal(compare(sample,{measures:{inspections:20}}).status,'NOT_COMPARABLE');
});
test('unknown measures cannot silently become zero or pass reconciliation',()=>{
 assert.equal(compare(sample,sample).status,'INCOMPLETE');
 const zero={...sample,measures:{inspections:0}};assert.equal(compare(zero,zero).status,'MATCH');
 assert.equal(compare(zero,{...zero,measures:{inspections:1}}).status,'MISMATCH');
 assert.equal(compare(zero,{...zero,measures:{inspections:'0'}}).status,'INCOMPLETE');
});
