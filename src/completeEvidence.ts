import {loadSchemaRegistry,readValue,type DataRow,type DataSlice,type SchemaRegistry} from './datahub';
import {SOURCE_IDS,type CarrierEvidence,type EvidenceKey} from './carrierEvidence';

export type CompleteProgress={finished:number;total:number;rows:number;source:string;status:'loading'|'complete'|'errors';errors:number};
const legacy=new Set(['legacyCarrier','legacyActivePendingInsurance','legacyAuthHistory','legacyBoc3','legacyInsuranceHistory','legacyRejected','legacyRevocation']);
const children=new Set(['units','violations','citations','specialStudies']);
const base='https://data.transportation.gov';
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
function whereDot(registry:SchemaRegistry,key:EvidenceKey,dot:string){const source=registry.sources.find(s=>s.id===SOURCE_IDS[key]);const field=source?.columns.find(c=>['dot_number','usdot_number'].includes(c.field_name??''));if(!field?.field_name)throw Error('Registered USDOT field unavailable');const values=legacy.has(key)?[...new Set([dot,dot.padStart(8,'0')])]:[dot];return `${field.field_name} in (${values.map(value=>field.data_type==='number'?String(Number(value)):quote(value)).join(',')})`;}

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
 return {dotNumber:dot,mode:'evidence',loadedAt:new Date().toISOString(),registry,slices,errors,census:census?.length===1?census[0]:undefined,completeAll:Object.keys(errors).length===0};
}

type Entry={promise:Promise<CarrierEvidence>;controller:AbortController;progress?:CompleteProgress;listeners:Set<(p:CompleteProgress)=>void>};
const cache=new Map<string,Entry>();
export function completeCarrier(dot:string,notify:(p:CompleteProgress)=>void){
 let entry=cache.get(dot);
 if(!entry){while(cache.size>=2){const oldest=cache.keys().next().value!;cache.get(oldest)?.controller.abort();cache.delete(oldest);}const controller=new AbortController();entry={controller,listeners:new Set(),promise:Promise.resolve(null as unknown as CarrierEvidence)};const current=entry;cache.set(dot,current);current.promise=acquireCompleteCarrier(dot,controller.signal,p=>{current.progress=p;for(const listener of current.listeners)listener(p);}).catch(error=>{if(cache.get(dot)===current)cache.delete(dot);throw error;});}
 entry.listeners.add(notify);if(entry.progress)notify(entry.progress);return {promise:entry.promise,unsubscribe:()=>entry!.listeners.delete(notify)};
}
export function retryCompleteCarrier(dot:string){cache.get(dot)?.controller.abort();cache.delete(dot);}
