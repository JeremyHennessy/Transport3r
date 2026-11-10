import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';

const built=await build({stdin:{contents:"export * from './src/publicIntelligence';",resolveDir:process.cwd(),loader:'ts'},bundle:true,write:false,format:'esm',platform:'node'});
const app=await import(`data:text/javascript;base64,${Buffer.from(built.outputFiles[0].text).toString('base64')}`);

const carrier={dot_number:'1209',phy_country:'US',carrier_operation:'A',fleetsize:'G',power_units:'20',total_drivers:'15',mcs150_date:'20250115',
 phone:'(555) 123-4567',email_address:'Ops@Example.Net',company_officer_1:'JANE   SAMPLE',dun_bradstreet_no:'123-456-789',
 phy_street:'1   TEST ROAD',phy_city:'TESTVILLE',phy_state:'TX',phy_country:'US',phy_zip:'75001',prior_revoke_dot_number:'5678'};
const seed={...carrier,power_units:'22',total_drivers:'16'};
const slice=(sourceId,rows=[],truncated=false)=>({sourceId,rows,total:truncated?null:rows.length,truncated,scope:'carrier'});
function evidence(overrides={}){return {dotNumber:'1209',mode:'intelligence',loadedAt:'2026-11-10T00:00:00Z',registry:{sources:[]},errors:{},slices:{
 motusCarrier:slice('inys-ebih',[{op_auth_status:'active'}]),
 motusAuthHistory:slice('yu5v-wbh6',[]),motusInsurance:slice('c5y8-a4uz',[{effective_date:'20260101'}]),
 motusInsuranceHistory:slice('3uet-3z4i',[]),motusRevokeSuspend:slice('wb4f-neki',[]),
 newEntrantOos:slice('p2mt-9ige',[]),inspections:slice('fx4q-ay7w',[]),crash:slice('aayw-vxb3',[]),
 ...overrides.slices},errors:{...overrides.errors}};}

test('biennial schedule respects the verified 2026 FMCSA suspension window',()=>{
 const value=app.biennialReview('1209','20240101',new Date('2026-11-10T12:00:00Z'));
 assert.equal(value.state,'TEMPORARY_SUSPENSION');
 assert.match(value.summary,/2026-09-30/);
 assert.match(value.summary,/verified 2026-11-10/);
 assert.doesNotMatch(value.summary,/overdue/i);
});
test('temporary guidance becomes a data gap after its review boundary instead of persisting indefinitely',()=>{
 const value=app.biennialReview('1209','20240101',new Date('2026-12-11T12:00:00Z'));
 assert.equal(value.state,'DATA_GAP');
 assert.match(value.summary,/requires re-verification after 2026-12-10/);
 assert.doesNotMatch(value.summary,/currently/i);
});
test('future-dated MCS-150 evidence becomes a data gap at the retained review time',()=>{
 const value=app.biennialReview('1209','20261201',new Date('2026-09-01T00:00:00Z'));
 assert.equal(value.state,'DATA_GAP');
 assert.match(value.summary,/2026-12-01 is later than the evidence review time 2026-09-01/);
 assert.doesNotMatch(value.summary,/TEMPORARY_SUSPENSION|additional time/i);
});
test('pre-suspension scheduled cycle can still produce a review lead without certifying a violation',()=>{
 const value=app.biennialReview('1205','20230101',new Date('2026-05-31T12:00:00Z'));
 assert.equal(value.state,'REVIEW');
 assert.match(value.action,/Review the FMCSA\/Motus record/);
});
test('a USDOT without a next-to-last digit cannot be assigned a filing parity',()=>{
 assert.equal(app.biennialReview('9','20240101',new Date('2026-11-10T12:00:00Z')).state,'DATA_GAP');
});
test('compliance review fails open on missing or truncated evidence rather than clean status',()=>{
 const missing=evidence({slices:{motusCarrier:undefined},errors:{motusCarrier:'source unavailable'}});
 let value=app.complianceReview(carrier,missing,new Date('2026-11-10T12:00:00Z'));
 assert.equal(value.status,'INCOMPLETE_EVIDENCE');
 assert.ok(value.checks.some(row=>row.id==='AUTHORITY'&&row.state==='DATA_GAP'));
 const partial=evidence({slices:{motusInsuranceHistory:slice('3uet-3z4i',[],true)}});
 value=app.complianceReview(carrier,partial,new Date('2026-11-10T12:00:00Z'));
 assert.ok(value.checks.some(row=>row.id==='FILING_CHANGES'&&row.state==='DATA_GAP'));
 assert.match(value.limitation,/Partial, truncated or undated evidence remains a data gap/);
});
test('unparseable lifecycle dates cannot become a no-change information state',()=>{
 const e=evidence({slices:{
  motusInsuranceHistory:slice('3uet-3z4i',[{cancl_effective_date:'not-a-date'}]),
  motusAuthHistory:slice('yu5v-wbh6',[{status_change_date:''}])
 }});
 const value=app.complianceReview(carrier,e,new Date('2026-11-10T12:00:00Z'));
 assert.equal(value.status,'INCOMPLETE_EVIDENCE');
 assert.ok(value.checks.some(row=>row.id==='FILING_CHANGES'&&row.state==='DATA_GAP'&&/1 rows lack/.test(row.summary)));
 assert.ok(value.checks.some(row=>row.id==='AUTHORITY_CHANGES'&&row.state==='DATA_GAP'&&/1 rows lack/.test(row.summary)));
});

test('default compliance clock stays anchored to an accepted warehouse cut instead of wall-clock time',()=>{
 const e=evidence({slices:{
  motusInsuranceHistory:slice('3uet-3z4i',[{cancl_effective_date:'20260820'}]),
  motusAuthHistory:slice('yu5v-wbh6',[])
 }});
 e.loadedAt='2026-11-10T12:00:00Z';
 e.completenessReceipt={backend:'verified_nationwide_warehouse',status:'VERIFIED',cutId:'cut-1',cutAvailableAt:'2026-09-01T00:00:00Z',warehouseSha256:'a'.repeat(64),identityContract:'FMCSA_CARRIER_IDENTITY_1',sourcesExpected:36,sourcesReturned:36,carrierRows:1,unresolvedRowsExcluded:true,mappingTotals:null,smsReleaseBinding:'UNVERIFIED',historicalFeatureValidity:'NOT_CERTIFIED'};
 const value=app.complianceReview(carrier,e);
 assert.equal(value.asOf,'2026-09-01T00:00:00.000Z');
 assert.ok(value.checks.some(row=>row.id==='FILING_CHANGES'&&row.state==='REVIEW'&&row.summary.startsWith('1 filing-history rows')));
});
test('warehouse compliance binds registration and MCS-150 fields to retained Census instead of newer live route data',()=>{
 const live={...carrier,status_code:'A',mcs150_date:'20260830'};
 const e=evidence();
 e.loadedAt='2026-11-10T12:00:00Z';
 e.census={...carrier,status_code:'I',mcs150_date:'20240101'};
 e.slices.census=slice('az4n-8mr2',[e.census]);
 e.completenessReceipt={backend:'verified_nationwide_warehouse',status:'VERIFIED',cutId:'cut-1',cutAvailableAt:'2026-09-01T00:00:00Z',warehouseSha256:'a'.repeat(64),identityContract:'FMCSA_CARRIER_IDENTITY_1',sourcesExpected:36,sourcesReturned:36,carrierRows:1,unresolvedRowsExcluded:true,mappingTotals:null,smsReleaseBinding:'UNVERIFIED',historicalFeatureValidity:'NOT_CERTIFIED'};
 const value=app.complianceReview(live,e);
 const registration=value.checks.find(row=>row.id==='REGISTRATION');
 const biennial=value.checks.find(row=>row.id==='BIENNIAL');
 assert.equal(registration.state,'REVIEW');
 assert.match(registration.summary,/status: I/);
 assert.match(biennial.summary,/Latest Census report: 2024-01-01/);
 assert.doesNotMatch(biennial.summary,/2026-08-30/);
});

test('missing evidence clock makes time-window checks data gaps instead of using Date.now',()=>{
 const e=evidence();e.loadedAt='not-a-date';
 const value=app.complianceReview(carrier,e);
 assert.equal(value.asOf,null);
 assert.ok(value.checks.some(row=>row.id==='BIENNIAL'&&row.state==='DATA_GAP'));
 assert.ok(value.checks.some(row=>row.id==='FILING_CHANGES'&&row.state==='DATA_GAP'&&/review time is unavailable/i.test(row.summary)));
 assert.ok(value.checks.some(row=>row.id==='AUTHORITY_CHANGES'&&row.state==='DATA_GAP'&&/review time is unavailable/i.test(row.summary)));
});

test('peer benchmark refetches target and peers inside one stable Company Census publication bracket',async t=>{
 const urls=[];
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);urls.push(url);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:100,viewLastModified:200});
  const u=new URL(url),select=u.searchParams.get('$select')??'',where=u.searchParams.get('$where')??'';
  if(where==='dot_number=1209')return Response.json([seed]);
  if(select.includes('avg('))return Response.json([{count:'80',avg_power_units:'25.5',avg_drivers:'18.25'}]);
  if(select.includes('count('))return Response.json([{count:'100'}]);
  throw new Error('unexpected '+url);
 });
 const value=await app.loadPeerBenchmark(carrier);
 assert.equal(value.candidateCount,100);assert.equal(value.eligibleCount,80);assert.equal(value.excludedCount,20);
 assert.equal(value.targetPowerUnits,22);assert.equal(value.targetDrivers,16);
 assert.equal(value.averagePowerUnits,25.5);assert.equal(value.insufficient,false);
 const queries=urls.filter(url=>url.includes('/resource/')).map(url=>new URL(url));
 assert.ok(queries.some(u=>u.searchParams.get('$where')==='dot_number=1209'));
 const cohort=queries.filter(u=>(u.searchParams.get('$select')??'').includes('count(')||(u.searchParams.get('$select')??'').includes('avg(')).map(u=>u.searchParams.get('$where')??'');
 assert.ok(cohort.every(where=>where.includes("phy_country='US'")&&where.includes("carrier_operation='A'")&&where.includes("fleetsize='G'")&&where.includes("status_code='A'")));
 assert.ok(cohort.every(where=>where.includes('dot_number<>1209')));
 assert.match(value.limitation,/single-publication benchmark/);
});
test('peer benchmark rejects source publication drift even after refetching the target',async t=>{
 let stamp=1;
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:stamp++,viewLastModified:200});
  const u=new URL(url),select=u.searchParams.get('$select')??'',where=u.searchParams.get('$where')??'';
  if(where==='dot_number=1209')return Response.json([seed]);
  return Response.json([select.includes('avg(')?{count:'80',avg_power_units:'25',avg_drivers:'18'}:{count:'100'}]);
 });
 await assert.rejects(app.loadPeerBenchmark(carrier),/changed during peer acquisition/);
});

test('related registration screening refetches the seed and retrieves normalized-format candidates',async t=>{
 const urls=[];
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);urls.push(url);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:100,viewLastModified:200});
  const u=new URL(url),where=u.searchParams.get('$where')??'';
  if(where==='dot_number=1209')return Response.json([seed]);
  return Response.json([{dot_number:'5678',legal_name:'RELATED TEST',status_code:'A',mcs150_date:'20260101',add_date:'20200101',
    phone:'5551234567',email_address:'other@example.net',company_officer_1:'OTHER PERSON',dun_bradstreet_no:'987654321',
    phy_street:'1 TEST ROAD',phy_city:'TESTVILLE',phy_state:'TX',phy_country:'US',phy_zip:'75001',prior_revoke_dot_number:''}]);
 });
 const value=await app.loadRelatedCarrierLeads(carrier);
 assert.equal(value.leads.length,1);assert.equal(value.leads[0].dot,'5678');
 assert.ok(value.leads[0].matches.includes('phone'));assert.ok(value.leads[0].matches.includes('physical address'));
 assert.ok(value.leads[0].matches.includes('published prior-revocation reference'));
 assert.match(value.limitation,/do not prove fraud/);
 const query=urls.map(url=>new URL(url)).find(u=>u.pathname.includes('/resource/')&&u.searchParams.get('$where')!=='dot_number=1209');
 const where=query.searchParams.get('$where');
 assert.match(where,/dot_number<>1209/);
 assert.match(where,/phone like '%5%5%5%1%2%3%4%5%6%7%'/);
 assert.match(where,/upper\(company_officer_1\) like '%JANE%SAMPLE%'/);
});
test('related registration screen discloses a source ceiling instead of claiming completeness',async t=>{
 t.mock.method(globalThis,'fetch',async input=>{
  const url=String(input);
  if(url.includes('/api/views/'))return Response.json({id:'az4n-8mr2',rowsUpdatedAt:100,viewLastModified:200});
  const u=new URL(url),where=u.searchParams.get('$where')??'';
  if(where==='dot_number=1209')return Response.json([seed]);
  return Response.json(Array.from({length:201},(_,i)=>({dot_number:String(2000+i),legal_name:'TEST '+i,status_code:'A',phone:'5551234567'})));
 });
 const value=await app.loadRelatedCarrierLeads(carrier);
 assert.equal(value.partial,true);assert.equal(value.leads.length,200);
});
