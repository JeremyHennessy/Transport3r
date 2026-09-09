(()=>{
 const original=fetch.bind(window),scenario=new URLSearchParams(location.hash.split('?')[1]).get('case')??'rich';
 window.__reportErrors=[];window.addEventListener('error',event=>{window.__reportErrors.push(event.message);document.documentElement.dataset.reportError=event.message;});
 window.addEventListener('unhandledrejection',event=>{document.documentElement.dataset.reportError=String(event.reason);});
 window.fetch=async(input,options)=>{
  const text=String(input);if(text.includes('data.transportation.gov/api/views/'))return Response.json({id:text.split('/').at(-1),rowsUpdatedAt:1,viewLastModified:1});
  if(!text.includes('data.transportation.gov/resource/'))return original(input,options);
  const url=new URL(text),id=url.pathname.split('/').at(-1).replace('.json','');
  const dot='3938496',noRows=scenario==='no-inspections'||scenario==='inactive';
  if(scenario==='partial'&&['876r-jsdb','c5y8-a4uz'].includes(id))return new Response('{}',{status:503});
  if(id==='az4n-8mr2')return Response.json([{dot_number:dot,legal_name:`REPORT FIXTURE ${scenario}`,status_code:scenario==='inactive'?'I':'A',carrier_operation:'A',power_units:scenario==='large'?'90000':scenario==='small'?'1':'20',total_drivers:scenario==='partial'?null:'25',mcs150_date:scenario==='inactive'?'20100101':'20260501',mcs150_mileage:'1200000',mcs150_mileage_year:'2025',phy_street:'100 TEST ROAD',phy_city:'TEST CITY',phy_state:'TX',phy_zip:'00000'}]);
  let rows=[];
  if(id==='fx4q-ay7w'&&!noRows)rows=Array.from({length:scenario==='large'?70:3},(_,i)=>({dot_number:dot,inspection_id:String(1000+i),insp_date:'20260315',report_state:'TX',county_code_state:'TX',report_number:`R${i}`,oos_total:i===0?'1':'0'}));
  if(id==='aayw-vxb3'&&!noRows)rows=[{dot_number:dot,crash_id:'800',report_date:'20260201',state:'VA',fatalities:'0'}];
  if(id==='wt8s-2hbx'&&!noRows)rows=Array.from({length:scenario==='multiple-vins'?12:2},(_,i)=>({inspection_id:'1000',insp_unit_vehicle_id_number:`TESTVIN${String(i).padStart(10,'0')}`,insp_unit_make:i%2?'VOLVO':'MACK',insp_unit_type_id:'TT'}));
  if(id==='876r-jsdb'&&!noRows)rows=[{inspection_id:'1000',viol_desc:'Brakes - test evidence',out_of_service_indicator:'Y'}];
  if(id==='inys-ebih')rows=[{usdot_number:dot,op_auth_status:'ACTIVE',op_auth_type:'MOTOR CARRIER',docket_number:'MC123'}];
  if(id==='yu5v-wbh6'&&scenario!=='small')rows=[{usdot_number:dot,status_change_date:'20250501',op_auth_status:'ACTIVE',docket_number:'MC123'}];
  if(id==='c5y8-a4uz')rows=[{usdot_number:dot,insurance_company_name:'TEST INSURER',effective_date:'20260101',max_cov_amount:'750000'}];
  if(id==='3uet-3z4i'&&scenario!=='small')rows=Array.from({length:scenario==='history'?40:1},(_,i)=>({usdot_number:dot,insurance_company_name:`PREVIOUS INSURER ${i}`,effective_date:'20250101',cancl_effective_date:'20260101',filing_status_reason:'replaced'}));
  if(id==='4y6x-dmck')rows=[{dot_number:dot,hos_driv_measure:'0',veh_maint_measure:'1.2'}];
  if(url.searchParams.has('$select')&&url.searchParams.get('$select').includes('count'))return Response.json([{count:String(scenario==='partial'&&id==='fx4q-ay7w'?501:rows.length)}]);
  return Response.json(rows);
 };
})();
