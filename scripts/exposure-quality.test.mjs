import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const compiled=await build({entryPoints:['src/exposureQuality.ts'],bundle:true,write:false,format:'esm',platform:'node'});
const {exposureQualityFlags:flags}=await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const today=new Date('2026-09-09T12:00:00Z');
const good={powerUnits:'100',drivers:'90',mcs150Date:'20260901',statusCode:'A',mileage:'100000',mileageYear:'2025'};
test('exposure flags distinguish missing, stale and implausible reports without changing them',()=>{
  assert.deepEqual(flags(good,today),[]);
  const suspect={...good,powerUnits:'52000',drivers:'2',mcs150Date:'20200101'};
  assert.equal(flags(suspect,today).length,2);assert.equal(suspect.powerUnits,'52000');
  assert.ok(flags({...good,drivers:undefined},today).some(x=>x.includes('missing')));
  assert.ok(flags({...good,drivers:'0'},today).some(x=>x.includes('zero drivers')));
  assert.ok(flags({...good,mcs150Date:'20260230'},today).some(x=>x.includes('date missing')));
  assert.ok(flags({...good,mcs150Date:'20270909'},today).some(x=>x.includes('future')));
  assert.ok(flags({...good,statusCode:'I'},today).some(x=>x.includes('not confirmed active')));
});
