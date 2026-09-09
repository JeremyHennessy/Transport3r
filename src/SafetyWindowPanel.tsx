import {SafetyVisuals} from './SafetyVisuals';
import { useEffect, useRef, useState } from 'react';
import { readValue, type SchemaRegistry } from './datahub';
import { validateEventWindow } from './eventWindow';
import { loadSafetyWindow, windowMonths, type SafetyWindowResult } from './safetyWindow';

export function SafetyWindowPanel({dot,registry}:{dot:string;registry:SchemaRegistry}) {
  const today=new Date().toISOString().slice(0,10);
  const [start,setStart]=useState(`${today.slice(0,4)}-01-01`),[end,setEnd]=useState(today),[page,setPage]=useState(1);
  const [result,setResult]=useState<SafetyWindowResult|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const generation=useRef(0);
  useEffect(()=>()=>{generation.current++;},[dot]);
  async function apply() {
    const request=++generation.current;setPage(1);setResult(null);setError('');setBusy(true);
    try { const window=validateEventWindow({start,end});const loaded=await loadSafetyWindow(registry,dot,window,true);if(request===generation.current)setResult(loaded); }
    catch(cause){if(request===generation.current)setError(cause instanceof Error?cause.message:String(cause));}
    finally{if(request===generation.current)setBusy(false);}
  }
  return <section className="t3-window-panel" data-testid="safety-window"><h3>Explore an event date window</h3><p>Query daily inspections and crash involvement for inclusive calendar dates. This separate view does not change the recent evidence below or the SMS calculation window.</p>
    <form className="t3-coverage-controls" onSubmit={event=>{event.preventDefault();void apply();}}><label>Start date <input type="date" required value={start} onChange={event=>setStart(event.target.value)}/></label><label>End date <input type="date" required value={end} onChange={event=>setEnd(event.target.value)}/></label><button type="submit">{busy?'Loading — apply again to restart':'Apply date window'}</button></form>
    {error&&<p role="alert">{error}</p>}{busy&&<p role="status">Querying both official daily sources…</p>}
    {result?.dot===dot&&<div><SafetyVisuals key={result.acquiredAt} result={result}/><a className="t3-button secondary" href={`#/carrier/${dot}/report?format=brief&start=${result.window.start}&end=${result.window.end}`}>Export brief for this window</a><p><strong>Applied window: {result.window.start} through {result.window.end}</strong> · retrieved {result.acquiredAt}</p><div className="c360-split">{result.sources.map(source=><article key={source.id}><h4>{source.label}</h4>{source.error?<p role="alert">Unavailable: {source.error}</p>:source.slice&&<><p><strong>{source.slice.total?.toLocaleString()??'Unavailable'} source rows in window</strong> · {source.slice.rows.length} loaded{source.slice.truncated?' · partial detail window':''}</p><p>Source rows updated: {new Date(source.after!.rowsUpdatedAt*1000).toISOString()}. Publication metadata was stable around this request.</p><details><summary>Monthly counts from loaded records</summary><p>{source.slice.truncated?'Counts are lower bounds, including months with zero loaded rows.':'Counts cover returned records in this request.'} The first and last months follow the selected dates.</p><table className="inspection-observations"><thead><tr><th>Month</th><th>Loaded rows</th></tr></thead><tbody>{windowMonths(source.slice).map(month=><tr key={month.month}><td>{month.month}</td><td>{month.loaded}{month.complete?'':'+'}</td></tr>)}</tbody></table></details>{source.id==='fx4q-ay7w'&&<details><summary>Open inspections in this window</summary><p>Page {page} of {Math.max(1,Math.ceil(source.slice.rows.length/30))} · {source.slice.rows.length} inspection records.</p><ul>{source.slice.rows.slice((page-1)*30,page*30).map((row,index)=><li key={index}><a href={`#/carrier/${dot}/inspection/${readValue(row,['inspection_id'])}`}>{readValue(row,['insp_date'])} · report {readValue(row,['report_number'])??'unavailable'}</a></li>)}</ul><button disabled={page<=1} onClick={()=>setPage(page-1)}>Previous inspections</button> <button disabled={page*30>=source.slice.rows.length} onClick={()=>setPage(page+1)}>Next inspections</button></details>}</>}<a href={`https://data.transportation.gov/d/${source.id}`} target="_blank" rel="noreferrer">Official source ↗</a></article>)}</div></div>}
    <p className="c360-disclaimer">Source-date alignment: daily event dates, source publication timestamps, Census report dates and SMS snapshot dates answer different questions. Equal selected dates do not establish a shared SMS release. Missing or invalid source dates cannot establish window membership; sparse months do not prove a missing data feed.</p>
  </section>;
}
