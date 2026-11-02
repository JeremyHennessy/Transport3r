import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

const result=await build({stdin:{contents:"export * from './src/insuranceLineModel.ts';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {buildInsuranceLines}=await import('data:text/javascript;base64,'+Buffer.from(result.outputFiles[0].text).toString('base64'));
const base={dotNumber:'3938496',census:{hm_ind:'Y',total_drivers:'3'},errors:{},slices:{}};
const slice=(rows,truncated=false)=>({rows,truncated});

test('eight underwriting lines, no invented risk score',()=>{
 const lines=buildInsuranceLines(base);
 assert.equal(lines.length,8);
 assert.equal(new Set(lines.map(x=>x.id)).size,8);
 assert.ok(lines.every(x=>!('riskScore' in x)&&!('probability' in x)));
 assert.ok(lines.every(x=>x.href.startsWith('#/carrier/3938496/')));
});
test('missing and failed evidence never become a clean zero',()=>{
 const a=buildInsuranceLines({...base,errors:{crash:'HTTP 503'},slices:{inspections:slice([])}}).find(x=>x.id==='auto-liability');
 assert.equal(a.evidenceStatus,'Incomplete public context');
 assert.match(a.snapshot,/source unavailable/);
 assert.match(a.snapshot,/0 inspection rows returned/);
});
test('partial sources are lower bounds',()=>{
 const a=buildInsuranceLines({...base,slices:{crash:slice([{}],true),inspections:slice([{},{}]),violations:slice([])}}).find(x=>x.id==='auto-liability');
 assert.equal(a.evidenceStatus,'Incomplete public context');
 assert.match(a.snapshot,/At least 1 crash-involvement rows/);
});
test('hazmat registration does not mean confirmed cargo or incident',()=>{
 const l=buildInsuranceLines(base);
 assert.match(l.find(x=>x.id==='motor-truck-cargo').snapshot,/indicator: Y/);
 assert.equal(l.find(x=>x.id==='motor-truck-cargo').evidenceStatus,'Additional evidence required');
 assert.match(l.find(x=>x.id==='environmental-hazmat').limitations,/not evidence/);
});
