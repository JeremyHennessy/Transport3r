import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

const built=await build({stdin:{contents:"export * from './src/publicIntelligence';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);

const carrier={dot_number:'1209',phy_country:'US',carrier_operation:'A',fleetsize:'G',power_units:'20',total_drivers:'15',mcs150_date:'20250115',
 phone:'5551234567',email_address:'ops@example.net',company_officer_1:'JANE SAMPLE',dun_bradstreet_no:'123456789',
 phy_street:'1 TEST ROAD',phy_city:'TESTVILLE',phy_state:'TX',phy_zip:'75001',prior_revoke_dot_number:'5678'};
const slice=(sourceId,rows=[])=>({sourceId,rows,total:rows.length,truncated:false,scope:'carrier'});
function evidence(overrides={}){return {dotNumber:'1209',mode:'intelligence',loadedAt:'2026-11-10T00:00:00Z',registry:{sources:[]},errors:{},slices:{
 motusCarrier:slice('inys-ebih',[{op_auth_status:'active'}]),
 motusAuthHistory:slice('yu5v-wbh6',[]),motusInsurance:slice('c5y8-a4uz',[{effective_date:'20260101'}]),
 motusInsuranceHistory:slice('3uet-3z4i',[]),motusRevokeSuspend:slice('wb4f-neki',[]),
 newEntrantOos:slice('p2mt-9ige',[]),inspections:slice('fx4q-ay7w',[]),crash:slice('aayw-vxb3',[]),
 ...overrides.slices},errors:{...overrides.errors}};}

test('biennial schedule respects the current 2026 FMCSA suspension',()=>{
 const value=app.biennialReview('1209','20240101',new Date('2026-11-10T12:00:00Z'));
 assert.equal(value.state,'TEMPORARY_SUSPENSION');
 assert.match(value.summary,/2026-09-30/);
 assert.doesNotMatch(value.summary,/overdue/i);
});
test('pre-suspension scheduled cycle can still produce a review lead without certifying a violation',()=>{
 const value=app.biennialReview('1205','20230101',new Date('2026-05-31T12:00:00Z'));
 assert.equal(value.state,'REVIEW');
 assert.match(value.action,/Review the FMCSA\/Motus record/);
});
test('compliance review fails open on missing source evidence rather than clean status',()=>{
 const e=evidence({slices:{motusCarrier:undefined},errors:{motusCarrier:'source unavailable'}});
 const value=app.complianceReview(carrier,e,new Date('2026-11-10T12:00:00Z'));
 assert.equal(value.status,'INCOMPLETE_EVIDENCE');
 assert.ok(value.checks.some(row=>row.id==='AUTHORITY'&&row.state==='DATA_GAP'));
 assert.match(value.limitation,/not legal-compliance certification/);
});

test('peer benchmark uses same country, operation and fleet band with stable publication metadata',async t=>{
 const urls=[];
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);urls.push(url);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:100,viewLastModified:200});
  const u=new URL(url),select=u.searchParams.get('$select')??'';
  if(select.includes('avg('))return Response.json([{count:'80',avg_power_units:'25.5',avg_drivers:'18.25'}]);
  return Response.json([{count:'100'}]);
 });
 const value=await app.loadPeerBenchmark(carrier);
 assert.equal(value.candidateCount,100);assert.equal(value.eligibleCount,80);assert.equal(value.excludedCount,20);
 assert.equal(value.averagePowerUnits,25.5);assert.equal(value.insufficient,false);
 const queries=urls.filter(url=>url.includes('/resource/')).map(url=>new URL(url).searchParams.get('$where')??'');
 assert.ok(queries.every(where=>where.includes("phy_country='US'")&&where.includes("carrier_operation='A'")&&where.includes("fleetsize='G'")&&where.includes("status_code='A'")));
 assert.ok(queries.every(where=>where.includes('dot_number<>1209')));
 assert.match(value.limitation,/not an SMS percentile/);
});
test('peer benchmark rejects source publication drift',async t=>{
 let stamp=1;
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:stamp++,viewLastModified:200});
  const select=new URL(url).searchParams.get('$select')??'';
  return Response.json([select.includes('avg(')?{count:'80',avg_power_units:'25',avg_drivers:'18'}:{count:'100'}]);
 });
 await assert.rejects(app.loadPeerBenchmark(carrier),/changed during peer acquisition/);
});

test('related registration screening returns exact public-detail leads without fraud conclusion',async t=>{
 const urls=[];
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);urls.push(url);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:100,viewLastModified:200});
  return Response.json([{dot_number:'5678',legal_name:'RELATED TEST',status_code:'A',mcs150_date:'20260101',add_date:'20200101',
    phone:'5551234567',email_address:'other@example.net',company_officer_1:'OTHER PERSON',dun_bradstreet_no:'987654321',
    phy_street:'1 TEST ROAD',phy_city:'TESTVILLE',phy_state:'TX',phy_country:'US',phy_zip:'75001',prior_revoke_dot_number:''}]);
 });
 const value=await app.loadRelatedCarrierLeads(carrier);
 assert.equal(value.leads.length,1);assert.equal(value.leads[0].dot,'5678');
 assert.ok(value.leads[0].matches.includes('phone'));assert.ok(value.leads[0].matches.includes('physical address'));
 assert.ok(value.leads[0].matches.includes('published prior-revocation reference'));
 assert.match(value.limitation,/do not prove fraud/);
 const where=new URL(urls.find(url=>url.includes('/resource/'))).searchParams.get('$where');
 assert.match(where,/dot_number<>1209/);
});
test('related registration screen discloses a source ceiling instead of claiming completeness',async t=>{
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:100,viewLastModified:200});
  return Response.json(Array.from({length:201},(_,i)=>({dot_number:String(2000+i),legal_name:'TEST '+i,status_code:'A',phone:'5551234567'})));
 });
 const value=await app.loadRelatedCarrierLeads(carrier);
 assert.equal(value.partial,true);assert.equal(value.leads.length,200);
});
