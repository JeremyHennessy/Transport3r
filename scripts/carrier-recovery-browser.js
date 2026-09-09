// Browser-only response fixtures; executes the actual production React bundle.
(async () => {
  const result = {status:'RUNNING',checks:[],requests:[],fixture_source:'scripts/fixtures/large-carrier-census.json'};
  const originalFetch = window.fetch.bind(window);
  let mode = 'fail';
  const pending = [];
  const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
  const waitFor = async (predicate, label) => {
    for (let i=0;i<300;i++) { if (predicate()) return; await sleep(20); }
    throw new Error(`Timed out: ${label}`);
  };
  const assert = (condition, label) => {if (!condition) throw new Error(label);result.checks.push(label);};
  const rows = () => [...document.querySelectorAll('.t3-carrier-row:not(.header)')];
  const loaded = () => !document.querySelector('.t3-spinner');
  const click = text => {
    const button=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===text);
    if (!button) throw new Error(`Button missing: ${text}`);
    button.click();
  };
  window.fetch = (url, options={}) => {
    if (!String(url).includes('/resource/az4n-8mr2.json')) return originalFetch(url,options);
    const where=new URL(url).searchParams.get('$where')??'';
    const dot=/dot_number=(\d+)/.exec(where)?.[1];
    const record={mode,dot:dot??'all',aborted:false};result.requests.push(record);
    const payload=window.__carrierFixtures.filter(r=>!dot||r.dot_number===dot);
    const response=()=>new Response(JSON.stringify(payload),{status:200,headers:{'Content-Type':'application/json'}});
    if (mode==='fail') return Promise.resolve(new Response('{}',{status:503}));
    if (mode==='slow') return new Promise(resolve=>{
      // Deliberately settle even after cancellation to also test the stale-response guard.
      options.signal?.addEventListener('abort',()=>{record.aborted=true;},{once:true});
      pending.push({record,resolve:()=>resolve(response())});
    });
    return Promise.resolve(response());
  };
  try {
    await waitFor(()=>document.querySelector('.t3-error button'),'initial source error');
    const failed=result.requests.length;
    mode='success';click('Retry');
    await waitFor(()=>rows().length===1&&loaded(),'Retry recovery');
    assert(result.requests.length>failed&&!document.querySelector('.t3-error'),'Retry sends a fresh request and clears the source error');
    assert(rows()[0].textContent.includes('24,116'),'Recovered driver count comes from the Census fixture');

    const same=result.requests.length;
    document.querySelector('form').requestSubmit();
    await waitFor(()=>result.requests.length>same&&loaded(),'unchanged Apply');
    assert(location.hash==='#/carriers?q=80806','Reapplying unchanged filters refreshes without changing the URL');

    location.hash='#/prospect?q=80806';await sleep(60);
    const alias=result.requests.length;document.querySelector('form').requestSubmit();
    await waitFor(()=>result.requests.length>alias&&loaded(),'equivalent shared URL');
    assert(location.hash==='#/carriers?q=80806','Applying equivalent filters from a legacy URL still refreshes');

    click('Reset');
    await waitFor(()=>location.hash==='#/carriers'&&rows().length===window.__carrierFixtures.length&&loaded(),'Reset');
    const reset=result.requests.length;click('Reset');
    await waitFor(()=>result.requests.length>reset&&loaded(),'unchanged Reset');
    assert(rows().length===window.__carrierFixtures.length,'Reset refreshes even when already on the default view');

    mode='slow';location.hash='#/carriers?q=54283';
    await waitFor(()=>pending.length===1,'slow request');
    assert(rows().length===0&&document.querySelector('.t3-table-headline').textContent.includes('Loading matching rows'),'Loading clears prior rows and the prior match count');
    mode='success';location.hash='#/carriers?q=80806';
    await waitFor(()=>rows().length===1&&rows()[0].textContent.includes('J B HUNT')&&loaded(),'newer result');
    assert(pending[0].record.aborted,'Changing filters cancels the obsolete request');
    pending[0].resolve();await sleep(60);
    assert(rows()[0].textContent.includes('J B HUNT')&&!rows()[0].textContent.includes('SWIFT'),'An obsolete response cannot replace the newer carrier');

    const invalid=result.requests.length;location.hash='#/carriers?minDrivers=20&maxDrivers=10';
    await waitFor(()=>document.querySelector('.t3-error')&&loaded(),'invalid range');
    assert(result.requests.length===invalid&&rows().length===0,'Invalid ranges do not fetch or retain previous carriers');
    location.hash='#/carriers?risk=available';
    await waitFor(()=>document.body.textContent.includes('No released risk scores are available.')&&loaded(),'risk availability');
    assert(result.requests.length===invalid,'Unreleased risk availability does not fabricate a source query');

    mode='slow';location.hash='#/carriers?q=54283';
    await waitFor(()=>pending.length===2,'request before leaving directory');
    location.hash='#/overview';
    await waitFor(()=>document.body.textContent.includes('Know the carrier before you price the risk.'),'overview');
    assert(pending[1].record.aborted,'Leaving the directory cancels the pending request');
    pending[1].resolve();await sleep(60);
    result.status='PASS';
  } catch (error) {result.status='FAIL';result.error=error.message;}
  finally {
    window.fetch=originalFetch;
    const pre=document.createElement('pre');pre.id='carrier-recovery-result';pre.textContent=JSON.stringify(result);document.body.append(pre);
  }
})();
