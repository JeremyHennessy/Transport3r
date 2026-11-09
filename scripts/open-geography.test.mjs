import test from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
const b=await build({stdin:{contents:"export * from './src/openGeography';",loader:'ts',resolveDir:process.cwd()},bundle:true,write:false,platform:'node',format:'esm',define:{'import.meta.env.BASE_URL':'"/Transport3r/"'}});
const geo=await import(`data:text/javascript;base64,${Buffer.from(b.outputFiles[0].text).toString('base64')}`);
const evidence=()=>({dotNumber:'3706',mode:'summary',loadedAt:'2026-11-09T00:00:00Z',registry:{sources:[]},errors:{},slices:{
 inspections:{sourceId:'fx4q-ay7w',rows:[{dot_number:'3706',inspection_id:'1',insp_date:'20260101',county_code_state:'TX',insp_carrier_state:'CA'},{dot_number:'3706',inspection_id:'2',insp_date:'20260201',report_state:'NY',insp_carrier_state:'CA'},{dot_number:'3706',inspection_id:'3',insp_date:'bad',insp_carrier_state:'CA'}],total:3,truncated:false},
 crash:{sourceId:'aayw-vxb3',rows:[{dot_number:'3706',crash_id:'4',report_date:'20260301',state:'TX',crash_carrier_state:'CA'},{dot_number:'999',crash_id:'5',report_date:'20260101',state:'FL'}],total:2,truncated:false},
}});
const opts={inspections:true,crashes:true,includeReporting:true,start:'',end:''};
test('geography preserves applied filters while removing table pagination/sort',()=>{
 const q=new URLSearchParams({'$where':"status_code='A' and total_drivers >= 0",'$limit':'100','$offset':'200','$order':'dot_number desc','$q':'LOGISTICS'});
 const g=geo.geographyQuery(q.toString(),true);
 assert.equal(g.get('$where'),q.get('$where'));assert.equal(g.get('$q'),'LOGISTICS');assert.equal(g.get('$group'),'phy_country,phy_state');assert.equal(g.get('$offset'),'0');assert.equal(g.get('$limit'),'250');assert.equal(g.get('$order'),'phy_country,phy_state');
 const c=geo.geographyQuery(q.toString(),false);assert.equal(c.has('$offset'),false);assert.equal(c.has('$limit'),false);assert.equal(c.get('$select'),'count(*) as count');
});
test('full matching counts exceed current page without fabricating foreign coordinates',()=>{
 const value=geo.reconcileDirectoryGroups([{phy_country:'US',phy_state:'TX',count:'1000'},{phy_country:'CA',phy_state:'ON',count:'200'},{phy_country:'MX',phy_state:'CA',count:'50'},{count:'7'}],1257);
 assert.equal(value.mapped,1000);assert.equal(value.unlocated,257);assert.deepEqual(value.regions,[{code:'TX',count:1000}]);
});
for(const [name,rows,total] of [
 ['changed total',[{phy_country:'US',phy_state:'TX',count:'2'}],1],
 ['duplicate group',[{phy_country:'US',phy_state:'TX',count:'1'},{phy_country:'US',phy_state:'TX',count:'1'}],2],
 ['null count',[{count:null}],0],['blank count',[{count:''}],0],['boolean count',[{count:true}],1],['negative count',[{count:'-1'}],0],['fraction',[{count:'1.2'}],1],['unsafe count',[{count:'9007199254740992'}],0],['array row',[[]],0],
])test(`rejects geography ${name}`,()=>assert.throws(()=>geo.reconcileDirectoryGroups(rows,total)));
test('known zero remains zero; distinct raw groups may normalize to same display state',()=>{
 assert.deepEqual(geo.reconcileDirectoryGroups([],0),{matched:0,mapped:0,unlocated:0,regions:[]});
 assert.equal(geo.reconcileDirectoryGroups([{phy_country:'US',phy_state:'TX',count:'2'},{phy_country:'USA',phy_state:'tx',count:'3'}],5).regions[0].count,5);
});
test('full query checks stable metadata and source count; credentials omitted',async t=>{
 const requests=[];t.mock.method(globalThis,'fetch',async(url,init)=>{requests.push({url:String(url),init});const u=new URL(url);
 if(u.pathname.includes('/api/views/'))return Response.json({id:'az4n-8mr2',tableId:1,rowsUpdatedAt:1,columns:[]});
 return Response.json(u.searchParams.has('$group')?[{phy_country:'US',phy_state:'TX',count:'155'}]:[{count:'155'}]);});
 const value=await geo.loadDirectoryGeography(new URLSearchParams({'$where':"phy_state='TX'",'$limit':'100','$offset':'100'}).toString(),new AbortController().signal);
 assert.equal(value.matched,155);assert.equal(requests.length,4);assert.ok(requests.every(r=>r.init.credentials==='omit'));
});
test('source publication change rejects map instead of certifying mixed groups',async t=>{
 let meta=0;t.mock.method(globalThis,'fetch',async url=>String(url).includes('/api/views/')?Response.json({id:'az4n-8mr2',tableId:1,rowsUpdatedAt:++meta,columns:[]}):Response.json(new URL(url).searchParams.has('$group')?[]:[{count:'0'}]));
 await assert.rejects(geo.loadDirectoryGeography('',new AbortController().signal),/publication changed/);
});
test('already cancelled map sends no requests',async t=>{
 let calls=0;t.mock.method(globalThis,'fetch',async()=>{calls++;return Response.json({});});const c=new AbortController();c.abort();
 await assert.rejects(geo.loadDirectoryGeography('',c.signal),{name:'AbortError'});assert.equal(calls,0);
});
test('safety map never uses carrier address as event location; keeps record identities',()=>{
 const value=geo.safetyGeography(evidence(),opts);
 assert.equal(value.mapped,3);assert.equal(value.unlocated,1);assert.equal(value.rejected,1);assert.equal(value.invalidDates,1);
 assert.equal(value.regions.find(r=>r.code==='TX').count,2);assert.ok(!value.regions.some(r=>r.code==='CA'||r.code==='FL'));
 assert.equal(value.records.find(r=>r.id==='2').precision,'reporting jurisdiction');
});
test('layer/date filters act on loaded records, preserving unknown-date distinction',()=>{
 const value=geo.safetyGeography(evidence(),{...opts,crashes:false,includeReporting:false,start:'2026-01-01',end:'2026-02-28'});
 assert.equal(value.mapped,1);assert.equal(value.reportingExcluded,1);assert.equal(value.invalidDates,1);assert.equal(value.unlocated,0);
});
for(const options of [{start:'2026-02-30'},{start:'2026-03-01',end:'2026-01-01'},{end:'bad'}])test('invalid dates are errors, not broadened map windows '+JSON.stringify(options),()=>assert.throws(()=>geo.safetyGeography(evidence(),{...opts,...options})));
test('failed, missing and partial evidence never appears complete',()=>{
 const e=evidence();e.errors.crash='HTTP 503';e.slices.inspections.truncated=true;
 const value=geo.safetyGeography(e,opts);assert.deepEqual(value.unavailable,['crash']);assert.equal(value.partial,true);assert.equal(value.records.some(r=>r.kind==='crash'),false);
});
test('all display boundaries are finite closed rings; state centres are labelled aggregates',()=>{
 assert.equal(geo.REGIONS.size,52);assert.equal(geo.DISPLAY_BOUNDARIES.features.length,52);
 for(const f of geo.DISPLAY_BOUNDARIES.features)for(const poly of f.geometry.coordinates)for(const ring of poly){assert.ok(ring.length>=4);assert.deepEqual(ring[0],ring.at(-1));for(const [lon,lat]of ring){assert.ok(Number.isFinite(lon)&&lon>=-180&&lon<=180);assert.ok(Number.isFinite(lat)&&lat>=-90&&lat<=90);}}
});
