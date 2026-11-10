import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({stdin:{contents:"export * from './src/WorkspaceApp';",resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);

test('country, province and page persist; source paging uses deterministic order', () => {
  const f=app.parseCarrierFilters('#/carriers?country=ca&state=on&page=3');
  assert.deepEqual(app.parseCarrierFilters(app.carrierHash(f)),f);
  const q=app.buildCarrierQuery(f);
  assert.equal(q.get('$offset'),'200');
  assert.equal(q.get('$where'),"phy_state='ON' AND phy_country='CA'");
  assert.equal(q.get('$order'),'fleetsize DESC NULLS LAST, dot_number DESC');
  assert.match(app.buildCarrierQuery({...f,sort:'name_asc'}).get('$order'), /NULLS LAST/);
  for(const page of ['0','-1','1.5','garbage','Infinity','9007199254740991']) assert.throws(()=>app.buildCarrierQuery(app.parseCarrierFilters(`#/carriers?page=${page}`)),/Page/);
});

test('lookahead enables next only for another real row without showing it on both pages', async () => {
  const oldFetch=globalThis.fetch,oldWindow=globalThis.window;globalThis.window={setTimeout,clearTimeout};
  const requested=[];
  globalThis.fetch=async url=>{
    const q=new URL(url).searchParams;requested.push(q);
    const offset=Number(q.get('$offset')??0);
    return new Response(JSON.stringify(Array.from({length:offset===0?101:1},(_,i)=>({dot_number:String(offset+i+1)}))));
  };
  try {
    const a=await app.loadCarrierPage(app.parseCarrierFilters('#/carriers'));
    const b=await app.loadCarrierPage(app.parseCarrierFilters('#/carriers?page=2'));
    assert.equal(a.rows.length,100);assert.equal(a.hasNext,true);
    assert.equal(b.rows[0].dotNumber,'101');assert.equal(b.hasNext,false);
    assert.equal(requested[0].get('$limit'),'101');
    assert.equal(new Set([...a.rows,...b.rows].map(r=>r.dotNumber)).size,101);
  } finally {globalThis.fetch=oldFetch;globalThis.window=oldWindow;}
});

test('driver range and risk availability survive a shared URL with existing filters', () => {
  const filters = app.parseCarrierFilters('#/carriers?q=ACME&state=tx&operation=a&hazmat=Y&minFleet=Q&minDrivers=10&maxDrivers=1000&risk=unavailable&sort=drivers_desc');
  assert.deepEqual(app.parseCarrierFilters(app.carrierHash(filters)), filters);
  const query = app.buildCarrierQuery(filters);
  assert.equal(query.get('$limit'), '100');
  assert.equal(query.get('$q'), 'ACME');
  assert.equal(query.get('$where'), "phy_state='TX' AND carrier_operation='A' AND hm_ind='Y' AND fleetsize>='Q' AND total_drivers::number>=10 AND total_drivers::number<=1000");
});

test('driver ordering is numeric, before the server limit, with unknowns last and stable USDOT ties', () => {
  for (const [sort, direction] of [['drivers_desc','DESC'],['drivers_asc','ASC']]) {
    assert.equal(app.buildCarrierQuery(app.parseCarrierFilters(`#/carriers?sort=${sort}`)).get('$order'), `total_drivers::number ${direction} NULLS LAST, dot_number DESC`);
  }
});

test('zero is an explicit driver bound, while blank bounds do not filter unknown counts', () => {
  const zero = app.parseCarrierFilters('#/carriers?minDrivers=0&maxDrivers=0');
  assert.equal(app.buildCarrierQuery(zero).get('$where'), 'total_drivers::number>=0 AND total_drivers::number<=0');
  assert.match(app.carrierHash(zero), /minDrivers=0&maxDrivers=0/);
  assert.equal(app.buildCarrierQuery(app.parseCarrierFilters('#/carriers')).get('$where'), null);
});

test('invalid, fractional, unsafe and reversed driver bounds fail instead of broadening the search', () => {
  for (const query of ['minDrivers=-1','maxDrivers=1.5','minDrivers=1e3','minDrivers=9007199254740992','minDrivers=0%20OR%201=1','minDrivers=20&maxDrivers=10']) {
    const filters = app.parseCarrierFilters(`#/carriers?${query}`);
    assert.ok(app.carrierFilterError(filters), query);
    assert.throws(() => app.buildCarrierQuery(filters), /Driver limits|Minimum drivers/);
  }
});

test('unknown sort and risk URL values cannot become source query expressions', () => {
  const filters = app.parseCarrierFilters('#/carriers?sort=total_drivers%20DESC&risk=low');
  assert.equal(filters.sort, 'fleet_desc');
  assert.equal(filters.risk, '');
  assert.equal(app.carrierHash(app.parseCarrierFilters('#/carriers')), '#/carriers');
});

test('unreleased risk scores never trigger fabricated values or a Census risk query', async () => {
  const previous = globalThis.fetch;
  globalThis.fetch = () => { throw new Error('No score artifact is released'); };
  try { assert.deepEqual(await app.loadCarriers(app.parseCarrierFilters('#/carriers?risk=available')), []); }
  finally { globalThis.fetch = previous; }
});

test('driver filtering queries the source and retains report dates, status and missing drivers', async () => {
  const previousFetch = globalThis.fetch, previousWindow = globalThis.window;
  let requested;
  globalThis.window = {setTimeout,clearTimeout};
  globalThis.fetch = async url => {
    requested = new URL(url);
    return new Response(JSON.stringify([{dot_number:'80806',legal_name:'J B HUNT',total_drivers:'24116',mcs150_date:'20250707',status_code:'A'},{dot_number:'2',legal_name:'Unknown drivers'}]));
  };
  try {
    const rows = await app.loadCarriers(app.parseCarrierFilters('#/carriers?minDrivers=10&sort=drivers_desc&risk=unavailable'));
    assert.equal(requested.searchParams.get('$where'), 'total_drivers::number>=10');
    assert.equal(rows[0].drivers, '24116');
    assert.equal(rows[0].mcs150Date, '20250707');
    assert.equal(rows[0].statusCode, 'A');
    assert.equal(rows[1].drivers, undefined);
    assert.equal(requested.searchParams.has('risk'), false);
  } finally {globalThis.fetch=previousFetch;globalThis.window=previousWindow;}
});

test('an already cancelled directory request never reaches the source', async () => {
  const previous=globalThis.fetch;
  globalThis.fetch=()=>{throw new Error('Must not fetch');};
  try {
    const controller=new AbortController();controller.abort();
    await assert.rejects(app.loadCarriers(app.parseCarrierFilters('#/carriers'),controller.signal),{name:'AbortError'});
  } finally {globalThis.fetch=previous;}
});

test('directory cancellation remains effective while the response body is loading', async () => {
  const previousFetch=globalThis.fetch,previousWindow=globalThis.window;
  globalThis.window={setTimeout,clearTimeout};
  let started,aborted=false;
  const bodyStarted=new Promise(resolve=>{started=resolve;});
  globalThis.fetch=async(_url,{signal})=>({ok:true,json:()=>new Promise((_resolve,reject)=>{
    signal.addEventListener('abort',()=>{aborted=true;reject(new DOMException('Cancelled','AbortError'));},{once:true});started();
  })});
  try {
    const controller=new AbortController();
    const request=app.loadCarriers(app.parseCarrierFilters('#/carriers'),controller.signal);
    await bodyStarted;controller.abort();
    await assert.rejects(request,{name:'AbortError'});
    assert.equal(aborted,true);
  } finally {globalThis.fetch=previousFetch;globalThis.window=previousWindow;}
});

test('the request deadline also bounds a slow response body and differs from cancellation', async () => {
  const previousFetch=globalThis.fetch,previousWindow=globalThis.window;
  globalThis.window={setTimeout,clearTimeout};
  globalThis.fetch=async(_url,{signal})=>({ok:true,json:()=>new Promise((_resolve,reject)=>{
    signal.addEventListener('abort',()=>reject(new DOMException('Deadline','AbortError')),{once:true});
  })});
  try {await assert.rejects(app.fetchDirectoryRows('https://example.invalid',undefined,5),{message:'FMCSA request timed out'});}
  finally {globalThis.fetch=previousFetch;globalThis.window=previousWindow;}
});

test('exposure summaries preserve unknown coverage, explicit zero and unsafe sums', () => {
  assert.deepEqual(app.exposureTotal([{powerUnits:'10'},{powerUnits:'0'},{},{powerUnits:'bad'},{powerUnits:'-1'}], 'powerUnits'), {value:10,known:2,missing:3});
  assert.deepEqual(app.exposureTotal([{drivers:''},{}], 'drivers'), {value:null,known:0,missing:2});
  assert.deepEqual(app.exposureTotal([{drivers:'0'}], 'drivers'), {value:0,known:1,missing:0});
  assert.deepEqual(app.exposureTotal([], 'drivers'), {value:0,known:0,missing:0});
  assert.equal(app.exposureTotal([{drivers:'9007199254740991'},{drivers:'1'}], 'drivers').value,null);
});

test('configured family counts include all MOTUS deltas and the separate legacy archive', () => {
  assert.equal(app.sourceFamilyCount('MOTUS','MOTUS Delta','MOTUS Legacy Archive'),20);
  assert.equal(app.sourceFamilyCount('Census','Safety','Inspection'),7);
  assert.equal(app.sourceFamilyCount('SMS Input','SMS Output'),8);
  assert.equal(app.sourceFamilyCount('Enforcement'),1);
});

test('missing snapshot is unavailable, while measured zero healthy is retained', () => {
  assert.equal(app.sourceHealthSummary(null).healthy,null);
  assert.equal(app.sourceHealthSummary({generated_at:null,sources:[]}).failed,null);
  const health=app.sourceHealthSummary({generated_at:'2026-09-09T00:00:00Z',healthy_count:36,sources:[{id:'az4n-8mr2',status:'failed'},{id:'invented',status:'healthy'}]});
  assert.equal(health.healthy,0);
  assert.equal(health.failed,1);
  assert.equal(health.unknown,35);
});

test('registration filtering round trips and applies before the row limit', () => {
  const filters=app.parseCarrierFilters('#/carriers?registration=i&minDrivers=100');
  assert.equal(filters.registration,'I');
  assert.deepEqual(app.parseCarrierFilters(app.carrierHash(filters)),filters);
  assert.match(app.buildCarrierQuery(filters).get('$where'), /status_code='I' AND total_drivers::number>=100/);
  assert.throws(()=>app.buildCarrierQuery(app.parseCarrierFilters('#/carriers?registration=garbage')),/registration/);
});


test('Census retry makes exactly one fresh attempt on a first timeout, preserving the response', async () => {
  const signal = new AbortController().signal;
  const calls = [], retries = [];
  const result = await app.retryTransientCensusTimeout(async () => {
    calls.push('request');
    if (calls.length === 1) throw new Error('FMCSA request timed out');
    return { rows: [{dotNumber: '3706'}], hasNext: false };
  }, signal, 0, () => retries.push('retry'));
  assert.deepEqual(result, { rows: [{dotNumber:'3706'}], hasNext: false });
  assert.equal(calls.length, 2);
  assert.deepEqual(retries, ['retry']);
});


test('Census retry fails closed after second timeout and never loops', async () => {
  let calls=0, retries=0;
  await assert.rejects(app.retryTransientCensusTimeout(async () => {
    calls++; throw new Error('FMCSA request timed out');
  }, new AbortController().signal, 0, () => retries++), /FMCSA request timed out/);
  assert.equal(calls,2);
  assert.equal(retries,1);
});


test('Census retry does not repeat HTTP, invalid payload or caller cancellation', async () => {
  for (const error of [new Error('Company Census returned HTTP 503'), new Error('Company Census returned an unexpected payload'),new DOMException('Request cancelled', 'AbortError')]) {
    let calls=0;
    await assert.rejects(app.retryTransientCensusTimeout(async()=>{calls++;throw error;},new AbortController().signal,0),{message:error.message});
    assert.equal(calls,1);
  }
});


test('Census route cancellation during retry backoff prevents a second request', async () => {
  let calls=0;
  const controller=new AbortController();
  await assert.rejects(app.retryTransientCensusTimeout(async()=>{calls++;throw new Error('FMCSA request timed out');},controller.signal,100,()=>controller.abort()),{name:'AbortError'});
  assert.equal(calls,1);
});


test('Census already-aborted signal cannot issue a retry even if first operation times out', async () => {
  const controller=new AbortController();
  let calls=0;
  await assert.rejects(app.retryTransientCensusTimeout(async()=>{calls++;controller.abort();throw new Error('FMCSA request timed out');},controller.signal,0),/FMCSA request timed out/);
  assert.equal(calls,1);
});


test('source health badge freshness expires after 48 hours despite 36 healthy probes', () => {
  const observed = '2026-11-08T00:00:00Z';
  const at = Date.parse(observed);
  assert.deepEqual(app.sourceSnapshotFreshness(observed,at+24*3600000), {fresh:true,ageDays:1});
  assert.deepEqual(app.sourceSnapshotFreshness(observed,at+48*3600000), {fresh:true,ageDays:2});
  assert.deepEqual(app.sourceSnapshotFreshness(observed,at+48*3600000+1), {fresh:false,ageDays:2});
  assert.deepEqual(app.sourceSnapshotFreshness('2026-10-23T00:00:00Z',Date.parse('2026-11-09T00:00:00Z')), {fresh:false,ageDays:17});
  assert.deepEqual(app.sourceSnapshotFreshness(null,at), {fresh:false,ageDays:null});
  assert.deepEqual(app.sourceSnapshotFreshness(observed,at-6*60000), {fresh:false,ageDays:null});
});
