// Simulated adversarial identities test the real production bundle.
(async()=>{
 const result={status:'RUNNING',checks:[],simulation:true};
 const original=fetch.bind(window),sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async fn=>{for(let i=0;i<600;i++){if(fn())return;await sleep(20);}throw Error('Inspection browser timeout');};
 const check=(yes,label)=>{if(!yes)throw Error(label);result.checks.push(label);};
 const childRequests=[];let unitFailure=false;
 window.fetch=async(input,options)=>{
  if(String(input).includes('/api/views/'))return Response.json({id:String(input).split('/').at(-1).replace('.json',''),rowsUpdatedAt:1,tableId:1,columns:[]});
  if(!String(input).includes('data.transportation.gov/resource/'))return original(input,options);
  const url=new URL(input),sid=url.pathname.split('/').at(-1).replace('.json',''),where=url.searchParams.get('$where')??'';
  if(sid==='az4n-8mr2')return Response.json([window.__carrierFixtures.find(r=>r.dot_number==='80806')]);
  const id=where.match(/(?:in\s*\(\s*'?|=')(\d+)/)?.[1]??'900001';
  if(sid==='fx4q-ay7w'){
   if(id==='900004')await sleep(500);
   return Response.json(id==='900003'?[]:[{inspection_id:id,dot_number:id==='900002'?'2':'80806',insp_date:'20230901',report_number:`REPORT-${id}`,report_state:'TX',insp_level_id:'1'}]);
  }
  childRequests.push({sid,id});
  if(sid==='wt8s-2hbx'&&unitFailure)return new Response('{}',{status:503});
  if(url.searchParams.get('$select')?.includes('count'))return Response.json([{count:sid==='wt8s-2hbx'?'1':'0'}]);
  if(sid==='wt8s-2hbx')return Response.json([{transport_row_id:'unit1',inspection_id:id,insp_unit_vehicle_id_number:'3C63RRGLXNG286232',insp_unit_make:'RAM'}]);
  return Response.json([]);
 };
 try{
  location.hash='#/carrier/80806/inspection/900001';
  await wait(()=>document.querySelector('[data-testid="inspection-detail"]')?.textContent.includes('REPORT-900001'));
  check(document.body.textContent.includes('Retrieved directly by inspection ID'),'Deep inspection route retrieves its specific report');
  check(childRequests.length>=4&&childRequests.every(r=>r.id==='900001'),'All child requests use the verified inspection only');
  const vin=document.querySelector('[data-testid="inspection-detail"] a[href*="/vin/"]');vin.click();
  await wait(()=>document.querySelector('[data-testid="vin-detail"]'));
  check(document.querySelector('[data-testid="vin-detail"]').textContent.includes('1 verified unit observation'),'VIN link preserves a verified observation outside the recent window');
  document.querySelector('[data-testid="vin-detail"] a[href*="/inspection/"]').click();
  await wait(()=>document.querySelector('[data-testid="inspection-detail"]'));
  check(location.hash.endsWith('/inspection/900001'),'VIN drilldown links back to its parent inspection');
  const before=childRequests.length;location.hash='#/carrier/80806/inspection/900002';
  await wait(()=>document.querySelector('[data-testid="inspection-detail"]')?.textContent.includes('does not belong'));
  check(childRequests.length===before&&!document.body.textContent.includes('REPORT-900001'),'Wrong-carrier route hides prior evidence and blocks child retrieval');
  location.hash='#/carrier/80806/inspection/900003';
  await wait(()=>document.querySelector('[data-testid="inspection-detail"]')?.textContent.includes('was not returned'));
  check(childRequests.length===before,'Missing parent does not invent successful empty child requests');
  location.hash='#/carrier/80806/inspection/900004';await sleep(40);location.hash='#/carrier/80806/inspection/900005';
  await wait(()=>document.body.textContent.includes('REPORT-900005'));await sleep(600);
  check(!document.body.textContent.includes('REPORT-900004'),'Late inspection response cannot overwrite a newer route');
  unitFailure=true;document.querySelector('[data-testid="inspection-detail"] button').click();
  await wait(()=>document.querySelector('[data-testid="inspection-detail"]')?.textContent.includes('503'));
  check(document.querySelector('[data-testid="inspection-detail"] .c360-metric strong').textContent==='—','Failed unit request shows unavailable instead of zero');
  unitFailure=false;document.querySelector('[data-testid="inspection-detail"] button').click();
  await wait(()=>document.querySelector('[data-testid="inspection-detail"] a[href*="/vin/"]'));
  check(!document.querySelector('[data-testid="inspection-detail"]').textContent.includes('503'),'Refresh recovers a failed child request');
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.message;}
 finally{window.fetch=original;const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();
