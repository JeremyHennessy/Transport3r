// Deliberately simulated missing/partial data exercises the actual production bundle.
(async()=>{
 const result={status:'RUNNING',checks:[],simulation:true};
 const original=fetch.bind(window), sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
 const wait=async fn=>{for(let i=0;i<500;i++){if(fn())return;await sleep(20);}throw new Error('Coverage browser timeout');};
 const check=(value,label)=>{if(!value)throw new Error(label);result.checks.push(label);};
 let exported;
 const originalClick=HTMLAnchorElement.prototype.click;
 HTMLAnchorElement.prototype.click=function(){if(!this.download)originalClick.call(this);};
 const originalUrl=URL.createObjectURL.bind(URL);
 URL.createObjectURL=blob=>{exported=blob;return originalUrl(blob);};
 window.fetch=(url,options)=>{
  if(!String(url).includes('data.transportation.gov/resource/'))return original(url,options);
  const u=new URL(url),id=u.pathname.split('/').at(-1).replace('.json','');
  if(id==='az4n-8mr2')return Promise.resolve(new Response(JSON.stringify([window.__carrierFixtures.find(r=>r.dot_number==='80806')])));
  if(id==='aayw-vxb3')return Promise.resolve(new Response('{}',{status:503}));
  let rows=[];
  if(id==='fx4q-ay7w')rows=u.searchParams.has('$select')?[{total:'600',count:'600'}]:Array.from({length:501},(_,i)=>({inspection_id:String(i+1),dot_number:'80806',insp_date:i?'20260801':'20260901'})).slice(Number(u.searchParams.get('$offset')??0),Number(u.searchParams.get('$offset')??0)+Number(u.searchParams.get('$limit')??500));
  if(id==='c5y8-a4uz')rows=[{dot_number:'80806'}];
  return Promise.resolve(new Response(JSON.stringify(rows)));
 };
 try{
  location.hash='#/carrier/80806/evidence';
  await wait(()=>document.querySelector('.t3-coverage tbody tr'));
  const panel=document.querySelector('.t3-coverage');
  check(panel.open&&panel.querySelectorAll('tbody tr').length===36,'Evidence includes all 36 requests including unavailable sources');
  check(panel.textContent.includes('500 rows loaded')&&panel.textContent.includes('2026-08-01 → 2026-09-01'),'Capped counts and loaded event range render together');
  const select=panel.querySelector('select');
  const choose=async value=>{Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value').set.call(select,value);select.dispatchEvent(new Event('change',{bubbles:true}));await sleep(50);};
  await choose('unavailable');check(panel.querySelectorAll('tbody tr').length===1&&panel.textContent.includes('HTTP 503'),'Unavailable filter retains acquisition errors');
  await choose('partial');check([...panel.querySelectorAll('tbody tr')].some(r=>r.textContent.includes('inspections')),'Partial filter includes the capped parent inspection window');
  await choose('empty');check(panel.querySelectorAll('tbody tr').length>0&&!panel.querySelector('tbody').textContent.includes('HTTP 503'),'Empty and failed requests stay separate');
  panel.querySelector('button').click();await wait(()=>exported);
  const report=JSON.parse(await exported.text());
  check(report.sources.length===36&&report.dotNumber==='80806'&&report.exposure.drivers==='24116'&&report.riskScore===null,'Export retains all sources and exposure even while filtered');
  location.hash='#/carrier/80806/summary';await wait(()=>document.querySelector('.t3-coverage caption')?.textContent.includes('summary'));
  check(document.querySelector('.t3-coverage')&&!document.querySelector('.t3-coverage').open,'Summary offers the same report without expanding the detail table');
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.message;}
 finally{window.fetch=original;URL.createObjectURL=originalUrl;HTMLAnchorElement.prototype.click=originalClick;const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();
