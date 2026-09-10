import {createServer} from 'node:http';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {resolve,extname,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';

const chrome=process.env.CHROME_BIN??['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','/usr/bin/chromium','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(existsSync);
if (!chrome) throw new Error('Chrome is required for the carrier recovery release gate');
const dist=resolve('dist');
const fixture=await readFile('scripts/fixtures/large-carrier-census.json','utf8');
const scenario=process.env.BROWSER_SCENARIO??'carrier-recovery';
if (!['carrier-recovery','data-ui','coverage','inspection','date-enrichment','sms-display','insight'].includes(scenario)) throw new Error('Unknown browser scenario');
const harness=(scenario==='insight'?await readFile('scripts/report-fixture-browser.js','utf8'):'')+await readFile(`scripts/${scenario}-browser.js`,'utf8');
const html=(await readFile(resolve(dist,'index.html'),'utf8')).replace('<head>',`<head><script>window.__carrierFixtures=${fixture.replaceAll('<','\\u003c')};</script><script src="/recovery-harness.js"></script>`);
const server=createServer(async(req,res)=>{
  try {
    const url=new URL(req.url,'http://localhost');
    if(url.pathname==='/recovery-harness.js'){res.setHeader('Content-Type','application/javascript');res.end(harness);return;}
    if(url.pathname==='/favicon.ico'){res.writeHead(204);res.end();return;}
    if(url.pathname==='/Transport3r/'||url.pathname==='/Transport3r/index.html'){res.setHeader('Content-Type','text/html');res.end(html);return;}
    const file=resolve(dist,decodeURIComponent(url.pathname.replace(/^\/Transport3r\//,'')));
    if(!file.startsWith(dist+sep))throw new Error('Path outside build');
    res.setHeader('Content-Type',({'.js':'application/javascript','.css':'text/css','.json':'application/json'})[extname(file)]??'application/octet-stream');
    res.end(await readFile(file));
  }catch {res.writeHead(404);res.end('Not found');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const profile=await mkdtemp(resolve(tmpdir(),'transport3r-recovery-'));
try {
  const address=server.address();
  const url=`http://127.0.0.1:${address.port}/Transport3r/#/carriers?q=80806`;
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
