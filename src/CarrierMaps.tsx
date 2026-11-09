import {useEffect,useMemo,useState} from 'react';
import type {CarrierEvidence} from './carrierEvidence';
import {GEOGRAPHY_SOURCE,loadDirectoryGeography,safetyGeography,type DirectoryGeography,type SafetyMapOptions} from './openGeography';
import {OpenMap} from './OpenMap';

export function DirectoryMap({query,unavailable,refresh,selectState}:{query:string;unavailable:string;refresh:number;selectState:(state:string)=>void}){
  const [open,setOpen]=useState(false),[result,setResult]=useState<DirectoryGeography|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[retry,setRetry]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();let current=true;setResult(null);setError('');setBusy(false);
    if(open&&!unavailable){setBusy(true);void loadDirectoryGeography(query,controller.signal).then(value=>{if(current)setResult(value);}).catch(cause=>{if(current)setError(cause instanceof Error?cause.message:String(cause));}).finally(()=>{if(current)setBusy(false);});}
    return()=>{current=false;controller.abort();};
  },[open,query,unavailable,refresh,retry]);
  return <section className="t3-panel t3-map-panel" data-testid="directory-map"><div className="t3-map-heading"><div><div className="t3-eyebrow">Filtered carrier geography</div><h2>Where matching carriers are registered</h2></div><button className="t3-button secondary" type="button" aria-expanded={open} onClick={()=>setOpen(value=>!value)}>{open?'Hide carrier map':'Show carrier map'}</button></div>
    <p>State-level carrier counts use the same applied filters as the table, across the matching source population rather than only the current page. Symbols are regional aggregates, not precise addresses or operating routes.</p>
    {open&&<><div className="t3-map-summary" aria-live="polite">{unavailable?<p role="status">{unavailable}</p>:busy?<p role="status">Loading matching carrier regions...</p>:error?<p role="alert">Map unavailable: {error} <button type="button" className="t3-button secondary" onClick={()=>setRetry(n=>n+1)}>Retry carrier map</button></p>:result?<><strong data-testid="map-matched">{result.matched.toLocaleString()} matching source records</strong><span>{result.mapped.toLocaleString()} mapped · {result.unlocated.toLocaleString()} outside supported U.S. regions or missing location</span></>:null}</div>
      {result&&!busy&&!error&&!unavailable&&<><OpenMap regions={result.regions} onSelect={selectState} label="Carrier registration regions; select a region to filter the directory"/>
        <div className="t3-region-list" aria-label="Matching carrier regions">{result.regions.map(region=><button type="button" key={region.code} onClick={()=>selectState(region.code)}><strong>{region.code}</strong><span>{region.count.toLocaleString()} carriers</span><small>Filter this state</small></button>)}</div>
        {!result.regions.length&&<p>No matching records have a supported regional location. Unmapped is not zero carriers.</p>}
        <p className="t3-map-note">Source: FMCSA Company Census az4n-8mr2 · acquired {result.acquiredAt}. Counts reconcile to the filtered query and a stable source publication, not an accepted nationwide warehouse.</p></>}
      <p className="t3-map-note">Coverage: 50 U.S. states, DC and Puerto Rico. Canadian, Mexican, other and missing locations stay in the unlocated count; no substitute U.S. coordinates are assigned. <a href={GEOGRAPHY_SOURCE.url} target="_blank" rel="noreferrer">Census {GEOGRAPHY_SOURCE.vintage} display boundaries</a>.</p>
    </>}
  </section>;
}

const DEFAULT:SafetyMapOptions={inspections:true,crashes:true,includeReporting:true,start:'',end:''};
export function CarrierSafetyMap({evidence}:{evidence:CarrierEvidence}){
  const [options,setOptions]=useState<SafetyMapOptions>(DEFAULT),[selected,setSelected]=useState('');
  const state=useMemo(()=>{try{return {value:safetyGeography(evidence,options),error:''};}catch(cause){return {value:null,error:String(cause instanceof Error?cause.message:cause)};}},[evidence,options]);
  const data=state.value;
  useEffect(()=>{setSelected('');},[evidence.dotNumber]);
  const records=data?.records.filter(row=>!selected||row.state===selected)??[];
  return <section className="c360-card t3-map-panel" data-testid="carrier-safety-map"><div className="t3-map-heading"><div><div className="c360-eyebrow">Observed inspection and crash geography</div><h2>Where safety records were reported</h2></div><span className="t3-map-precision">State-level evidence</span></div>
    <p>These source files do not provide validated coordinates. The map groups recorded event states and, optionally, reporting jurisdictions. It does not show exact crash sites, inspection addresses, traveled lanes or fault.</p>
    <div className="t3-map-controls"><label><input type="checkbox" checked={options.inspections} onChange={e=>setOptions({...options,inspections:e.target.checked})}/> Inspections</label><label><input type="checkbox" checked={options.crashes} onChange={e=>setOptions({...options,crashes:e.target.checked})}/> Crashes</label><label><input type="checkbox" checked={options.includeReporting} onChange={e=>setOptions({...options,includeReporting:e.target.checked})}/> Include reporting jurisdictions</label><label>From<input type="date" value={options.start} onChange={e=>setOptions({...options,start:e.target.value})}/></label><label>Through<input type="date" value={options.end} onChange={e=>setOptions({...options,end:e.target.value})}/></label><button type="button" className="t3-button secondary" onClick={()=>{setOptions(DEFAULT);setSelected('');}}>Reset map filters</button></div>
    {state.error?<p role="alert">{state.error}</p>:data&&<><div className="t3-map-summary"><strong>{data.mapped.toLocaleString()} mapped records</strong><span>{data.unlocated} unlocated · {data.reportingExcluded} reporting-only excluded · {data.invalidDates} unknown/invalid dates</span></div>
      {(data.partial||data.unavailable.length>0)&&<p className="t3-map-warning">{data.partial?'Loaded evidence is a partial window, not all carrier events. ':''}{data.unavailable.length?`Unavailable layers: ${data.unavailable.join(', ')}. Missing data is not zero events.`:''}</p>}
      <OpenMap regions={data.regions} selected={selected} onSelect={setSelected} label="Inspection and crash records by event state or explicitly labelled reporting jurisdiction"/>
      <div className="t3-region-list" aria-label="Inspection and crash regions"><button type="button" aria-pressed={!selected} onClick={()=>setSelected('')}><strong>All regions</strong><span>{data.mapped} records</span></button>{data.regions.map(region=><button type="button" key={region.code} aria-pressed={selected===region.code} onClick={()=>setSelected(region.code)}><strong>{region.code}</strong><span>{region.inspections} inspections · {region.crashes} crashes</span><small>{region.reporting} reporting jurisdiction only</small></button>)}</div>
      <details className="t3-map-records"><summary>Review {selected||'all'} mapped records · {records.length.toLocaleString()} loaded</summary>{records.slice(0,20).map((row,index)=><article key={`${row.kind}-${row.id}-${index}`}><strong>{row.kind==='inspection'?'Inspection':'Crash'} · {row.state} · {row.date||'Date unavailable'}</strong><span>{row.location}</span><small>{row.precision}; no verified coordinates. {row.id?`Source record ${row.id}`:'Record identifier unavailable'}</small><a href={row.kind==='inspection'&&/^\d+$/.test(row.id)?`#/carrier/${evidence.dotNumber}/inspection/${row.id}`:`#/carrier/${evidence.dotNumber}/safety`}>Open supporting evidence</a></article>)}{records.length>20&&<p>First 20 shown. Open Safety or the evidence archive for the remaining loaded records.</p>}</details>
      <p className="t3-map-note">Inspection fx4q-ay7w · crash aayw-vxb3 · {data.outsideWindow} outside the selected dates · {data.rejected} foreign/invalid identities excluded. {options.start||options.end?'Unknown dates are excluded from dated views.':'Unknown dates remain visible when no date filter is selected.'}</p>
      <p className="t3-map-note">{evidence.completenessReceipt?.cutId?`Evidence cut: ${evidence.completenessReceipt.cutId}.`:'No common accepted warehouse cut is established for this loaded view.'} Source retrieval: {evidence.loadedAt}. State locations must not be used for point-level hazard attribution.</p></>}
  </section>;
}
