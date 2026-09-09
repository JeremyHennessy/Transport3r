(async()=>{
 const result={status:'RUNNING',checks:[],simulation:true},original=fetch.bind(window),sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async fn=>{for(let i=0;i<700;i++){if(fn())return;await sleep(20);}throw Error('Date/enrichment browser timeout');};
 const check=(value,label)=>{if(!value)throw Error(label);result.checks.push(label);};
 const vin='3C63RRGLXPG628183';let decoded=0,failDecode=false,changing=false,stamp=1,delay=false;const ranges=[];
 const panel=()=>document.querySelector('[data-testid="safety-window"]');
 const setDate=(index,value)=>{const input=panel().querySelectorAll('input')[index];Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));};
 const apply=()=>panel().querySelector('button').click();
 window.fetch=async(input,options)=>{
  const text=String(input);
  if(text.includes('vpic.nhtsa.dot.gov')){decoded++;return failDecode?new Response('{}',{status:503}):Response.json({Results:[{VIN:vin,ErrorCode:'1',ErrorText:'Check digit warning',Make:'RAM',ModelYear:'2023',GVWR:'Class 3'}]});}
  if(text.includes('data.transportation.gov/api/views/')){const id=text.split('/').at(-1);return Response.json({id,rowsUpdatedAt:changing?stamp++:1,viewLastModified:1});}
  if(!text.includes('data.transportation.gov/resource/'))return original(input,options);
  const url=new URL(text),sid=url.pathname.split('/').at(-1).replace('.json',''),where=url.searchParams.get('$where')??'';
  if(sid==='az4n-8mr2')return Response.json([window.__carrierFixtures.find(row=>row.dot_number==='80806')]);
  if(where.includes('between')){
   ranges.push(where);if(delay&&where.includes('20240101'))await sleep(500);
   if(url.searchParams.has('$select'))return Response.json([{count:sid==='fx4q-ay7w'?'501':'0'}]);
   return Response.json(sid==='fx4q-ay7w'?[{dot_number:'80806',inspection_id:'900001',insp_date:where.includes('20240301')?'20240315':'20240229',report_number:'WINDOW-REPORT'}]:[]);
  }
  if(url.searchParams.has('$select'))return Response.json([{count:'1'}]);
  if(sid==='fx4q-ay7w')return Response.json([{dot_number:'80806',inspection_id:'900001',insp_date:'20240229',report_number:'PARENT'}]);
  if(sid==='wt8s-2hbx')return Response.json([{inspection_id:'900001',insp_unit_vehicle_id_number:vin}]);
  return Response.json([]);
 };
 try{
  location.hash='#/carrier/80806/safety';await wait(()=>panel());setDate(0,'2024-01-01');setDate(1,'2024-03-31');apply();
  await wait(()=>panel().textContent.includes('501 source rows'));
  check(ranges.length===4&&ranges.every(range=>range.includes("between '20240101' and '20240331'")),'Date controls send matching inclusive bounds to rows and counts');
  check(panel().querySelector('a[href*="/inspection/900001"]'),'Window records retain direct inspection links');
  check(panel().textContent.includes('2024-01')&&panel().textContent.includes('0+')&&panel().textContent.includes('lower bounds'),'Partial monthly counts do not turn unloaded months into exact zeros');
  changing=true;apply();await wait(()=>panel().textContent.includes('Source changed'));check(!panel().textContent.includes('501 source rows'),'Changed publication suppresses mixed window results');
  changing=false;apply();await wait(()=>panel().textContent.includes('501 source rows'));check(true,'Repeated Apply refetches and recovers source results');
  delay=true;apply();await sleep(30);setDate(0,'2024-03-01');apply();await wait(()=>panel().textContent.includes('Applied window: 2024-03-01'));await sleep(600);check(!panel().textContent.includes('Applied window: 2024-01-01'),'Late window response cannot overwrite a newer selection');
  location.hash=`#/carrier/80806/vin/${vin}?inspection=900001`;await wait(()=>document.querySelector('[data-testid="vin-specifications"]'));
  check(decoded===0,'VIN enrichment waits for an explicit lookup on a verified observation');
  const specs=()=>document.querySelector('[data-testid="vin-specifications"]');specs().querySelector('button').click();await wait(()=>specs().textContent.includes('Decoder warning'));
  check(specs().textContent.includes('Check digit warning')&&specs().textContent.includes('Class 3'),'NHTSA warnings remain alongside provisional specifications');
  failDecode=true;specs().querySelector('button').click();await wait(()=>specs().textContent.includes('503'));check(!specs().textContent.includes('Class 3'),'Failed lookup clears previous specifications');
  failDecode=false;specs().querySelector('button').click();await wait(()=>specs().textContent.includes('Class 3'));check(true,'VIN specification retry recovers');
  location.hash='#/sources';await wait(()=>document.querySelector('[data-testid="enrichment-sources"]'));check(document.querySelector('[data-testid="enrichment-sources"]').textContent.includes('Only NHTSA VIN specifications are integrated'),'Source catalog separates integrated enrichment from research candidates');
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.message;}
 finally{window.fetch=original;const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();
