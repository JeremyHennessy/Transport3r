// Compare exported web/Power BI facts only after their provenance and scope agree.
import {readFile,writeFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const dimensions=['dotNumber','sourceId','sourceCut','windowStart','windowEnd','dateField','grain','filters'];
export function compareMeasureSnapshots(left,right){
 const differences=[];
 for(const key of dimensions){
  if(typeof left[key]!=='string'||!left[key].trim()||typeof right[key]!=='string'||!right[key].trim())differences.push(`MISSING_CONTEXT:${key}`);
  else if(left[key]!==right[key])differences.push(`DIFFERENT_CONTEXT:${key}`);
 }
 if(differences.length)return {status:'NOT_COMPARABLE',differences};
 const a=left.measures??{},b=right.measures??{};
 const names=[...new Set([...Object.keys(a),...Object.keys(b)])];
 if(!names.length)return {status:'NOT_COMPARABLE',differences:['NO_MEASURES']};
 const checks=names.map(name=>({name,left:a[name]??null,right:b[name]??null,status:typeof a[name]!=='number'||!Number.isFinite(a[name])||typeof b[name]!=='number'||!Number.isFinite(b[name])?'UNAVAILABLE':a[name]===b[name]?'MATCH':'MISMATCH'}));
 return {status:checks.some(c=>c.status==='MISMATCH')?'MISMATCH':checks.some(c=>c.status==='UNAVAILABLE')?'INCOMPLETE':'MATCH',checks};
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href){
 const [left,right,out]=process.argv.slice(2);if(!left||!right||!out)throw new Error('Usage: node scripts/compare-measure-snapshots.mjs web.json powerbi.json result.json');
 const result=compareMeasureSnapshots(JSON.parse(await readFile(left,'utf8')),JSON.parse(await readFile(right,'utf8')));
 await writeFile(out,JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));if(result.status!=='MATCH')process.exitCode=1;
}
