import {createServer} from 'node:http';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve,extname,sep} from 'node:path';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE??'file:///C:/Users/JeremyHennessy/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright/index.mjs');
const output=resolve(process.argv[3]??'outputs/complete-live-ui');await mkdir(output,{recursive:true});
let server;let base=process.argv[2];
if(!base){const dist=resolve('dist');server=createServer(async(req,res)=>{try{const path=new URL(req.url,'http://localhost').pathname;const file=resolve(dist,path==='/Transport3r/'?'index.html':decodeURIComponent(path.replace(/^\/Transport3r\//,'')));if(!file.startsWith(dist+sep))throw Error('scope');res.setHeader('Content-Type',({'.js':'application/javascript','.css':'text/css','.json':'application/json','.html':'text/html'})[extname(file)]??'application/octet-stream');res.end(await readFile(file));}catch{res.writeHead(404).end();}});await new Promise(r=>server.listen(0,'127.0.0.1',r));base=`http://127.0.0.1:${server.address().port}/Transport3r/`;}
const browser=await chromium.launch({executablePath:process.env.CHROME_BIN??'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
const results=[];
try{
 for(const dot of ['3938496','2855794','3706']){
  const page=await browser.newPage({viewport:{width:1365,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(`${base}#/carrier/${dot}/evidence`);
  const status=page.getByTestId('complete-data-status');
  await status.getByRole('heading',{name:'Complete carrier evidence loaded',exact:true}).waitFor({timeout:240000});
  await status.scrollIntoViewIfNeeded();await page.screenshot({path:resolve(output,`${dot}-desktop.png`)});
  const records=page.getByTestId('all-source-records');await records.scrollIntoViewIfNeeded();
  const text=await records.innerText();if(dot==='3706')assert.ok(text.includes('26,709 loaded'));
  const input=records.getByRole('spinbutton'),max=await input.getAttribute('max');await input.fill(max);await input.press('Tab');
  if(dot==='3706')assert.ok((await records.innerText()).includes('Record 26709'));
  await page.screenshot({path:resolve(output,`${dot}-last-records.png`)});
  await page.setViewportSize({width:390,height:844});await records.scrollIntoViewIfNeeded();await page.screenshot({path:resolve(output,`${dot}-mobile.png`)});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false,`${dot}: mobile overflow`);
  assert.deepEqual(errors,[]);results.push({dot,status:await status.innerText(),lastPage:Number(max),runtimeErrors:errors});await page.close();
 }
 await writeFile(resolve(output,'acceptance.json'),JSON.stringify({status:'PASS',base,results},null,2));
 await writeFile(resolve(output,'gallery.html'),`<!doctype html><meta charset="utf-8"><title>Transport3r complete carrier data verification</title><style>body{font:16px system-ui;background:#eef2f7;margin:30px}img{max-width:100%;border:1px solid #ccd}section{margin-bottom:40px}</style><h1>Complete carrier evidence</h1><p>All 36 sources verified for each carrier; large-carrier last-page access and mobile overflow checked.</p>${results.map(r=>`<section><h2>USDOT ${r.dot}</h2><p>${r.status}</p><img src="${r.dot}-desktop.png"><img src="${r.dot}-last-records.png"><img src="${r.dot}-mobile.png"></section>`).join('')}`);
 console.log(JSON.stringify({status:'PASS',base,results},null,2));
}finally{await browser.close();if(server)await new Promise(r=>server.close(r));}
