import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {spawnSync} from 'node:child_process';

test('private workspace and document enhancement are valid as the exact served script',()=>{
  const code=readFileSync('local_workspace/app.js','utf8')+'\n'+readFileSync('local_workspace/coverage-documents.js','utf8');
  const result=spawnSync(process.execPath,['--check','--input-type=commonjs'],{input:code,encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);
});
