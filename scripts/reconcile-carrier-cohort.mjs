// Retained, deterministic strata and production mapping; no model or historical reconstruction.
import {build} from 'esbuild';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {queryLiveSource} from './live-source-retry.mjs';
const out=process.argv[2]??'outputs/reconciliation'; await mkdir(out,{recursive:true});
const compiled=await build({stdin:{contents:"export * from './src/datahub'; export * from './src/evidenceCoverage'; export {carrierFromRow} from './src/CarrierRouteApp';",resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const acquisitionAttempts=[];
async function fetchRecorded(url){
 try{
  const {slice,attempts}=await queryLiveSource(()=>app.fetchSourceJson(url,{},30000));
  acquisitionAttempts.push({url,attempts});return slice;
 }catch(error){
  acquisitionAttempts.push({url,attempts:error.attempts??[],error:error.message});
  await writeFile(`${out}/acquisition-attempts.json`,JSON.stringify(acquisitionAttempts,null,2));
  throw new Error(`Source acquisition failed after bounded attempts: ${url}: ${error.message}`);
 }
}
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const sourceIds=['az4n-8mr2','fx4q-ay7w','aayw-vxb3','rbkj-cgst','kjg3-diqy'];
const metadata=async()=>Object.fromEntries(await Promise.all(sourceIds.map(async id=>{const m=await fetchRecorded(`https://data.transportation.gov/api/views/${id}`);return [id,{rowsUpdatedAt:m.rowsUpdatedAt??null,viewLastModified:m.viewLastModified??null}];})));
const before=await metadata();
const strata=[['large_active',"status_code='A' AND power_units::number>=1000"],['inactive',"status_code='I'"],['passenger',"status_code='A' AND bus_units::number>0"],['small_active',"status_code='A' AND power_units::number between 1 and 5"],['intrastate',"status_code='A' AND carrier_operation='C'"]];
const cohort=new Map(), selections=[];
for(const [name,where] of strata){
 for(const direction of ['ASC','DESC']){
 const params=new URLSearchParams({'$where':where,'$order':`dot_number ${direction}`,'$limit':'10'});
 const url=`https://data.transportation.gov/resource/az4n-8mr2.json?${params}`;
 const rows=await fetchRecorded(url);if(!Array.isArray(rows)||!rows.length)throw new Error(`No cohort rows for ${name}`);
 selections.push({stratum:name,direction,url,rows});
 for(const row of rows){const dot=String(row.dot_number);const prior=cohort.get(dot);cohort.set(dot,{row,strata:[...(prior?.strata??[]),name]});}
 }
}
const fixed=['2855794','80806','54283','264184','265752','3938496'];
for(const dot of fixed){if(!cohort.has(dot)){const {slice}=await queryLiveSource(()=>app.queryByDot(registry,'az4n-8mr2',dot,{limit:2}));if(slice.rows.length!==1)throw new Error(`Ambiguous Census ${dot}`);cohort.set(dot,{row:slice.rows[0],strata:['prior_regression']});}}
const detailed=[...new Set([...fixed,...selections.flatMap(selection=>selection.rows.slice(0,2).map(row=>String(row.dot_number)))])];
const carriers=[],errors=[];
for(const [dot,entry] of cohort){
 const carrier=app.carrierFromRow(entry.row);
 const discrepancies=[];
 for(const [field,source] of [['drivers','total_drivers'],['powerUnits','power_units'],['mcs150Date','mcs150_date'],['statusCode','status_code']]){
  if((carrier[field]??null)!==(app.readValue(entry.row,[source])??null))discrepancies.push(`CENSUS_MAPPING:${field}`);
 }
 const observation={dot,strata:entry.strata,census:entry.row,discrepancies,detailed:detailed.includes(dot)};
 if(observation.detailed){
  const slices={},attempts={};
  for(const [key,id,limit,dates] of [['inspections','fx4q-ay7w',500,['INSP_DATE']],['crash','aayw-vxb3',350,['CRASH_DATE','REPORT_DATE']],['smsInspection','rbkj-cgst',1000,['INSP_DATE']],['smsCensus','kjg3-diqy',5,[]]]){
   try{
    const acquired=await queryLiveSource(()=>app.queryByDot(registry,id,dot,{limit,includeTotal:true,orderAliases:dates}),{requireTotal:true});
    const slice=acquired.slice;slices[key]=slice;attempts[key]=acquired.attempts;
    if(slice.rows.some(row=>String(row.dot_number)!==dot))discrepancies.push(`FOREIGN_USDOT:${key}`);
    if(slice.rows.length!==Math.min(limit,slice.total)||slice.truncated!==(slice.total>limit))discrepancies.push(`COUNT_WINDOW:${key}`);
    if(key==='inspections'||key==='smsInspection'){
     const ids=slice.rows.map(row=>app.readValue(row,[key==='inspections'?'INSPECTION_ID':'UNIQUE_ID']));
     if(ids.some(id=>!id)||new Set(ids).size!==ids.length)discrepancies.push(`MISSING_OR_DUPLICATE_ID:${key}`);
    }
   }catch(error){errors.push({dot,key,error:error.message});}
  }
  observation.slices=slices;observation.attempts=attempts;
  observation.coverage=app.coverageReport({dotNumber:dot,mode:'evidence',loadedAt:new Date().toISOString(),registry,slices,errors:{}},entry.row);
  observation.coverage.sources=observation.coverage.sources.filter(source=>['inspections','crash','smsInspection','smsCensus'].includes(source.key));
  observation.coverage.mode='core_reconciliation';
  observation.comparison='Daily and SMS source counts are separate populations/windows. Differences are retained, not forced equal; Power BI comparison requires matching source cut and scope.';
 }
 carriers.push(observation);
 console.log(`${dot}: ${observation.detailed?'detailed':'Census'} ${discrepancies.length?'DISCREPANCY':'mapped'}`);
}
const after=await metadata();
await writeFile(`${out}/acquisition-attempts.json`,JSON.stringify(acquisitionAttempts,null,2));
const changedSources=sourceIds.filter(id=>JSON.stringify(before[id])!==JSON.stringify(after[id]));
const payload=JSON.stringify({selections,carriers},null,2);await writeFile(`${out}/observations.json`,payload);
const summary={version:1,checkedAt:new Date().toISOString(),status:errors.length||carriers.some(c=>c.discrepancies.length)?'FAIL':changedSources.length?'SOURCE_CHANGED':'PASS',censusCarriers:carriers.length,detailedCarriers:detailed.length,strata:selections.map(s=>({name:s.stratum,rows:s.rows.length})),errors,discrepancies:carriers.filter(c=>c.discrepancies.length).map(c=>({dot:c.dot,issues:c.discrepancies})),before,after,changedSources,observationsSha256:createHash('sha256').update(payload).digest('hex'),powerBi:'NOT_EXECUTED: imported Power BI source data and matching refresh cuts were not supplied.',limitations:'Deterministic engineering sample, not population certification. Stable metadata around acquisition is not a transactional or monthly historical snapshot. Full counts and bounded rows queried separately; acquisition races remain possible.'};
await writeFile(`${out}/summary.json`,JSON.stringify(summary,null,2));console.log(JSON.stringify(summary,null,2));if(summary.status!=='PASS')process.exitCode=1;
