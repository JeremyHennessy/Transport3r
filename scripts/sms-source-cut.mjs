// Independently enforce query-window lineage before executing application replay.
export const SMS_RUNTIME_SOURCES = ['4y6x-dmck','h9zy-gjn8','m3ry-qcip','h3zn-uid9','rbkj-cgst','8mt8-2mdr'];
const markers = ['rows_updated_at','schema_sha256','table_id','row_count'];
function time(raw) {
  if(typeof raw!=='string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)$/.test(raw)) throw new Error('Invalid timestamp or missing timezone');
  const value=Date.parse(raw);
  if(!Number.isFinite(value)) throw new Error('Invalid timestamp');
  const calendar=new Date(`${raw.slice(0,19)}Z`);
  if(!Number.isFinite(calendar.getTime()) || calendar.toISOString().slice(0,19)!==raw.slice(0,19)) throw new Error('Invalid calendar timestamp');
  return value;
}
export function verifySmsSourceCut(sample) {
  const cut=sample.source_cut;
  if(!cut || cut.schema_version!==1) throw new Error('Missing or invalid SMS source-cut lineage');
  const required=[...SMS_RUNTIME_SOURCES].sort().join(',');
  if(!Array.isArray(sample.source_ids) || [...sample.source_ids].sort().join(',')!==required) throw new Error('Unexpected SMS source set');
  for(const phase of ['before','after']) {
    if(Object.keys(cut[phase]??{}).sort().join(',')!==required) throw new Error('Incomplete source observations');
  }
  const [start,first,last,end]=['started_at','queries_started_at','queries_completed_at','completed_at'].map(key=>time(cut[key]));
  if(!(start<=first && first<=last && last<=end && end<=time(sample.captured_at))) throw new Error('Invalid source query window');
  for(const sid of SMS_RUNTIME_SOURCES) {
    for(const phase of ['before','after']) {
      const state=cut[phase][sid];
      if(!state || state.error || state.source_id!==sid || state.metadata?.id!==sid) throw new Error(`Unavailable or wrong source observation: ${sid}`);
      const observed=time(state.observed_at);
      if(!Number.isSafeInteger(state.rows_updated_at) || state.rows_updated_at<=0 || state.rows_updated_at!==state.metadata.rowsUpdatedAt || state.rows_updated_at*1000>observed) throw new Error(`Invalid update watermark: ${sid}`);
      if(!Number.isSafeInteger(state.row_count) || state.row_count<0 || !state.table_id || state.table_id!==state.metadata.tableId || !/^[a-f0-9]{64}$/.test(state.schema_sha256??'')) throw new Error(`Invalid source markers: ${sid}`);
      if(phase==='before' ? !(start<=observed && observed<=first) : !(last<=observed && observed<=end)) throw new Error(`Source observations do not bracket queries: ${sid}`);
    }
    for(const marker of markers) if(cut.before[sid][marker]!==cut.after[sid][marker]) throw new Error(`Source changed during queries: ${sid}:${marker}`);
  }
  return {status:'STABLE_DURING_QUERY_WINDOW',source_count:SMS_RUNTIME_SOURCES.length,monthly_alignment:'NOT_VERIFIED',snapshot_date:null};
}
