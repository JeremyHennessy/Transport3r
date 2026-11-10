import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const built=await build({stdin:{contents:"export * from './src/atlasLoadState';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {atlasLoadReducer:reduce,initialAtlasLoadState:initial}=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const evidence=dotNumber=>({dotNumber,slices:{},errors:{},loadedAt:'2026-11-09T00:00:00Z'});
test('refresh revision clears prior evidence until its matching completion',()=>{
 let s=reduce(initial,{type:'start',generation:1});
 s=reduce(s,{type:'complete',generation:1,evidence:evidence('1')});
 const prior=s;s=reduce(s,{type:'start',generation:2});
 assert.equal(prior.status,'loaded');assert.equal(s.status,'loading');assert.equal(s.evidence,null);
 assert.equal(reduce(s,{type:'complete',generation:1,evidence:evidence('1')}),s);
 s=reduce(s,{type:'complete',generation:2,evidence:evidence('2')});
 assert.equal(s.status,'loaded');assert.equal(s.evidence.dotNumber,'2');
});
test('invalid submission revokes an in-flight success and error without restoring the map',async()=>{
 let finish;const pending=new Promise(resolve=>{finish=resolve;});
 let s=reduce(initial,{type:'start',generation:1});
 const update=pending.then(value=>{s=reduce(s,{type:'complete',generation:1,evidence:value});});
 s=reduce(s,{type:'invalidate',generation:2,error:'Invalid USDOT'});
 finish(evidence('1'));await update;
 assert.equal(s.status,'invalid');assert.equal(s.evidence,null);assert.equal(s.error,'Invalid USDOT');
 assert.equal(reduce(s,{type:'fail',generation:1,error:'Older request failed'}),s);
});
test('cleared route stays empty after late response',()=>{
 let s=reduce(initial,{type:'start',generation:1});s=reduce(s,{type:'clear',generation:2});
 assert.equal(s.status,'idle');assert.equal(reduce(s,{type:'complete',generation:1,evidence:evidence('1')}),s);
});
test('a current failure clears old data and a later retry can succeed',()=>{
 let s=reduce(initial,{type:'start',generation:1});s=reduce(s,{type:'fail',generation:1,error:'Source unavailable'});
 assert.equal(s.status,'failed');assert.equal(s.evidence,null);
 s=reduce(s,{type:'start',generation:2});assert.equal(s.error,'');
 s=reduce(s,{type:'complete',generation:2,evidence:evidence('2')});assert.equal(s.status,'loaded');
});
test('duplicate or stale transitions cannot overwrite a terminal result',()=>{
 let s=reduce(initial,{type:'start',generation:1});s=reduce(s,{type:'complete',generation:1,evidence:evidence('1')});
 for(const action of [{type:'complete',generation:1,evidence:evidence('2')},{type:'fail',generation:1,error:'late'},
 {type:'start',generation:1},{type:'clear',generation:1}])assert.equal(reduce(s,action),s);
});
test('invalid request sequence cannot enter application state',()=>{
 for(const generation of [0,-1,NaN,Infinity,1.5,Number.MAX_SAFE_INTEGER+1]){
  assert.throws(()=>reduce(initial,{type:'start',generation}));
 }
 assert.equal(initial.status,'idle');assert.equal(initial.generation,0);
});
