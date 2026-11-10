// Synthetic unit-test receipts only. Never publish as accepted source data.
import catalog from '../../data/fmcsa_sources.json' with {type:'json'};
const globals=['source_coverage','receipt_scope','aggregate_rows','audited_sources','census_carriers','mapping_totals','immutable_file'];
const checks=['source_counts','raw_identity','mapping_cardinality','joined_rows','mapping_status','mapping_reasons','provenance','exact_duplicates','identity_mapping'];
const trueMap=keys=>Object.fromEntries(keys.map(key=>[key,true]));
export function syntheticAudit(evidence){
 const totals=evidence.completeness_receipt.mapping_totals;
 const sources=catalog.map(({id})=>{
  const lineage=evidence.sources.find(source=>source.source_id===id);
  const mapping_status=id==='az4n-8mr2'?{RESOLVED:totals.resolved,IDENTIFIED_ONLY:totals.identified_only,UNRESOLVED:totals.unresolved}:{};
  const n=Object.values(mapping_status).reduce((sum,value)=>sum+value,0);
  return {source:id,sha256:lineage?.source_sha256??'b'.repeat(64),available_at:lineage?.source_available_at??evidence.cut_available_at,
   rows_updated_at:lineage?.source_rows_updated_at??1,published:n,acquired:n,warehouse:n,actual_raw:n,actual_mapping:n,
   actual_joined:n,distinct_mapping_rows:n,missing_mapping_rows:0,orphan_mapping_rows:0,identity_mapping_disagreements:0,
   mapping_status,exact_duplicate_rows:0,distinct_source_rows:n,checks:trueMap(checks)};
 });
 const raw=sources.reduce((sum,source)=>sum+source.actual_raw,0);
 const report={schema_version:'TRANSPORT3R_WAREHOUSE_AUDIT_2',status:'PASS',release_ready:true,
  audited_at:'2026-11-09T00:00:00Z',warehouse_sha256:evidence.warehouse_sha256,identity_contract:'FMCSA_CARRIER_IDENTITY_1',
  scope:'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES',cut_id:evidence.cut_id,cut_available_at:evidence.cut_available_at,
  source_count:36,raw_rows:raw,receipt_rows:raw,census_carriers:totals.resolved,
  deep_exact_duplicates_checked:true,duplicate_rule:'EXACT_ORIGINAL_SOURCE_COLUMNS_V2',checks:trueMap(globals),sources,failures:[]};
 const health={status:'ok',independent_audit:'PASS',warehouse_sha256:evidence.warehouse_sha256,
  cut_id:evidence.cut_id,cut_available_at:evidence.cut_available_at,sources:36,identity_contract:'FMCSA_CARRIER_IDENTITY_1'};
 return {report,health};
}
export function syntheticEvidence(){
 return {cut_id:'synthetic-test-cut',cut_available_at:'2026-10-23T00:00:00Z',warehouse_sha256:'a'.repeat(64),
  sources:catalog.map(({id})=>({source_id:id,source_sha256:'b'.repeat(64),source_available_at:'2026-10-23T00:00:00Z',
   source_rows_updated_at:1,carrier_rows:id==='az4n-8mr2'?1:0})),
  completeness_receipt:{mapping_totals:{resolved:100,identified_only:2,unresolved:3}}};
}
