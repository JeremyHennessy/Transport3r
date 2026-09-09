import { SMS_OUTPUT_KEYS, SOURCE_IDS, selectOfficialSmsOutput, type CarrierEvidence } from './carrierEvidence';
import { fetchSourceJson, findColumn, readValue, type DataRow, type SchemaRegistry } from './datahub';

export const PUBLIC_SMS_BASICS = [
  {key:'unsafe_driv',label:'Unsafe Driving',short:'Unsafe'},
  {key:'hos_driv',label:'Hours-of-Service Compliance',short:'HOS'},
  {key:'driv_fit',label:'Driver Fitness',short:'Fitness'},
  {key:'contr_subst',label:'Controlled Substances / Alcohol',short:'Substances'},
  {key:'veh_maint',label:'Vehicle Maintenance',short:'Vehicle'},
] as const;
export function officialNumeric(row:DataRow,key:string,max=Infinity):number|null {
  const raw=readValue(row,[key])?.trim();
  if(!raw||!/^\d*(?:\.\d+)?$/.test(raw))return null;
  const value=Number(raw);return Number.isFinite(value)&&value>=0&&value<=max?value:null;
}
export function officialPercentile(row:DataRow,key:string):number|null {
  const raw=readValue(row,[key])?.trim();
  return raw?officialNumeric({value:raw.replace(/%$/,'')},'value',100):null;
}
export function officialSmsView(evidence:CarrierEvidence) {
  const selected=selectOfficialSmsOutput(evidence);
  const passenger=selected.sourceId==='m3ry-qcip'||selected.sourceId==='h3zn-uid9';
  const status=selected.issues.length?'unavailable':selected.row?'available':'empty';
  const sources=SMS_OUTPUT_KEYS.map(key=>({id:SOURCE_IDS[key],acquiredAt:evidence.slices[key]?.acquiredAt??null,error:evidence.errors[key]??null}));
  return {status,sourceId:selected.sourceId,passenger,issues:selected.issues,sources,
    basics:PUBLIC_SMS_BASICS.map(basic=>({...basic,
      measure:selected.row?officialNumeric(selected.row,`${basic.key}_measure`):null,
      percentile:selected.row&&passenger?officialPercentile(selected.row,`${basic.key}_pct`):null,
      alert:selected.row&&passenger?readValue(selected.row,[`${basic.key}_basic_alert`])??null:null,
    }))};
}
export type OfficialSmsView=ReturnType<typeof officialSmsView>;

// Four batched lookups for up to 100 visible carriers, rather than four requests per row.
export async function loadOfficialSmsBatch(registry:SchemaRegistry,requested:string[]):Promise<Record<string,CarrierEvidence>> {
  const dots=[...new Set(requested)];
  if(!dots.length)return {};
  if(dots.length>100||dots.some(dot=>!/^[1-9]\d*$/.test(dot)))throw new Error('SMS batch requires 1–100 valid USDOT numbers.');
  const records=Object.fromEntries(dots.map(dot=>[dot,{dotNumber:dot,mode:'summary',loadedAt:new Date().toISOString(),registry,slices:{},errors:{}} as CarrierEvidence]));
  await Promise.all(SMS_OUTPUT_KEYS.map(async key=>{
    const id=SOURCE_IDS[key];
    try{
      const schema=registry.sources.find(source=>source.id===id),column=schema&&findColumn(schema,['DOT_NUMBER']);
      if(!column?.field_name||!['text','number'].includes(column.data_type??''))throw new Error('SMS USDOT schema unavailable.');
      const values=dots.map(dot=>column.data_type==='number'?dot:`'${dot}'`).join(',');
      const params=new URLSearchParams({'$where':`${column.field_name} in (${values})`,'$order':`${column.field_name}, :id`,'$limit':String(dots.length*2+1)});
      const rows=await fetchSourceJson(`https://data.transportation.gov/resource/${id}.json?${params}`,{},15000);
      if(!Array.isArray(rows))throw new Error('SMS source returned a non-array response.');
      if(rows.length>dots.length*2)throw new Error('SMS batch exceeded the accepted output window.');
      const grouped=new Map(dots.map(dot=>[dot,[] as DataRow[]]));
      for(const row of rows){if(!row||typeof row!=='object'||Array.isArray(row))throw new Error('Invalid SMS record.');const dot=readValue(row,['DOT_NUMBER'])?.trim();if(!dot||!grouped.has(dot))throw new Error('SMS batch returned an unrelated USDOT.');grouped.get(dot)!.push(row);}
      const acquiredAt=new Date().toISOString();
      for(const dot of dots)records[dot].slices[key]={sourceId:id,rows:grouped.get(dot)!,total:grouped.get(dot)!.length,truncated:false,scope:'carrier',acquiredAt};
    }catch(cause){for(const dot of dots)records[dot].errors[key]=cause instanceof Error?cause.message:String(cause);}
  }));
  return records;
}
