import {loadSchemaRegistry,readValue,type DataRow,type DataSlice,type SchemaRegistry} from './datahub';
import {SOURCE_IDS,type CarrierEvidence,type CompletenessReceipt,type EvidenceKey} from './carrierEvidence';
import sourceContract from '../data/fmcsa_source_contract.json';

export type CompleteProgress={finished:number;total:number;rows:number;source:string;status:'loading'|'complete'|'errors';errors:number;backend?:CompletenessReceipt['backend'];cutId?:string|null;smsReleaseBinding?:CompletenessReceipt['smsReleaseBinding']};
type SourceContract={identity:{strategy:string;field:string}};
const contracts=sourceContract.sources as Record<string,SourceContract>;
const legacy=new Set((Object.keys(SOURCE_IDS) as EvidenceKey[]).filter(key=>contracts[SOURCE_IDS[key]]?.identity.strategy==='direct_usdot_legacy'));
const children=new Set((Object.keys(SOURCE_IDS) as EvidenceKey[]).filter(key=>contracts[SOURCE_IDS[key]]?.identity.strategy==='inspection_parent'));
const base='https://data.transportation.gov';
const warehouseBase=String(import.meta.env?.VITE_EVIDENCE_API_URL??'').trim().replace(/\/$/,'');
const positive=(value:unknown)=>typeof value==='string'&&/^[0-9]+$/.test(value)&&!/^0+$/.test(value)?value.replace(/^0+/,''):null;
const quote=(value:string)=>"'"+value.replaceAll("'","''")+"'";
const chunks=<T,>(values:T[],size:number)=>Array.from({length:Math.ceil(values.length/size)},(_,i)=>values.slice(i*size,(i+1)*size));
async function pooled<T,R>(items:T[],work:(item:T)=>Promise<R>,concurrency=3):Promise<R[]>{const results:R[]=new Array(items.length);let next=0;await Promise.all(Array.from({length:Math.min(concurrency,items.length)},async()=>{for(;;){const i=next++;if(i>=items.length)return;results[i]=await work(items[i]);}}));return results;}
async function request(url:string,signal:AbortSignal):Promise<unknown>{
 for(let attempt=0;;attempt++){
  try{const response=await fetch(url,{signal:AbortSignal.any([signal,AbortSignal.timeout(30000)]),cache:'no-store'});if(!response.ok){const error=new Error(`HTTP ${response.status}`);if(response.status!==429&&response.status<500)throw Object.assign(error,{permanent:true});throw error;}return await response.json();}
  catch(error){if(signal.aborted||attempt>=2||(error as {permanent?:boolean}).permanent)throw error;await new Promise(resolve=>setTimeout(resolve,(attempt+1)*500));}
 }
}
function publication(value:unknown,source:string){const m=value as {id?:string;rowsUpdatedAt?:number;tableId?:string;columns?:unknown[]};if(m?.id!==source||!m.rowsUpdatedAt||!m.tableId||!Array.isArray(m.columns))throw Error('Source publication metadata unavailable');return JSON.stringify([m.id,m.rowsUpdatedAt,m.tableId,m.columns]);}
export function recentDailyRows(source:string,rows:DataRow[]){
 const field=source==='fx4q-ay7w'?'insp_date':source==='aayw-vxb3'?'report_date':null;
 if(!field)return rows;
 const dated=rows.map(row=>{const raw=readValue(row,[field])??'';return {row,date:/^\d{8}$/.test(raw)?raw:''};});
 dated.sort((a,b)=>b.date.localeCompare(a.date));return dated.map(item=>item.row);
}

export async function completeQuery(source:string,wheres:string[],valid:(row:DataRow)=>boolean,signal:AbortSignal,onRows:(count:number)=>void=()=>{}):Promise<DataSlice>{
 if(!/^[a-z0-9]{4}-[a-z0-9]{4}$/.test(source))throw Error('Invalid source');
 const before=publication(await request(`${base}/api/views/${source}.json`,signal),source);
 const ids=new Set<string>();let loaded=0;
 const batches=await pooled(wheres,async where=>{
  const url=(params:Record<string,string>)=>`${base}/resource/${source}.json?`+new URLSearchParams({'$where':where,...params});
  const count=await request(url({'$select':'count(*) as count'}),signal) as DataRow[];
  const raw=count?.[0]?.count;if(typeof raw!=='string'||!/^\d+$/.test(raw)||!Number.isSafeInteger(Number(raw)))throw Error('Full source count unavailable');
  const total=Number(raw),rows:DataRow[]=[];
  while(rows.length<total){
   const batch=await request(url({'$select':'*, :id as transport_row_id','$order':':id','$limit':'5000','$offset':String(rows.length)}),signal);
   if(!Array.isArray(batch)||!batch.length||batch.length>5000||rows.length+batch.length>total)throw Error('Incomplete or inconsistent full pagination');
   for(const item of batch){const {transport_row_id,...row}=item as DataRow;if(typeof transport_row_id!=='string'||ids.has(transport_row_id)||!valid(row))throw Error('Duplicate, missing or unrelated source identity');ids.add(transport_row_id);rows.push(row);}
   loaded+=batch.length;onRows(loaded);
  }
  return rows;
 });
 const after=publication(await request(`${base}/api/views/${source}.json`,signal),source);if(before!==after)throw Error('Source changed during complete acquisition; retry required');
 const rows=recentDailyRows(source,batches.flat());return {sourceId:source,sourcePublication:after,rows,total:rows.length,truncated:false,scope:'carrier',acquiredAt:new Date().toISOString()};
}
function whereDot(registry:SchemaRegistry,key:EvidenceKey,dot:string){const id=SOURCE_IDS[key],source=registry.sources.find(s=>s.id===id),contract=contracts[id];if(!contract||!['direct_usdot','direct_usdot_legacy'].includes(contract.identity.strategy))throw Error(`No direct USDOT contract for ${id}`);const field=source?.columns.find(c=>c.field_name===contract.identity.field);if(!field?.field_name)throw Error('Registered USDOT field unavailable');const values=legacy.has(key)?[...new Set([dot,dot.padStart(8,'0')])]:[dot];return `${field.field_name} in (${values.map(value=>field.data_type==='number'?String(Number(value)):quote(value)).join(',')})`;}

export async function acquireCompleteCarrier(dot:string,signal:AbortSignal,notify:(p:CompleteProgress)=>void=()=>{}):Promise<CarrierEvidence>{
 if(!/^[1-9][0-9]*$/.test(dot))throw Error('Positive USDOT required');
 const registry=await loadSchemaRegistry(),slices:CarrierEvidence['slices']={},errors:CarrierEvidence['errors']={};
 const keys=Object.keys(SOURCE_IDS) as EvidenceKey[],counts=new Map<string,number>();let finished=0;
 const update=(source:string,status:CompleteProgress['status']='loading')=>notify({finished,total:keys.length,rows:[...counts.values()].reduce((a,b)=>a+b,0),source,status,errors:Object.keys(errors).length});
 async function capture(key:EvidenceKey,work:()=>Promise<DataSlice>){try{slices[key]=await work();}catch(error){errors[key]=error instanceof Error?error.message:String(error);}finally{finished++;update(key);}}
 const direct=(key:EvidenceKey)=>completeQuery(SOURCE_IDS[key],[whereDot(registry,key,dot)],row=>positive(readValue(row,['DOT_NUMBER','USDOT_NUMBER']))===dot,signal,count=>{counts.set(key,count);update(key);});
 await pooled(['census','inspections','legacyCarrier'] as EvidenceKey[],key=>capture(key,()=>direct(key)));
 if(signal.aborted)throw Error('Complete acquisition cancelled');
 const parents=new Set((slices.inspections?.rows??[]).map(row=>readValue(row,['INSPECTION_ID'])));
 if(parents.size!==(slices.inspections?.rows.length??0)||parents.has(undefined))errors.inspections='Inspection business identities are missing or duplicated';
 const bridge=new Map<string,string>();for(const row of slices.legacyCarrier?.rows??[]){const docket=readValue(row,['DOCKET_NUMBER']);if(docket)bridge.set(docket,dot);}
 await pooled(keys.filter(key=>!['census','inspections','legacyCarrier'].includes(key)),key=>capture(key,async()=>{
  if(children.has(key)){
   if(errors.inspections||parents.has(undefined))throw Error('Complete verified inspection parents unavailable');
   const ids=[...parents] as string[];const wheres=chunks(ids,250).map(batch=>`inspection_id in (${batch.map(quote).join(',')})`);
   return {...await completeQuery(SOURCE_IDS[key],wheres,row=>parents.has(readValue(row,['INSPECTION_ID']))&&(!readValue(row,['DOT_NUMBER','USDOT_NUMBER'])||positive(readValue(row,['DOT_NUMBER','USDOT_NUMBER']))===dot),signal,count=>{counts.set(key,count);update(key);}),scope:'loaded_inspections'};
  }
  if(key==='legacyInsurance'){
   if(errors.legacyCarrier)throw Error('Complete legacy docket bridge unavailable');
   const dockets=[...bridge.keys()];if(dockets.some(d=>!/^([A-Za-z]{1,3})[0-9]+$/.test(d)))throw Error('Unresolved docket identity');
   const groups=chunks(dockets,100);
   const proof=await completeQuery(SOURCE_IDS.legacyCarrier,groups.map(b=>`docket_number in (${b.map(quote).join(',')})`),row=>bridge.has(readValue(row,['DOCKET_NUMBER'])??'')&&positive(readValue(row,['DOT_NUMBER']))===dot,signal);
   if(proof.sourcePublication!==slices.legacyCarrier?.sourcePublication)throw Error('Docket publication changed between identity observations');
   if(new Set(proof.rows.map(row=>readValue(row,['DOCKET_NUMBER']))).size!==bridge.size)throw Error('Incomplete global docket ownership proof');
   return {...await completeQuery(SOURCE_IDS[key],groups.map(b=>`prefix_docket_number in (${b.map(quote).join(',')})`),row=>bridge.has(readValue(row,['PREFIX_DOCKET_NUMBER'])??''),signal,count=>{counts.set(key,count);update(key);}),scope:'dockets'};
  }
  return direct(key);
 }));
 const census=slices.census?.rows;if(census?.length!==1)errors.census='Carrier Census identity is not unique or unavailable';
 update('',Object.keys(errors).length?'errors':'complete');
 const completeAll=Object.keys(errors).length===0;
 return {dotNumber:dot,mode:'evidence',loadedAt:new Date().toISOString(),registry,slices,errors,census:census?.length===1?census[0]:undefined,completeAll,
  completenessReceipt:{backend:'live_public_sources',status:completeAll?'LIVE_SOURCE_WINDOW':'PARTIAL',cutId:null,cutAvailableAt:null,warehouseSha256:null,identityContract:sourceContract.identity_contract??null,sourcesExpected:keys.length,sourcesReturned:Object.keys(slices).length,carrierRows:[...counts.values()].reduce((a,b)=>a+b,0),unresolvedRowsExcluded:false,mappingTotals:null,smsReleaseBinding:'UNVERIFIED',historicalFeatureValidity:'NOT_CERTIFIED'}};
}

type WarehouseSource={source_id:string;carrier_rows:number;status:string;scope:string;source_available_at:string;source_rows_updated_at:number;source_sha256:string;rows:DataRow[]};
type WarehousePayload={dot_number:string;cut_id:string;cut_available_at:string;identity_contract:string;source_count:number;carrier_rows:number;warehouse_sha256:string;sources:WarehouseSource[];completeness_receipt:{status:string;sources_expected:number;sources_returned:number;unresolved_rows_excluded_from_carrier_assignment:boolean;mapping_totals:{resolved:number;identified_only:number;unresolved:number};sms_release_binding:string;historical_feature_validity:string}};
export async function acquireWarehouseCarrier(dot:string,signal:AbortSignal,notify:(p:CompleteProgress)=>void=()=>{},baseOverride?:string):Promise<CarrierEvidence>{
 const serviceBase=(baseOverride??warehouseBase).replace(/\/$/,'');if(!serviceBase)throw Error('Verified evidence API is not configured');
 if(!/^[1-9][0-9]*$/.test(dot))throw Error('Positive USDOT required');
 notify({finished:0,total:36,rows:0,source:'warehouse',status:'loading',errors:0,backend:'verified_nationwide_warehouse'});
 const response=await fetch(`${serviceBase}/v1/carriers/${dot}/evidence`,{signal:AbortSignal.any([signal,AbortSignal.timeout(120000)]),headers:{Accept:'application/json'}});
 if(!response.ok)throw Error(`Verified evidence API HTTP ${response.status}`);
 const payload=await response.json() as WarehousePayload;
 if(payload.dot_number!==dot||payload.identity_contract!==sourceContract.identity_contract||payload.source_count!==36||!Array.isArray(payload.sources)||payload.completeness_receipt?.status!=='VERIFIED'||payload.completeness_receipt.sources_expected!==36||payload.completeness_receipt.unresolved_rows_excluded_from_carrier_assignment!==true)throw Error('Verified evidence receipt is invalid');
 if(!payload.cut_id||!/^\d{4}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:\d{2})$/.test(payload.cut_available_at)||Number.isNaN(Date.parse(payload.cut_available_at))||!/^[0-9a-f]{64}$/.test(payload.warehouse_sha256))throw Error('Verified warehouse lineage is invalid');
 const registry=await loadSchemaRegistry(),reverse=new Map<string,EvidenceKey>(Object.entries(SOURCE_IDS).map(([key,id])=>[id,key as EvidenceKey]));
 const slices:CarrierEvidence['slices']={},errors:CarrierEvidence['errors']={};let carrierRows=0;
 for(const source of payload.sources){
  const key=reverse.get(source.source_id),available=Date.parse(source.source_available_at);if(!key||!Number.isSafeInteger(source.carrier_rows)||source.carrier_rows<0||!Array.isArray(source.rows)||source.rows.length!==source.carrier_rows||!/^[0-9a-f]{64}$/.test(source.source_sha256)||!Number.isSafeInteger(source.source_rows_updated_at)||Number.isNaN(available)||source.scope!=='ALL_RESOLVED_ROWS_FOR_USDOT_IN_VERIFIED_NATIONWIDE_CUT'||source.status!==(source.carrier_rows?'ROWS_RETURNED':'NO_ROWS_RETURNED'))throw Error(`Verified source payload is invalid: ${source.source_id}`);
  slices[key]={sourceId:source.source_id,sourcePublication:JSON.stringify([payload.cut_id,source.source_sha256,source.source_rows_updated_at]),rows:recentDailyRows(source.source_id,source.rows),total:source.carrier_rows,truncated:false,scope:'carrier',acquiredAt:source.source_available_at};
  carrierRows+=source.carrier_rows;
 }
 if(Object.keys(slices).length!==36||payload.completeness_receipt.sources_returned!==36||carrierRows!==payload.carrier_rows)throw Error('Verified evidence source coverage or carrier total is inconsistent');
 const census=slices.census?.rows;if(census?.length!==1)throw Error('Verified Census identity is not unique');
 const totals=payload.completeness_receipt.mapping_totals;if(!totals||![totals.resolved,totals.identified_only,totals.unresolved].every(value=>Number.isSafeInteger(value)&&value>=0))throw Error('Verified mapping totals are invalid');
 const receipt:CompletenessReceipt={backend:'verified_nationwide_warehouse',status:'VERIFIED',cutId:payload.cut_id,cutAvailableAt:payload.cut_available_at,warehouseSha256:payload.warehouse_sha256,identityContract:payload.identity_contract,sourcesExpected:payload.completeness_receipt.sources_expected,sourcesReturned:payload.completeness_receipt.sources_returned,carrierRows:payload.carrier_rows,unresolvedRowsExcluded:payload.completeness_receipt.unresolved_rows_excluded_from_carrier_assignment,mappingTotals:{resolved:totals.resolved,identifiedOnly:totals.identified_only,unresolved:totals.unresolved},smsReleaseBinding:payload.completeness_receipt.sms_release_binding==='VERIFIED'?'VERIFIED':'UNVERIFIED',historicalFeatureValidity:payload.completeness_receipt.historical_feature_validity==='CERTIFIED'?'CERTIFIED':'NOT_CERTIFIED'};
 notify({finished:36,total:36,rows:payload.carrier_rows,source:'warehouse',status:'complete',errors:0,backend:receipt.backend,cutId:receipt.cutId,smsReleaseBinding:receipt.smsReleaseBinding});
 return {dotNumber:dot,mode:'evidence',loadedAt:new Date().toISOString(),registry,slices,errors,census:census[0],completeAll:true,completenessReceipt:receipt};
}

type Entry={promise:Promise<CarrierEvidence>;controller:AbortController;progress?:CompleteProgress;listeners:Set<(p:CompleteProgress)=>void>};
const cache=new Map<string,Entry>();
export function completeCarrier(dot:string,notify:(p:CompleteProgress)=>void){
 let entry=cache.get(dot);
 if(!entry){while(cache.size>=2){const oldest=cache.keys().next().value!;cache.get(oldest)?.controller.abort();cache.delete(oldest);}const controller=new AbortController();entry={controller,listeners:new Set(),promise:Promise.resolve(null as unknown as CarrierEvidence)};const current=entry;cache.set(dot,current);const notify=(p:CompleteProgress)=>{current.progress=p;for(const listener of current.listeners)listener(p);};current.promise=(warehouseBase?acquireWarehouseCarrier(dot,controller.signal,notify):acquireCompleteCarrier(dot,controller.signal,notify)).catch(error=>{if(cache.get(dot)===current)cache.delete(dot);throw error;});}
 entry.listeners.add(notify);if(entry.progress)notify(entry.progress);return {promise:entry.promise,unsubscribe:()=>entry!.listeners.delete(notify)};
}
export function retryCompleteCarrier(dot:string){cache.get(dot)?.controller.abort();cache.delete(dot);}
