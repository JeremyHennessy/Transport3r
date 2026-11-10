import {sourceRetryDelay} from './live-source-retry.mjs';
// All production evidence keys are exercised for an inactive/sparse and an active carrier.
import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
const compiled=await build({stdin:{contents:"export * from './src/datahub'; export * from './src/carrierEvidence'; export {carrierFromRow} from './src/CarrierRouteApp';",resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const original=globalThis.fetch;
globalThis.fetch=(url,options)=>String(url).endsWith('/data/source-schemas.json')?Promise.resolve(new Response(JSON.stringify(registry))):original(url,options);
const carriers=[];
let currentAttempt=null;
try {
 for(const dot of ['2855794','3938496']) {
  const attempts=[];let evidence;currentAttempt={dot,attempts};
  for(let attempt=1;attempt<=3;attempt++) {
   evidence=await app.loadCarrierEvidence(dot,'evidence');
   const messages=Object.values(evidence.errors);
   const delay=messages.length?sourceRetryDelay(messages,attempt):null;
   attempts.push({attempt,errors:evidence.errors,retry_after_ms:attempt<3?delay:null});
   if(!messages.length)break;
   if(attempt>=3||delay===null)break;
   await new Promise(resolve=>setTimeout(resolve,delay));
  }
  const checks=[];
  for(const [key,sourceId] of Object.entries(app.SOURCE_IDS)) {
   const slice=evidence.slices[key];
   if(!slice||evidence.errors[key])throw new Error(`${dot}/${key}: ${evidence.errors[key]??'missing mapping'}`);
   if(slice.sourceId!==sourceId)throw new Error(`${dot}/${key}: source identity differs`);
   const schema=app.sourceSchema(registry,sourceId);
   const column=app.findColumn(schema,['DOT_NUMBER','USDOT_NUMBER','USDOT_NUM','USDOT_NO','DOT_NO','US_DOT_NUMBER']);
   if(slice.scope==='carrier'&&column?.field_name&&slice.rows.some(row=>Number(row[column.field_name])!==Number(dot)))throw new Error(`${dot}/${key}: foreign carrier row`);
   if(slice.scope==='loaded_inspections') {
    const ids=new Set(evidence.slices.inspections.rows.map(app.inspectionId));
    if(slice.rows.some(row=>!ids.has(app.inspectionId(row))))throw new Error(`${dot}/${key}: orphan inspection child`);
   }
   checks.push({key,sourceId,rows:slice.rows.length,total:slice.total,truncated:slice.truncated,scope:slice.scope??null,status:'PASS'});
  }
  const census=evidence.slices.census.rows;
  if(census.length!==1)throw new Error(`${dot}: ambiguous Census identity`);
  const carrier=app.carrierFromRow(census[0]);
  if(carrier.drivers!==census[0].total_drivers||carrier.powerUnits!==census[0].power_units)throw new Error(`${dot}: exposure mapping mismatch`);
  carriers.push({dot,name:carrier.legalName,registration:carrier.statusCode,report_date:carrier.mcs150Date,drivers:carrier.drivers,power_units:carrier.powerUnits,inspection_availability:app.inspectionAvailability(evidence),attempts,checks});
 }
 const result={status:'PASS',checked_at:new Date().toISOString(),scope:'All configured source mappings for two carriers; not population-wide data completeness or history validation.',carriers};
 console.log(JSON.stringify({status:result.status,carriers:carriers.map(c=>({dot:c.dot,mappings:c.checks.length,inspections:c.checks.find(s=>s.key==='inspections')}))},null,2));
 if(process.argv[2])await writeFile(process.argv[2],JSON.stringify(result,null,2));
}catch(error){
 const result={status:'FAIL',checked_at:new Date().toISOString(),error:error.message,carriers,failed_carrier:currentAttempt};
 if(process.argv[2])await writeFile(process.argv[2],JSON.stringify(result,null,2));
 throw error;
}finally{globalThis.fetch=original;}
