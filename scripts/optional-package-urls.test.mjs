import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const lock=JSON.parse(await readFile(new URL('../package-lock.json',import.meta.url),'utf8'));
for(const [path,item] of Object.entries(lock.packages)){
 if(!path.startsWith('node_modules/@rollup/rollup-'))continue;
 test(`optional platform URL matches resolved package: ${path}`,()=>{
  const name=path.slice('node_modules/'.length),base=name.split('/').at(-1);
  assert.equal(item.resolved,`https://registry.npmjs.org/${name}/-/${base}-${item.version}.tgz`);
  assert.match(item.integrity,/^sha512-[A-Za-z0-9+/]+={0,2}$/);
 });
}
