import test from 'node:test';
import assert from 'node:assert/strict';
import {classifyAudit,candidatePackage} from './dependency-security.mjs';
const value=()=>({auditReportVersion:2,vulnerabilities:{},metadata:{vulnerabilities:{info:0,low:0,moderate:0,high:0,critical:0,total:0}}});
test('only a complete successful zero-vulnerability response is accepted',()=>{
 assert.equal(classifyAudit(JSON.stringify(value()),0).accepted,true);
});
test('known issues are not hidden by a passing audit command',()=>{
 const v=value();v.vulnerabilities.example={name:'example',severity:'high'};v.metadata.vulnerabilities.high=1;v.metadata.vulnerabilities.total=1;
 assert.equal(classifyAudit(JSON.stringify(v),1).status,'VULNERABILITIES_FOUND');
 assert.equal(classifyAudit(JSON.stringify(v),0).accepted,false);
});
for(const [label,text,status] of [
 ['network error',JSON.stringify({error:{code:'EAI_AGAIN'}}),1],
 ['invalid JSON','{',1],['missing fields','{}',0],
 ['signal timeout',JSON.stringify(value()),null],
 ['inconsistent exit',JSON.stringify(value()),1],
 ['negative count',JSON.stringify({...value(),metadata:{vulnerabilities:{info:0,low:-1,moderate:0,high:0,critical:0,total:0}}}),0],
 ['incorrect total',JSON.stringify({...value(),metadata:{vulnerabilities:{info:0,low:0,moderate:0,high:1,critical:0,total:0}}}),0],
])test(`audit fails closed: ${label}`,()=>assert.equal(classifyAudit(text,status).accepted,false));
test('candidate uses reviewed pins without mutating the input',()=>{
 const original={name:'transport3r',devDependencies:{vite:'6.0.5',esbuild:'0.24.0',typescript:'5.7.2'}};
 const copy=structuredClone(original),result=candidatePackage(original);
 assert.deepEqual(original,copy);assert.equal(result.devDependencies.vite,'6.4.5');assert.equal(result.devDependencies.esbuild,'0.28.2');
 assert.equal(result.overrides.esbuild,'$esbuild');assert.equal(result.devDependencies.typescript,'5.7.2');
 assert.throws(()=>candidatePackage({devDependencies:{}}));
});

for(const [name,entry] of [['positive-map',{name:'example',severity:'high'}],['null',null],['array',[]],['wrong-name',{name:'other',severity:'high'}],['wrong-severity',{name:'example',severity:'severe'}]]){
 test(`rejects contradictory or malformed vulnerability entry: ${name}`,()=>{
  const v=value();v.vulnerabilities.example=entry;
  assert.equal(classifyAudit(JSON.stringify(v),0).accepted,false);
 });
}
test('rejects wrong severity tally even when total and exit code agree',()=>{
 const v=value();v.vulnerabilities.example={name:'example',severity:'moderate'};
 v.metadata.vulnerabilities.high=1;v.metadata.vulnerabilities.total=1;
 assert.equal(classifyAudit(JSON.stringify(v),1).accepted,false);
});
test('accepts only internally consistent nonempty findings as vulnerable',()=>{
 const v=value();v.vulnerabilities={a:{name:'a',severity:'moderate'},b:{name:'b',severity:'high'}};
 v.metadata.vulnerabilities.moderate=1;v.metadata.vulnerabilities.high=1;v.metadata.vulnerabilities.total=2;
 assert.equal(classifyAudit(JSON.stringify(v),1).status,'VULNERABILITIES_FOUND');
});
