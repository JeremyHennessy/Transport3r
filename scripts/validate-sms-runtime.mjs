// Execute the application TypeScript, not a separate reimplementation, against retained official inputs.
import { readFile } from 'node:fs/promises';
import { build } from 'esbuild';
const compiled = await build({stdin:{contents: "export * from './src/smsReplay';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const r = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const sample = JSON.parse(await readFile(process.argv[2], 'utf8'));
const slice = (rows) => ({rows,total:rows.length,truncated:false,sourceId:'validation'});
const comparisons=[], failures=[], unavailable=[];
if(new Set(sample.carriers.map(c=>c.dot_number)).size!==sample.carriers.length) throw new Error('Duplicate carrier in validation sample');
for(const carrier of sample.carriers) {
  if(String(carrier.official.dot_number)!==carrier.dot_number) throw new Error('Official output carrier mismatch');
  if(carrier.inspections.length>=10000 || carrier.violations.length>=20000) throw new Error('Validation sample hit an acquisition limit');
  const outputs={};
  for(const key of ['smsABProperty','smsCProperty','smsABPass','smsCPass']) {
    if(!Array.isArray(carrier.outputs?.[key]) || carrier.outputs[key].length>=5) throw new Error(`Missing or capped population query: ${key}`);
    outputs[key]=slice(carrier.outputs[key]);
  }
  const evidence={dotNumber:carrier.dot_number,errors:{},slices:{smsInspection:slice(carrier.inspections),smsViolation:slice(carrier.violations),...outputs}};
  for(const result of r.replayCarrierInspectionMeasures(evidence)) {
    if(result.status==='PARTIAL_DATA') failures.push({dot:carrier.dot_number,basic:result.basic,issues:result.inputIssues,officialOutputIssues:result.officialOutputIssues});
    if(result.officialMeasure!==null) {
      if(result.status==='NO_DENOMINATOR' && result.officialMeasure===0 && result.denominator===0) {
        unavailable.push({dot:carrier.dot_number,basic:result.basic,official:0,reason:'No relevant inspection denominator; not a numeric comparison'});
        continue;
      }
      if(result.calculatedMeasure===null || Math.abs(result.calculatedMeasure-result.officialMeasure)>0.015) failures.push({dot:carrier.dot_number,basic:result.basic,status:result.status,delta:result.delta});
      comparisons.push({dot:carrier.dot_number,basic:result.basic,official:result.officialMeasure,replay:result.calculatedMeasure,delta:result.delta});
    }
  }
}
const result={status:!failures.length && sample.carriers.length>=6 && comparisons.length>=12?'PASS':'FAIL',captured_at:sample.captured_at,carriers:sample.carriers.length,comparisons:comparisons.length,unavailable,failures,results:comparisons};
console.log(JSON.stringify(result,null,2));
if(result.status!=='PASS') process.exitCode=1;

