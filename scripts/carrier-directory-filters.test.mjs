import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({stdin:{contents:"export * from './src/WorkspaceApp';",resolveDir:process.cwd(),loader:'tsx'},bundle:true,write:false,format:'esm',platform:'node',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const app = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);

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
