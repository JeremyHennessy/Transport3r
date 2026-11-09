/** Fail-closed npm audit plus an isolated, uncommitted upgrade candidate.
 * Candidate resolution never changes the reviewed package files or production build.
 */
import {spawnSync} from 'node:child_process';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';

const severities=['info','low','moderate','high','critical'];
export function classifyAudit(text,status){
  let value;
  try{value=JSON.parse(text);}catch{return {status:'UNAVAILABLE',reason:'INVALID_AUDIT_JSON',accepted:false};}
  const counts=value?.metadata?.vulnerabilities;
  if(value?.error||value?.auditReportVersion!==2||!counts||!value.vulnerabilities||
     typeof value.vulnerabilities!=='object'||Array.isArray(value.vulnerabilities)||
     [...severities,'total'].some(key=>!Number.isSafeInteger(counts[key])||counts[key]<0)){
    return {status:'UNAVAILABLE',reason:'INCOMPLETE_AUDIT_RESPONSE',accepted:false};
  }
  if(severities.reduce((sum,key)=>sum+counts[key],0)!==counts.total||
     (status===0)!==(counts.total===0)||![0,1].includes(status)){
    return {status:'UNAVAILABLE',reason:'INCONSISTENT_AUDIT_RESULT',accepted:false};
  }
  return {status:counts.total?'VULNERABILITIES_FOUND':'PASS',accepted:counts.total===0,
    vulnerabilities:Object.fromEntries([...severities,'total'].map(key=>[key,counts[key]])),
    scope:'LOCKFILE_PRODUCTION_AND_DEVELOPMENT_DEPENDENCIES'};
}
export function candidatePackage(original){
  const value=structuredClone(original);
  if(!value.devDependencies?.vite||!value.devDependencies?.esbuild)throw Error('Expected the reviewed Vite/esbuild development toolchain');
  value.devDependencies.vite='6.4.5';
  value.devDependencies.esbuild='0.28.2';
  value.overrides={...value.overrides,esbuild:'$esbuild'};
  return value;
}
async function command(command,args,cwd,output,maximum=120000){
  const result=spawnSync(command,args,{cwd,encoding:'utf8',timeout:maximum,maxBuffer:8*1024*1024,
    env:{...process.env,npm_config_registry:'https://registry.npmjs.org',npm_config_fetch_timeout:'20000',npm_config_fetch_retries:'1'}});
  await writeFile(output+'.stdout',result.stdout??'');
  await writeFile(output+'.stderr',result.stderr??'');
  return result;
}
async function npmAudit(cwd,output){
  const run=await command('npm',['audit','--json','--audit-level=low'],cwd,output);
  const report=classifyAudit(run.stdout??'',run.status);
  await writeFile(output+'.summary.json',JSON.stringify(report,null,2)+'\n');
  return report;
}
export async function run(root,output,{prepareCandidate=false}={}){
  root=resolve(root);output=resolve(output);
  if(output===root||output.startsWith(root+'/'))throw Error('Audit artifacts must remain outside the checkout');
  await mkdir(output,{recursive:true});
  const before=await readFile(resolve(root,'package.json'),'utf8');
  const locked=await readFile(resolve(root,'package-lock.json'),'utf8');
  const current=await npmAudit(root,resolve(output,'current-audit'));
  const planned=candidatePackage(JSON.parse(before));
  let candidate={status:'NOT_REQUESTED',accepted:false,reason:'Auditing the committed lockfile only'};
  if(prepareCandidate&&JSON.stringify(planned)!==JSON.stringify(JSON.parse(before))){
    const folder=resolve(output,'candidate');await mkdir(folder,{recursive:false});
    await writeFile(resolve(folder,'package.json'),JSON.stringify(planned,null,2)+'\n');
    const installed=await command('npm',['install','--ignore-scripts','--no-audit','--no-fund'],folder,resolve(output,'candidate-install'));
    if(installed.status===0){
      candidate=await npmAudit(folder,resolve(output,'candidate-audit'));
      const archive=await command('tar',['-czf',resolve(output,'candidate-node-modules.tar.gz'),'node_modules'],folder,resolve(output,'candidate-archive'));
      if(archive.status!==0)throw Error('Candidate dependency archive could not be retained');
    }else candidate={status:'UNAVAILABLE',accepted:false,reason:'CANDIDATE_RESOLUTION_FAILED'};
  }
  if(before!==await readFile(resolve(root,'package.json'),'utf8')||locked!==await readFile(resolve(root,'package-lock.json'),'utf8')){
    throw Error('Reviewed dependency files changed during isolated resolution');
  }
  const report={current,candidate,checked_at:new Date().toISOString(),
    candidate_is_committed:false,candidate_is_deployed:false,
    limitation:'An isolated candidate does not approve or replace the reviewed lockfile. Recommit verified package files and run all exact-head checks.'};
  await writeFile(resolve(output,'dependency-security-result.json'),JSON.stringify(report,null,2)+'\n');
  console.log(JSON.stringify(report,null,2));return current.accepted?0:1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(resolve(process.argv[1])).href){
  if(!process.argv[2]||process.argv.slice(3).some(arg=>arg!=='--prepare-candidate'))throw Error('Output directory and optional --prepare-candidate required');
  process.exitCode=await run(process.cwd(),process.argv[2],{prepareCandidate:process.argv.includes('--prepare-candidate')});
}
