// Synthetic production-bundle check for public intelligence. No private or actuarial acceptance implied.
(async()=>{
 const result={status:'RUNNING',checks:[],simulation:true},original=fetch.bind(window),sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async fn=>{for(let i=0;i<800;i++){if(fn())return;await sleep(20);}throw Error('Intelligence browser timeout');};
 const check=(value,label)=>{if(!value)throw Error(label);result.checks.push(label);};
 const carrier={...window.__carrierFixtures.find(row=>row.dot_number==='80806'),phy_country:'US',phy_state:'AR',phy_city:'LOWELL',phy_street:'1 TEST ROAD',phy_zip:'72745',carrier_operation:'A',fleetsize:'Z',phone:'5551234567',email_address:'ops@synthetic.invalid',company_officer_1:'JANE SAMPLE',dun_bradstreet_no:'123456789'};
 const candidate={dot_number:'90909',legal_name:'SYNTHETIC RELATED REGISTRATION',status_code:'A',add_date:'20200101',mcs150_date:'20260101',phone:'5551234567',phy_country:'US',phy_state:'AR',phy_city:'LOWELL',phy_street:'1 TEST ROAD',phy_zip:'72745'};
 const record=(sid)=>sid==='fx4q-ay7w'?[{dot_number:'80806',inspection_id:'900001',insp_date:'20261015',report_state:'AR',county_code_state:'AR'}]:
   sid==='inys-ebih'?[{dot_number:'80806',op_auth_status:'active',docket_number:'MC1'}]:
   sid==='c5y8-a4uz'?[{dot_number:'80806',effective_date:'20260101',policy_no:'TEST'}]:
   sid==='3uet-3z4i'?[{dot_number:'80806',cancl_effective_date:'20261020'}]:
   sid==='yu5v-wbh6'?[{dot_number:'80806',status_change_date:'20261025',op_auth_status:'active'}]:
   sid==='wb4f-neki'?[{dot_number:'80806',order1_effective_date:'20200101'}]:
   sid==='p2mt-9ige'?[]:[];
 window.fetch=async(input,options)=>{
  const text=String(input);
  if(text.includes('data.transportation.gov/api/views/')){
    const sid=text.split('/').at(-1).replace('.json','');
    return Response.json({id:sid,rowsUpdatedAt:100,viewLastModified:200,tableId:1,columns:[]});
  }
  if(!text.includes('data.transportation.gov/resource/'))return original(input,options);
  const u=new URL(text),sid=u.pathname.split('/').at(-1).replace('.json',''),select=u.searchParams.get('$select')??'',where=u.searchParams.get('$where')??'';
  if(sid==='az4n-8mr2'){
    if(where.includes('dot_number<>80806')){
      if(select.includes('avg('))return Response.json([{count:'80',avg_power_units:'22000',avg_drivers:'19000'}]);
      if(select.includes('count('))return Response.json([{count:'100'}]);
      return Response.json([candidate]);
    }
    if(select.includes('count('))return Response.json([{count:'1'}]);
    return Response.json([{...carrier,...(select.includes('transport_row_id')?{transport_row_id:'census:1'}:{})}]);
  }
  const rows=record(sid);
  if(select.includes('count('))return Response.json([{count:String(rows.length)}]);
  return Response.json(rows.map((row,i)=>select.includes('transport_row_id')?{...row,transport_row_id:`${sid}:${i}`}:row));
 };
 try{
  location.hash='#/carrier/80806/intelligence';
  await wait(()=>document.querySelector('[data-testid="public-intelligence"]'));
  const panel=document.querySelector('[data-testid="public-intelligence"]');
  check(panel.textContent.includes('Compliance, peers, relationships and incidents'),'Intelligence route renders compliance, peer, relationship and incident sections');
  check(panel.textContent.includes('Temporary suspension'),'Current biennial transition state is rendered as a suspension, not an overdue finding');
  const buttons=[...panel.querySelectorAll('button')];
  buttons.find(button=>button.textContent.includes('Compare peers')).click();
  await wait(()=>panel.textContent.includes('80')&&panel.textContent.includes('Eligible peers'));
  check(panel.textContent.includes('100 candidates'),'Peer comparison discloses candidate and eligible population');
  buttons.find(button=>button.textContent.includes('Find registration leads')).click();
  await wait(()=>panel.textContent.includes('SYNTHETIC RELATED REGISTRATION'));
  check(panel.textContent.includes('phone')&&panel.textContent.includes('physical address'),'Relationship screening exposes exact-match categories without a fraud score');
  check(panel.textContent.includes('does not prove fraud')||panel.textContent.includes('do not prove fraud'),'Relationship limitations remain visible');
  check(document.documentElement.scrollWidth<=innerWidth+2,'Intelligence page has no document-level horizontal overflow');
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.message;}
 finally{window.fetch=original;const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();
