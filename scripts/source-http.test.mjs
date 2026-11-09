import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const bundle=await build({stdin:{contents:"export * from './src/sourceHttp'",loader:'ts',resolveDir:process.cwd()},bundle:true,write:false,platform:'node',format:'esm'});
const {sourceJson,retryAfterMilliseconds,mapLimited}=await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString('base64')}`);
test('Retry-After seconds and dates are bounded, malformed numeric strings rejected',()=>{
 assert.equal(retryAfterMilliseconds('2'),2000);
 assert.equal(retryAfterMilliseconds('Mon, 09 Nov 2026 19:00:02 GMT',Date.parse('2026-11-09T19:00:00Z')),2000);
 for(const value of [null,'-1','1.5','bad','99999999999999999999'])assert.equal(retryAfterMilliseconds(value),null);
});
test('throttled GET retries without changing a successful known zero',async t=>{
 let calls=0;const urls=[];t.mock.method(globalThis,'fetch',async(url)=>{urls.push(url);return ++calls===1?new Response('Rate limited',{status:429,headers:{'Retry-After':'0'}}):Response.json([{count:'0'}]);});
 assert.deepEqual(await sourceJson('https://source.test/?q=exact',{},2000),[{count:'0'}]);assert.equal(calls,2);assert.equal(new Set(urls).size,1);
});
test('long Retry-After does not exceed deadline or immediately repeat request',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response('Busy',{status:429,headers:{'Retry-After':'60'}});});
 await assert.rejects(sourceJson('https://source.test',{},100),/HTTP 429.*retry-after 60000ms/);assert.equal(calls,1);
});
test('permanent status, malformed JSON and POST are not retried',async t=>{
 for(const [response,init] of [[new Response('Bad',{status:400}),{}],[new Response('Missing',{status:404}),{}],[new Response('{broken'),{}],[new Response('Busy',{status:503}),{method:'POST'}]]){
  let calls=0;const mocked=t.mock.method(globalThis,'fetch',async()=>{calls++;return response;});
  await assert.rejects(sourceJson('https://source.test',init,1000));assert.equal(calls,1);mocked.mock.restore();
 }
});
test('caller cancellation works before fetch and during retry wait',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return new Response('Busy',{status:503});});
 const a=new AbortController();a.abort();await assert.rejects(sourceJson('https://source.test',{signal:a.signal}),{name:'AbortError'});assert.equal(calls,0);
 const b=new AbortController();const pending=sourceJson('https://source.test',{signal:b.signal});setTimeout(()=>b.abort(),20);
 await assert.rejects(pending,{name:'AbortError'});assert.equal(calls,1);
});
test('deadline includes response body',async t=>{
 t.mock.method(globalThis,'fetch',async(_,options)=>({ok:true,json:()=>new Promise((_,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('stop','AbortError')),{once:true}))}));
 await assert.rejects(sourceJson('https://source.test',{},20),/timed out/);
});
test('bounded worker concurrency retains input order',async()=>{
 let active=0,peak=0;const result=await mapLimited(Array.from({length:13},(_,i)=>i),async i=>{active++;peak=Math.max(peak,active);await new Promise(r=>setTimeout(r,5));active--;return i*2;},4);
 assert.equal(peak,4);assert.deepEqual(result,Array.from({length:13},(_,i)=>i*2));
});
