import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SMS_RUNTIME_SOURCES as ids,verifySmsSourceCut} from './sms-source-cut.mjs';
function fixture() {
  const states=at=>Object.fromEntries(ids.map(id=>[id,{source_id:id,observed_at:at,row_count:10,rows_updated_at:1700000000,table_id:'t1',schema_sha256:'a'.repeat(64),metadata:{id,rowsUpdatedAt:1700000000,tableId:'t1'}}]));
  return {captured_at:'2026-01-01T00:04:00Z',source_ids:[...ids],source_cut:{schema_version:1,started_at:'2026-01-01T00:00:00Z',queries_started_at:'2026-01-01T00:01:00Z',queries_completed_at:'2026-01-01T00:02:00Z',completed_at:'2026-01-01T00:03:00Z',before:states('2026-01-01T00:00:30Z'),after:states('2026-01-01T00:02:30Z')}};
}
test('stable source observations certify only query-window stability',()=>{
  const result=verifySmsSourceCut(fixture());
  assert.equal(result.status,'STABLE_DURING_QUERY_WINDOW');
  assert.equal(result.monthly_alignment,'NOT_VERIFIED'); assert.equal(result.snapshot_date,null);
});
test('missing lineage and source omissions cannot pass using a claimed PASS',()=>{
  for(const mutate of [s=>delete s.source_cut,s=>delete s.source_cut.after[ids[0]],s=>s.source_ids.pop(),s=>s.source_ids.push(ids[0])]) {
    const sample=fixture(); sample.status='PASS'; mutate(sample); assert.throws(()=>verifySmsSourceCut(sample));
  }
});
test('rollovers in watermark, schema, table or row count are rejected independently',()=>{
  for(const [key,value] of [['rows_updated_at',1700000001],['schema_sha256','b'.repeat(64)],['table_id','t2'],['row_count',11]]) {
    const sample=fixture(), state=sample.source_cut.after[ids[0]]; state[key]=value;
    if(key==='rows_updated_at') state.metadata.rowsUpdatedAt=value;
    if(key==='table_id') state.metadata.tableId=value;
    assert.throws(()=>verifySmsSourceCut(sample),/Source changed/);
  }
});
test('failed, wrong-source, missing-marker and future-watermark observations fail',()=>{
  for(const mutate of [s=>s.error='HTTP 503',s=>s.source_id='wrong',s=>s.rows_updated_at=null,s=>s.row_count=-1,s=>s.metadata.id='wrong',s=>{s.rows_updated_at=2000000000;s.metadata.rowsUpdatedAt=2000000000;}]) {
    const sample=fixture(); mutate(sample.source_cut.before[ids[0]]); assert.throws(()=>verifySmsSourceCut(sample));
  }
});
test('observation times must bracket the query window and carry a timezone',()=>{
  for(const [phase,at] of [['before','2026-01-01T00:01:01Z'],['after','2026-01-01T00:01:59Z'],['before','2026-01-01T00:00:30'],['before','2026-02-30T00:00:30Z']]) {
    const sample=fixture(); sample.source_cut[phase][ids[0]].observed_at=at; assert.throws(()=>verifySmsSourceCut(sample));
  }
});
