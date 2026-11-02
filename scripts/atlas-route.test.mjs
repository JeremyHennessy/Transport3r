import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const out=await build({stdin:{contents:"export * from './src/atlasRoute.ts';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const {atlasDotFromHash,atlasHash}=await import('data:text/javascript;base64,'+Buffer.from(out.outputFiles[0].text).toString('base64'));
test('atlas URL is a shareable positive USDOT reference',()=>{
  assert.equal(atlasDotFromHash(atlasHash('3938496')),'3938496');
  assert.equal(atlasDotFromHash('#/atlas?dot=3706&layer=inspections'),'3706');
  assert.equal(atlasDotFromHash('#/carriers?dot=3706'),'');
});
test('invalid dots never resolve into a map',()=>{
  for(const dot of ['','0','000123','-1','1%20OR%201','99999999999','123;DROP','-2','2.0']){
    assert.equal(atlasDotFromHash('#/atlas?dot='+dot),'');
    assert.throws(()=>atlasHash(dot));
  }
});
test('Atlas has no implicit zero or empty-carrier selection',()=>{
  assert.equal(atlasDotFromHash('#/atlas'),'');
  assert.equal(atlasDotFromHash('#/atlas?state=TX'),'');
});
