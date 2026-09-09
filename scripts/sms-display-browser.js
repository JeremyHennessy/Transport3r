(async()=>{
 const result={status:'RUNNING',checks:[],simulation:true},original=fetch.bind(window),sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async fn=>{for(let i=0;i<700;i++){if(fn())return;await sleep(20);}throw Error('SMS display browser timeout');};
 const check=(value,label)=>{if(!value)throw Error(label);result.checks.push(label);};
 const ids=['4y6x-dmck','h9zy-gjn8','m3ry-qcip','h3zn-uid9'];let fail=false,delay=false;const batches=[];
 const panel=()=>document.querySelector('[data-testid="official-sms"]');
 window.fetch=async(input,options)=>{
  const text=String(input);if(!text.includes('data.transportation.gov/resource/'))return original(input,options);
  const url=new URL(text),sid=url.pathname.split('/').at(-1).replace('.json',''),where=url.searchParams.get('$where')??'';
  const dot=where.includes('3706')?'3706':where.includes('2855794')?'2855794':'80806';
  if(sid==='az4n-8mr2')return Response.json([{...window.__carrierFixtures.find(row=>row.dot_number==='80806'),dot_number:dot}]);
  if(ids.includes(sid)){
   if(where.includes(' in ')){batches.push(where);if(delay&&dot==='80806')await sleep(600);}
   if(fail&&sid===ids[2])return new Response('{}',{status:503});
   const row={dot_number:dot,unsafe_driv_measure:'.75',hos_driv_measure:'0',driv_fit_measure:'.04',contr_subst_measure:'0',veh_maint_measure:'3.41'};
   return Response.json(dot==='2855794'?[]:sid===ids[0]?[row]:sid===ids[2]&&dot==='3706'?[{...row,unsafe_driv_pct:'0%',veh_maint_pct:'4%',veh_maint_basic_alert:'N'}]:[]);
  }
  if(sid==='rsuw-dwxw')return new Response('{}',{status:503});
  if(url.searchParams.has('$select'))return Response.json([{count:'0'}]);
  return Response.json([]);
 };
 try{
  await wait(()=>document.querySelector('[data-testid="directory-sms"]')?.textContent.includes('Vehicle 3.41'));
  check(batches.length===4,'Directory loads four batched output populations automatically');
  check(document.querySelector('[data-testid="directory-sms"]').textContent.includes('HOS 0'),'Directory displays official zero measures');
  fail=true;[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh table SMS').click();await wait(()=>document.querySelector('[data-testid="directory-sms"]')?.textContent.includes('unavailable'));
  check(!document.querySelector('[data-testid="directory-sms"]').textContent.includes('3.41'),'Failed table refresh removes previous values');
  fail=false;[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh table SMS').click();await wait(()=>document.querySelector('[data-testid="directory-sms"]')?.textContent.includes('3.41'));check(true,'Table refresh recovers failed output');
  delay=true;[...document.querySelectorAll('button')].find(b=>b.textContent==='Refresh table SMS').click();await sleep(30);location.hash='#/carriers?q=2855794';await wait(()=>document.querySelector('[data-testid="directory-sms"]')?.textContent.includes('No public'));await sleep(700);
  check(!document.querySelector('[data-testid="directory-sms"]').textContent.includes('3.41'),'Late previous-carrier batch cannot overwrite a new filter');
  location.hash='#/carrier/80806/summary';await wait(()=>panel()?.querySelector('[data-basic="veh_maint"]'));
  check(panel().querySelector('[data-basic="veh_maint"] [data-value="measure"]').textContent==='3.41','Carrier Summary displays official Vehicle Maintenance measure');
  check(panel().querySelector('[data-basic="hos_driv"] [data-value="measure"]').textContent==='0','Carrier Summary preserves zero values');
  location.hash='#/carrier/3706/sms';await wait(()=>panel()?.querySelector('[data-basic="veh_maint"] [data-value="percentile"]')?.textContent==='4');
  check(panel().querySelector('[data-basic="unsafe_driv"] [data-value="percentile"]').textContent==='0','SMS view displays published passenger percentiles including zero');
  fail=true;panel().querySelector('button').click();await wait(()=>panel().textContent.includes('unavailable or conflicting'));
  check(!panel().querySelector('table'),'Failed detail refresh clears displayed official values');
  fail=false;panel().querySelector('button').click();await wait(()=>panel()?.querySelector('table'));check(true,'Detail SMS retry recovers independently of replay inputs');
  location.hash='#/carrier/2855794/summary';await wait(()=>panel()?.textContent.includes('No public SMS output row'));
  check(!panel().querySelector('table'),'No official row is not rendered as five zero measures');
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.message;}
 finally{window.fetch=original;const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();
