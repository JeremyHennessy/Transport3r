import {createServer} from 'node:http';
import {readFile,writeFile,mkdir,mkdtemp,rm} from 'node:fs/promises';
import {existsSync} from 'node:fs';
import {resolve,extname,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const chrome=process.env.CHROME_BIN??['/usr/bin/google-chrome','/usr/bin/google-chrome-stable','C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'].find(existsSync);
if(!chrome)throw Error('Chrome required');
const dist=resolve('dist'),output=resolve(process.argv[2]??'outputs/report-validation');await mkdir(output,{recursive:true});
const fixture=await readFile('scripts/report-fixture-browser.js','utf8');
const html=(await readFile(resolve(dist,'index.html'),'utf8')).replace('<head>','<head><script src="/report-fixture.js"></script>');
const server=createServer(async(req,res)=>{try{const url=new URL(req.url,'http://localhost');if(url.pathname==='/report-fixture.js'){res.setHeader('Content-Type','application/javascript');res.end(fixture);return;}if(url.pathname==='/Transport3r/'){res.setHeader('Content-Type','text/html');res.end(html);return;}const file=resolve(dist,decodeURIComponent(url.pathname.replace(/^\/Transport3r\//,'')));if(!file.startsWith(dist+sep))throw Error('scope');res.setHeader('Content-Type',({'.js':'application/javascript','.css':'text/css','.json':'application/json'})[extname(file)]??'application/octet-stream');res.end(await readFile(file));}catch{res.writeHead(404).end();}});
await new Promise(r=>server.listen(0,'127.0.0.1',r));const profile=await mkdtemp(resolve(tmpdir(),'transport3r-report-'));
const results=[];
try{
 for(const scenario of ['rich','large','small','inactive','no-inspections','partial','multiple-vins','history'])for(const format of ['brief','detailed']){
  const name=`${scenario}-${format}`,pdf=resolve(output,`${name}.pdf`),url=`http://127.0.0.1:${server.address().port}/Transport3r/#/carrier/3938496/report?format=${format}&case=${scenario}&start=2026-01-01&end=2026-09-09`;
  const dom=await new Promise((done,fail)=>{const child=spawn(chrome,['--headless=new','--no-sandbox','--disable-gpu','--disable-dev-shm-usage','--no-first-run',`--user-data-dir=${profile}`,'--virtual-time-budget=15000','--no-pdf-header-footer',`--print-to-pdf=${pdf}`,'--dump-dom',url],{windowsHide:true});let text='',err='';const timer=setTimeout(()=>{child.kill();fail(Error('PDF render timed out'));},45000);child.stdout.on('data',s=>text+=s);child.stderr.on('data',s=>err+=s);child.on('error',fail);child.on('close',code=>{clearTimeout(timer);code===0?done(text):fail(Error(err.slice(-1500)));});});
  assert.ok(dom.includes('data-testid="carrier-report"'),`${name}: report did not render`);assert.ok(!dom.includes('could not render this view'),name);assert.ok(dom.includes(`REPORT FIXTURE ${scenario}`),name);
  if(format==='detailed')assert.ok(dom.includes('data-testid="report-appendix"'));
  const bytes=await readFile(pdf);assert.ok(bytes.length>5000,`${name}: missing PDF`);await writeFile(resolve(output,`${name}.html`),dom);results.push({scenario,format,pdf,bytes:bytes.length});console.log(name);
 }
 await writeFile(resolve(output,'browser-results.json'),JSON.stringify({status:'PASS',results},null,2));
}finally{await new Promise(r=>server.close(r));if(!profile.startsWith(resolve(tmpdir())+sep)||!profile.includes('transport3r-report-'))throw Error('Unsafe temporary profile');await rm(profile,{recursive:true,force:true,maxRetries:5,retryDelay:200});}
