// Test-only missing fields and failed probes; never shipped or used as live data.
(async () => {
  const result={status:'RUNNING',checks:[],simulation:true,requests:[]};
  const original=window.fetch.bind(window);
  const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
  const waitFor=async (predicate,label)=>{for(let i=0;i<300;i++){if(predicate())return;await sleep(20);}throw new Error(`Timeout: ${label}`);};
  const check=(condition,label)=>{if(!condition)throw new Error(label);result.checks.push(label);};
  let fail=true;
  const census=[window.__carrierFixtures.find(r=>r.dot_number==='80806'),{...window.__carrierFixtures.find(r=>r.dot_number==='54283'),total_drivers:undefined,power_units:'0',status_code:'I'}];
  window.fetch=(url,options)=>{
    if(String(url).includes('source-health.json'))return Promise.resolve(new Response(JSON.stringify({generated_at:'2026-09-09T00:00:00Z',healthy_count:36,sources:[{id:'az4n-8mr2',status:'healthy',checked_at:'2026-09-09T00:00:00Z'},{id:'aayw-vxb3',status:'failed',error:'Simulated upstream HTTP 503',checked_at:'2026-09-09T00:00:00Z'}]})));
    if(!String(url).includes('/resource/az4n-8mr2.json'))return original(url,options);
    const where=new URL(url).searchParams.get('$where')??'';result.requests.push(where);
    return Promise.resolve(new Response(fail?'{}':JSON.stringify(where.includes("status_code='I'")?census.slice(1):census),{status:fail?503:200}));
  };
  const loaded=()=>!document.querySelector('.t3-spinner');
  const stats=()=>[...document.querySelectorAll('.t3-directory-stats>div')];
  const setControl=(element,value)=>{Object.getOwnPropertyDescriptor(element.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype,'value').set.call(element,value);element.dispatchEvent(new Event(element.tagName==='SELECT'?'change':'input',{bubbles:true}));};
  try {
    await waitFor(()=>document.querySelector('.t3-error button')&&loaded(),'source failure');
    check(stats().slice(0,4).every(node=>node.querySelector('strong').textContent==='—'),'Failed carrier requests do not display zero exposure or zero match counts');
    fail=false;document.querySelector('.t3-error button').click();
    await waitFor(()=>document.querySelectorAll('.t3-carrier-row:not(.header)').length===2&&loaded(),'partial exposure');
    check(stats()[3].textContent.includes('24,116')&&stats()[3].textContent.includes('1/2 rows reported'),'Driver sum discloses missing row coverage');
    check(stats()[2].textContent.includes('25,280')&&!stats()[2].textContent.includes('partial'),'Reported zero power units remain known counts');
    check(document.querySelector('.t3-carrier-row:not(.header)').textContent.includes('MCS-150'),'MCS-150 date is visible in the carrier row');
    location.hash='#/carriers?registration=I';
    await waitFor(()=>document.querySelectorAll('.t3-carrier-row:not(.header)').length===1&&loaded(),'registration filter');
    check(result.requests.at(-1).includes("status_code='I'")&&stats()[3].querySelector('strong').textContent==='—','Inactive registration is queried at source; entirely missing drivers stay unavailable');
    location.hash='#/sources';await waitFor(()=>document.querySelector('.t3-source-controls'),'sources');
    check(document.querySelectorAll('.t3-source-row:not(.header)').length===36&&document.querySelector('.t3-health').textContent.includes('1/36'),'All 36 sources are retained and health is derived from per-source results');
    setControl(document.querySelector('.t3-source-controls input'),'az4n-8mr2');
    await waitFor(()=>document.querySelectorAll('.t3-source-row:not(.header)').length===1,'source search');
    check(document.querySelector('.t3-source-row:not(.header) a').href==='https://data.transportation.gov/d/az4n-8mr2','Source search resolves an official dataset link');
    setControl(document.querySelector('.t3-source-controls input'),'');await sleep(40);
    setControl(document.querySelector('.t3-source-controls select'),'failed');
    await waitFor(()=>document.querySelector('.t3-source-error'),'failed filter');
    check(document.querySelectorAll('.t3-source-row:not(.header)').length===1&&document.querySelector('.t3-source-error').textContent.includes('503'),'Failed-source filter shows the saved error');
    setControl(document.querySelector('.t3-source-controls select'),'unavailable');
    await waitFor(()=>document.querySelectorAll('.t3-source-row:not(.header)').length===34,'unavailable filter');
    check(document.querySelector('[role=status]').textContent==='34 of 36 sources','Missing probes remain unavailable, not failed or healthy');
    location.hash='#/overview';await waitFor(()=>document.querySelector('.t3-kpi-grid'),'overview');
    check([...document.querySelectorAll('.t3-kpi-grid strong')].reduce((n,el)=>n+Number(el.textContent),0)===36,'Overview family totals reconcile to the configured registry');
    result.status='PASS';
  }catch(error){result.status='FAIL';result.error=error.message;}
  finally{window.fetch=original;const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();

