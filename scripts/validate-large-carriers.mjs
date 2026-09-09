// Exercise production mapping and bounded count queries on large real carriers.
import {build} from 'esbuild';
import {readFile,writeFile} from 'node:fs/promises';
import {queryLiveSource} from './live-source-retry.mjs';
const compiled=await build({stdin:{contents:"export * from './src/datahub'; export {carrierFromRow} from './src/CarrierRouteApp';",resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const registry=JSON.parse(await readFile('public/data/source-schemas.json','utf8'));
const carriers=await Promise.all(['80806','54283','264184','265752'].map(async dot=>{
  try {
    const [censusQuery,inspectionQuery]=await Promise.all([
      queryLiveSource(()=>app.queryByDot(registry,'az4n-8mr2',dot,{limit:2})),
      queryLiveSource(()=>app.queryByDot(registry,'fx4q-ay7w',dot,{limit:500,includeTotal:true,orderAliases:['INSP_DATE']}),{requireTotal:true}),
    ]);
    const census=censusQuery.slice, inspections=inspectionQuery.slice;
    if(census.rows.length!==1 || census.truncated) throw new Error('Ambiguous Census identity');
    const carrier=app.carrierFromRow(census.rows[0]);
    if(carrier.dotNumber!==dot || !/^\d+$/.test(carrier.drivers??'') || Number(carrier.drivers)<1000) throw new Error('Missing or invalid large-carrier driver exposure');
    if(carrier.drivers!==census.rows[0].total_drivers) throw new Error('Driver mapping differs from TOTAL_DRIVERS');
    if(inspections.total===null || inspections.rows.length!==Math.min(500,inspections.total) || inspections.truncated!==(inspections.total>500)) throw new Error('Full inspection count and loaded window were not distinguished');
    if(inspections.rows.some(row=>String(row.dot_number)!==dot)) throw new Error('Inspection identity mismatch');
    return {dot,name:carrier.legalName,drivers:carrier.drivers,power_units:carrier.powerUnits,mcs150_date:carrier.mcs150Date,census_status:app.censusStatusLabel(carrier.statusCode),inspection_source:'fx4q-ay7w',inspection_total:inspections.total,loaded_inspections:inspections.rows.length,truncated:inspections.truncated,latest_loaded_date:inspections.rows[0]?.insp_date??null,acquisition_attempts:{census:censusQuery.attempts,inspections:inspectionQuery.attempts},status:'PASS'};
  } catch(error) {return {dot,status:'FAIL',error:error.message,acquisition_attempts:error.attempts??[]};}
}));
const result={status:carriers.every(c=>c.status==='PASS')?'PASS':'FAIL',captured_at:new Date().toISOString(),scope:'Full available daily inspection-file history; not a standardized 24-month or SAFER count. Counts and rows are separately queried observations.',carriers};
const output=JSON.stringify(result,null,2);
console.log(output);
if(process.argv[2]) await writeFile(process.argv[2],output);
if(result.status!=='PASS') process.exitCode=1;
