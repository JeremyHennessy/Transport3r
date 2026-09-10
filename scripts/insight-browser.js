(async()=>{
 const result={status:'RUNNING',checks:[],simulation:true},sleep=ms=>new Promise(r=>setTimeout(r,ms));
 const wait=async fn=>{for(let i=0;i<700;i++){if(fn())return;await sleep(20);}throw Error('Insight browser timeout');};
 const check=(value,label)=>{if(!value)throw Error(label);result.checks.push(label);};
 const panel=()=>document.querySelector('[data-testid="safety-window"]'),map=()=>document.querySelector('[data-testid="safety-map"]'),recentMap=()=>document.querySelector('[data-testid="recent-safety-map"]');
 try{
  location.hash='#/carrier/3938496/summary';await wait(()=>document.querySelector('[data-testid="carrier-insight"]'));
  check(document.querySelector('[data-testid="carrier-insight"]').textContent.includes('USDOT 3938496'),'Summary narrative retains carrier identity');
  check(document.querySelectorAll('[data-testid="carrier-insight"] .t3-insight-summary article').length>0,'At-a-glance narrative renders as scannable evidence cards');
  check(document.querySelector('a[href*="report?format=brief"]')&&document.querySelector('a[href*="report?format=detailed"]'),'Both report actions are discoverable');
  location.hash='#/carrier/3938496/safety';await wait(()=>panel()&&recentMap());
  check(recentMap().textContent.includes('Recent published geography')&&recentMap().textContent.includes('not exact event coordinates'),'Recent safety map is visible before a custom date window and discloses state precision');
  const input=panel().querySelectorAll('input');for(const [i,value] of ['2026-01-01','2026-09-09'].entries()){Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(input[i],value);input[i].dispatchEvent(new Event('input',{bubbles:true}));}panel().querySelector('button').click();await wait(()=>map());
  check(map().textContent.includes('2026-01-01 through 2026-09-09'),'Map uses the applied daily event window');
  check(map().querySelectorAll('.t3-map-marker').length===2,'Inspection and crash observations form separate state clusters');
  map().querySelector('[aria-label^="TX:"]').dispatchEvent(new MouseEvent('click',{bubbles:true}));await wait(()=>map().querySelector('.t3-map-events'));
  check(map().querySelector('a[href="#/carrier/3938496/inspection/1000"]'),'Marker selection links the exact carrier and inspection');
  map().querySelector('input[type="checkbox"]').click();await wait(()=>map().querySelectorAll('.t3-map-marker').length===1);check(!map().querySelector('[aria-label^="TX:"]'),'Inspection toggle removes inspection clusters');
  check(map().textContent.includes('not exact event positions'),'Map discloses state-level precision');
  check(panel().querySelector('a[href*="start=2026-01-01&end=2026-09-09"]'),'Report action preserves selected event dates');
  location.hash='#/carrier/3938496/authority';await wait(()=>document.querySelector('.t3-insight-timeline'));check(document.querySelector('.t3-insight-timeline').textContent.includes('2025-05-01'),'Authority lifecycle uses explicit action dates');
  location.hash='#/carrier/3938496/fleet';await wait(()=>document.querySelector('[data-testid="carrier-insight"]')?.textContent.includes('Observed unit make mix'));check(document.querySelector('[data-testid="carrier-insight"]').textContent.includes('not establish ownership'),'Fleet summary preserves observational limitations');
  location.hash='#/carrier/3938496/evidence';await wait(()=>document.querySelector('.t3-source-matrix'));check(document.querySelectorAll('.t3-source-matrix>a').length===36,'Evidence matrix retains all configured source requests');
  result.status='PASS';
 }catch(error){result.status='FAIL';result.error=error.message;}
 finally{const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);}
})();
