import {mkdtemp,rm,writeFile} from 'node:fs/promises';
import {createServer} from 'node:http';
import {tmpdir} from 'node:os';
import {join,resolve,sep} from 'node:path';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';

const root=resolve('.'), scenario=process.env.BROWSER_SCENARIO??'recovery';
const harness=scenario==='data-ui'?'data-ui-browser.js':scenario==='coverage'?'coverage-browser.js':scenario==='inspection'?'inspection-browser.js':scenario==='date-enrichment'?'date-enrichment-browser.js':scenario==='sms-display'?'sms-display-browser.js':scenario==='insight'?'insight-browser.js':'carrier-recovery-browser.js';
const script=await import('node:fs/promises').then(fs=>fs.readFile(join(root,'scripts',harness),'utf8'));
const profile=await mkdtemp(join(tmpdir(),'transport3r-recovery-'));
const server=createServer(async(req,res)=>{
 try{
  const pathname=new URL(req.url??'/', 'http://127.0.0.1').pathname;
  if(pathname==='/__harness.js'){res.setHeader('content-type','application/javascript');res.end(script);return;}
  const target=pathname==='/'?'index.html':pathname.slice(1), file=join(root,'dist',target);
  if(!file.startsWith(join(root,'dist')))throw new Error('Unsafe path');
  const body=await import('node:fs/promises').then(fs=>fs.readFile(file));
  const type=target.endsWith('.js')?'application/javascript':target.endsWith('.css')?'text/css':target.endsWith('.json')?'application/json':'text/html';
  res.setHeader('content-type',type);
  if(target==='index.html')res.end(String(body).replace('</body>','<script src="/__harness.js"></script></body>'));else res.end(body);
 }catch(error){res.statusCode=404;res.end(String(error));}
});
await new Promise((resolve,reject)=>{server.once('error',reject);server.listen(0,'127.0.0.1',resolve);});
try{
  const address=server.address(); if(!address||typeof address==='string')throw new Error('No local server');
  const url=`http://127.0.0.1:${address.port}/`;
  const chrome=process.env.CHROME??'/usr/bin/google-chrome';
  const output=await new Promise((resolve,reject)=>{
    const child=spawn(chrome,['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run',`--user-data-dir=${profile}`,'--virtual-time-budget=20000','--dump-dom',url],{windowsHide:true});
    let stdout='',stderr='';
    const timeout=setTimeout(()=>{child.kill();reject(new Error('Carrier recovery browser timed out'));},45000);
    child.stdout.on('data',data=>{stdout+=data;});child.stderr.on('data',data=>{stderr+=data;});
    child.on('error',error=>{clearTimeout(timeout);reject(error);});
    child.on('close',code=>{clearTimeout(timeout);code===0?resolve(stdout):reject(new Error(`Chrome exited ${code}: ${stderr.slice(-2000)}`));});
  });
  const encoded=/<pre id="carrier-recovery-result">([\s\S]*?)<\/pre>/.exec(output)?.[1];
  assert.ok(encoded,'Browser did not complete the recovery scenarios');
  const result=JSON.parse(encoded.replaceAll('&quot;','"').replaceAll('&lt;','<').replaceAll('&gt;','>').replaceAll('&amp;','&'));
  console.log(JSON.stringify(result,null,2));
  if(process.argv[2]) await writeFile(process.argv[2],JSON.stringify(result,null,2));
  assert.equal(result.status,'PASS',result.error);
  assert.equal(result.checks.length,scenario==='inspection'?9:scenario==='coverage'?7:scenario==='data-ui'?10:scenario==='insight'?13:11);
} finally {
  await new Promise(resolve=>server.close(resolve));
  // This tool-created temporary profile is the only directory removed.
  if(!profile.startsWith(resolve(tmpdir())+sep)||!profile.includes('transport3r-recovery-'))throw new Error('Unsafe temporary-profile path');
  await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});
}
