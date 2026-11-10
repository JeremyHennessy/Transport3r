import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

const built=await build({stdin:{contents:"export * from './src/vinRecalls';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);
const vin='3C63RRGLXPG628183';

test('recall research decodes the observed VIN then queries official make/model/year campaigns',async t=>{
 const urls=[];
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);urls.push(url);
  if(url.includes('vpic.nhtsa.dot.gov'))return Response.json({Results:[{VIN:vin,ErrorCode:'0',ErrorText:'0 - VIN decoded clean. Check Digit (9th position) is correct',Make:'RAM',Model:'3500',ModelYear:'2023'}]});
  if(url.includes('api.nhtsa.gov/recalls/'))return Response.json({results:[{NHTSACampaignNumber:'26V001000',Manufacturer:'TEST MFR',Subject:'SYNTHETIC CAMPAIGN',Component:'EQUIPMENT',ReportReceivedDate:'01/01/2026',Summary:'Summary',Consequence:'Consequence',Remedy:'Remedy'}]});
  throw new Error('unexpected '+url);
 });
 const value=await app.loadVinRecallCandidates(vin.toLowerCase());
 assert.equal(urls[0],`https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/${vin}?format=json`);
 const recall=new URL(urls[1]);assert.equal(recall.hostname,'api.nhtsa.gov');assert.equal(recall.pathname,'/recalls/recallsByVehicle');
 assert.equal(recall.searchParams.get('make'),'RAM');assert.equal(recall.searchParams.get('model'),'3500');assert.equal(recall.searchParams.get('modelYear'),'2023');
 assert.equal(value.campaigns[0].campaignNumber,'26V001000');assert.equal(value.campaigns[0].subject,'SYNTHETIC CAMPAIGN');
 assert.match(value.limitation,/does not establish that this VIN is included/);
});
test('campaign research stops when VIN decode lacks model identity',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json({Results:[{VIN:vin,ErrorCode:'0',Make:'RAM',ModelYear:'2023'}]});});
 await assert.rejects(app.loadVinRecallCandidates(vin),/Model required/);assert.equal(calls,1);
});
test('campaign parser rejects an unexpected NHTSA payload',()=>assert.throws(()=>app.decodeRecallCampaigns({results:{}}),/campaign list/));
test('campaign parser preserves official fields without inventing VIN status',()=>{
 const rows=app.decodeRecallCampaigns({results:[{NHTSACampaignNumber:'X',Subject:'Test',Remedy:'Repair'}]});
 assert.deepEqual(rows,[{campaignNumber:'X',manufacturer:null,subject:'Test',component:null,reportReceivedDate:null,summary:null,consequence:null,remedy:'Repair',notes:null}]);
});
