import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const compiled=await build({stdin:{contents:"export * from './src/releaseLoader.ts';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {loadRelease}=await import('data:text/javascript;base64,'+Buffer.from(compiled.outputFiles[0].text).toString('base64'));
function releaseFixture(){return {schema_version:1,commit:'a'.repeat(40),built_at:'2026-11-06T10:00:00Z',source_metadata:{source_count:36,field_count:810,health_generated_at:'2026-10-23T12:00:00Z'}};}
test('release loader validates metadata with no credentials and independent abort signal',async()=>{
 const original=globalThis.fetch,controller=new AbortController();let options;
 globalThis.fetch=async(url,opts)=>{options=opts;assert.equal(url,'/Transport3r/release-manifest.json');return new Response(JSON.stringify(releaseFixture()));};
 try{const value=await loadRelease('/Transport3r/release-manifest.json',controller.signal);assert.equal(value.commit,'a'.repeat(40));
  assert.equal(options.credentials,'omit');assert.equal(options.cache,'no-store');assert.notEqual(options.signal,controller.signal);
  controller.abort();assert.equal(options.signal.aborted,false,'Completed requests detach their abort listener');
 }finally{globalThis.fetch=original;}
});
test('release failures and malformed/oversized manifests remain explicit failures',async()=>{
 const original=globalThis.fetch;
 try{for(const [body,status] of [['{}',503],['invalid json',200],[JSON.stringify({...releaseFixture(),commit:'wrong'}),200],['x'.repeat(256*1024+1),200]]){
  globalThis.fetch=async()=>new Response(body,{status});
  await assert.rejects(loadRelease('/release-manifest.json',new AbortController().signal));
 }}finally{globalThis.fetch=original;}
});
test('release cancellation during a stalled response body does not become verified metadata',async()=>{
 const original=globalThis.fetch,controller=new AbortController();
 globalThis.fetch=async(url,options)=>({ok:true,text:()=>new Promise((resolve,reject)=>{
  options.signal.addEventListener('abort',()=>reject(options.signal.reason),{once:true});queueMicrotask(()=>controller.abort());
 })});
 try{await assert.rejects(loadRelease('/release-manifest.json',controller.signal),{name:'AbortError'});}finally{globalThis.fetch=original;}
});

test('release loading works without AbortSignal.any or AbortSignal.timeout',async()=>{
 const original=globalThis.fetch,any=Object.getOwnPropertyDescriptor(AbortSignal,'any'),timeout=Object.getOwnPropertyDescriptor(AbortSignal,'timeout');
 Object.defineProperty(AbortSignal,'any',{value:undefined,configurable:true});Object.defineProperty(AbortSignal,'timeout',{value:undefined,configurable:true});
 globalThis.fetch=async()=>new Response(JSON.stringify(releaseFixture()));
 try{assert.equal((await loadRelease('/release-manifest.json',new AbortController().signal)).sources,36);}
 finally{globalThis.fetch=original;if(any)Object.defineProperty(AbortSignal,'any',any);else delete AbortSignal.any;if(timeout)Object.defineProperty(AbortSignal,'timeout',timeout);else delete AbortSignal.timeout;}
});
test('an already-cancelled release request never reaches fetch',async()=>{
 const original=globalThis.fetch,controller=new AbortController();let calls=0;controller.abort();
 globalThis.fetch=async()=>{calls++;throw Error('Should not fetch');};
 try{await assert.rejects(loadRelease('/release-manifest.json',controller.signal),{name:'AbortError'});assert.equal(calls,0);}finally{globalThis.fetch=original;}
});
test('the release deadline aborts a stalled request and is cleaned up',async()=>{
 const original=globalThis.fetch,set=globalThis.setTimeout,clear=globalThis.clearTimeout;let cancelled=0;
 globalThis.setTimeout=(callback,ms)=>{assert.equal(ms,15000);queueMicrotask(callback);return 123;};
 globalThis.clearTimeout=id=>{assert.equal(id,123);cancelled++;};
 globalThis.fetch=async(url,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
 try{await assert.rejects(loadRelease('/release-manifest.json',new AbortController().signal),{name:'AbortError'});assert.equal(cancelled,1);}
 finally{globalThis.fetch=original;globalThis.setTimeout=set;globalThis.clearTimeout=clear;}
});
