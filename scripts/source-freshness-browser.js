// Synthetic source-health snapshot regression against the real production React bundle.
// Deliberately changes the clock without navigation to prove a long-lived green badge expires.
(async () => {
  const result = {status:'RUNNING',checks:[],simulation:true};
  const fetchOriginal = window.fetch.bind(window);
  const nowOriginal = Date.now;
  const start = nowOriginal();
  let now = start;
  Date.now = () => now;
  const sleep = ms => new Promise(resolve => setTimeout(resolve,ms));
  const waitFor = async (predicate,label) => {
    for (let i=0;i<300;i++){ if(predicate())return;await sleep(20); }
    throw new Error('Timed out: '+label);
  };
  const check = (condition,label) => {if(!condition)throw new Error(label);result.checks.push(label);};
  window.fetch = async (url, options) => {
    const key = String(url);
    if (key.includes('source-health.json')) {
      const original = await fetchOriginal(url,options);
      const fixture = await original.json();
      fixture.generated_at = new Date(start - (47*60+59)*60_000).toISOString();
      return new Response(JSON.stringify(fixture),{status:200,headers:{'Content-Type':'application/json'}});
    }
    if (key.includes('/resource/az4n-8mr2.json')) {
      return new Response(JSON.stringify(window.__carrierFixtures.filter(row => row.dot_number==='80806')),{status:200});
    }
    return fetchOriginal(url,options);
  };
  try {
    await waitFor(() => document.querySelector('.t3-health.good')?.textContent.includes('36/36'),'fresh all-green source snapshot');
    check(document.querySelector('.t3-health.good')!==null,'A fresh complete source snapshot is shown as a saved healthy probe result');
    check(document.querySelector('.t3-status-head')?.textContent.includes('36 / 36'),'Fresh Overview may show the saved 36/36 probe snapshot');
    now = start + 2*60*60_000;
    window.dispatchEvent(new Event('focus'));
    await waitFor(() => document.querySelector('.t3-health.warn')?.textContent.includes('Snapshot stale'),'stale badge without navigation');
    check(document.querySelector('.t3-health.warn')!==null,'Advancing clock past 48h and focusing the same tab marks old success stale');
    await waitFor(() => document.querySelector('.t3-status-head')?.textContent.includes('Stale snapshot'),'stale Overview status');
    check(document.querySelector('.t3-status-head')?.textContent.includes('Stale snapshot'),'Overview stops presenting stale saved probes as current health');
    location.hash='#/alerts';
    await waitFor(() => document.querySelector('.t3-alert-table'),'Alerts page');
    check(document.querySelectorAll('.t3-alert-table .t3-source-dot.healthy').length===0 && document.querySelector('.t3-alert-table')?.textContent.includes('stale snapshot'),'Alerts replaces per-source healthy labels with stale snapshot state');
    location.hash='#/sources';
    await waitFor(() => document.querySelectorAll('.t3-source-row .t3-source-dot.stale').length===36,'stale Data Sources rows');
    check(document.querySelectorAll('.t3-source-row .t3-source-dot.healthy').length===0,'Data Sources shows all saved probe rows as stale rather than healthy');
    now = start;
    window.dispatchEvent(new Event('focus'));
    await waitFor(() => document.querySelectorAll('.t3-source-row .t3-source-dot.healthy').length===36,'fresh Data Sources rows');
    check(document.querySelectorAll('.t3-source-row .t3-source-dot.healthy').length===36,'Returning the synthetic clock to the observation window restores the saved per-source health state');
    location.hash='#/overview';
    await waitFor(() => document.querySelector('.t3-health.good')?.textContent.includes('Snapshot: 36/36'),'fresh badge rerender');
    check(document.querySelector('.t3-health.good')!==null,'Returning the synthetic clock to the observation window updates the header and Overview');
    result.status='PASS';
  } catch (error) {result.status='FAIL';result.error=String(error);}
  finally {
    Date.now=nowOriginal;
    window.fetch=fetchOriginal;
    const pre=document.createElement('pre');
    pre.id='carrier-recovery-result';
    pre.textContent=JSON.stringify(result);
    document.body.append(pre);
  }
})();
