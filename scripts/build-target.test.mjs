import test from 'node:test';
import assert from 'node:assert/strict';
import {loadConfigFromFile} from 'vite';
import {transform} from 'esbuild';
const result=await loadConfigFromFile({command:'build',mode:'production'});
test('patched compiler supports the explicitly declared production syntax targets',async()=>{
 const target=result?.config?.build?.target;
 assert.deepEqual(target,['es2020','edge88','firefox78','chrome87','safari15']);
 await assert.doesNotReject(transform('const {value,...rest}=source;export const answer=()=>[value,rest];',{target,format:'esm'}));
});
test('browser minimum is explicit rather than pretending unsupported lowering works',()=>{
 assert.ok(!result.config.build.supported,'Do not bypass compiler compatibility checks');
});
