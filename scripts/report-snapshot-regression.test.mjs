import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const built=await build({stdin:{contents:"export * from './src/reportModel';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {reportModel,reportArchive}=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const evidence=()=>({dotNumber:'1',mode:'evidence',completeAll:true,loadedAt:'2026-11-09T00:00:00Z',census:{dot_number:'1'},registry:{sources:[]},slices:{},errors:{},completenessReceipt:{backend:'verified_nationwide_warehouse',status:'VERIFIED',cutId:'accepted-cut',cutAvailableAt:'2026-11-08T00:00:00Z',warehouseSha256:'a'.repeat(64),sourcesExpected:36,sourcesReturned:36}});
const window=()=>({dot:'1',window:{start:'2026-01-01',end:'2026-11-08'},acquiredAt:'2026-11-09T00:00:00Z',sources:[]});
test('accepted warehouse report rejects an unbound live safety window',()=>{
 assert.throws(()=>reportModel(evidence(),window()),/snapshot|cut|lineage/i);
});
test('archive rejects mismatched carrier identity instead of exporting it',()=>{
 assert.throws(()=>reportArchive(evidence(),{...window(),dot:'2'}),/identity|snapshot|cut/i);
});
test('a separately verified source total is retained even when detail is partial',()=>{
 const e={...evidence(),completenessReceipt:undefined};
 const w={...window(),sources:[{id:'fx4q-ay7w',label:'Daily inspections',slice:{sourceId:'fx4q-ay7w',rows:[{dot_number:'1',insp_date:'20260201'}],total:10,truncated:true}}]};
 assert.equal(reportModel(e,w).metrics.find(([name])=>name==='Window inspections')[1],'10');
});
