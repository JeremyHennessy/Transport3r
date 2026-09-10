import {useMemo, useState} from 'react';
import type {CSSProperties} from 'react';
import type {SafetyWindowResult} from './safetyWindow';
import {windowMonths} from './safetyWindow';
import {Bars} from './CarrierInsight';
import {eventGeography} from './eventGeography';
import boundaries from './stateBoundaries.json';

export function SafetyVisuals({result,print=false}:{result:SafetyWindowResult;print?:boolean}) {
  const [inspections,setInspections]=useState(true),[crashes,setCrashes]=useState(true),[selected,setSelected]=useState<string|null>(null);
  const geo=eventGeography(result);
  const events=geo.events.filter(event=>(print||inspections||event.kind!=='inspection')&&(print||crashes||event.kind!=='crash'));
  const states=useMemo(()=>boundaries.states.map(state=>({...state,events:events.filter(event=>event.state===state.code)})),[events]);
  const ranked=useMemo(()=>states.filter(state=>state.events.length).sort((a,b)=>b.events.length-a.events.length||a.code.localeCompare(b.code)),[states]);
  const maxState=Math.max(1,...ranked.map(state=>state.events.length));
  const selectedEvents=events.filter(event=>event.state===selected);
  const inspectionCount=events.filter(event=>event.kind==='inspection').length;
  const crashCount=events.filter(event=>event.kind==='crash').length;
  const partial=result.sources.some(source=>source.error||source.slice?.truncated);

  return <section className="t3-safety-visuals" data-testid="safety-map">
    <div className="t3-map-head">
      <div><div className="t3-eyebrow">Selected event window</div><h3>Daily event geography and activity</h3><p>{result.window.start} through {result.window.end} · USDOT {result.dot}. State-level clusters, not exact event positions. Inspection fallback uses reporting jurisdiction only. Alaska, Hawaii and Puerto Rico are insets.</p></div>
      <div className="t3-map-kpis"><span className="inspection">{inspectionCount.toLocaleString()} inspections</span><span className="crash">{crashCount.toLocaleString()} crashes</span><span>{ranked.length} states</span></div>
    </div>
    {!print&&<div className="t3-coverage-controls"><label><span>Layers</span><span><input type="checkbox" checked={inspections} onChange={event=>setInspections(event.target.checked)}/> Inspections</span></label><label><span>&nbsp;</span><span><input type="checkbox" checked={crashes} onChange={event=>setCrashes(event.target.checked)}/> Crashes</span></label><label><span>Focus state</span><select value={selected??''} onChange={event=>setSelected(event.target.value||null)}><option value="">Top states</option>{ranked.map(state=><option value={state.code} key={state.code}>{state.code} · {state.events.length}</option>)}</select></label></div>}
    {!events.length?<div className="c360-empty"><strong>No mappable event rows are available for this selected window.</strong><p>Review the source status and detailed counts below; an empty map is not a carrier clearance.</p></div>:<div className="t3-map-layout">
      <div className="t3-map-canvas"><svg viewBox="0 0 760 560" aria-label="State clusters of loaded daily events" role="img"><title>State-level daily event clusters; symbol positions are not event coordinates</title>{states.map(state=>{const intensity=state.events.length/maxState;const fill=!state.events.length?'#f3f6f9':intensity>.66?'#c6dcf0':intensity>.33?'#d9e8f5':'#e9f2fa';const active=selected===state.code;const hasInspection=state.events.some(event=>event.kind==='inspection'),hasCrash=state.events.some(event=>event.kind==='crash');return <g key={state.code}><path d={state.path} fill={fill} stroke={active?'#f97316':'#8799ac'} strokeWidth={active?1.7:.55}/>{state.events.length>0&&<g role="button" tabIndex={print?-1:0} aria-label={`${state.code}: ${state.events.length} events`} onClick={()=>!print&&setSelected(state.code)} onKeyDown={event=>{if(!print&&(event.key==='Enter'||event.key===' ')){event.preventDefault();setSelected(state.code);}}} className="t3-map-marker" transform={`translate(${state.x},${state.y})`}><title>{state.code}: {state.events.length} loaded events, grouped by state</title>{hasInspection&&<circle cx={hasCrash?-7:0} cy={0} r={7} fill="#256da8" stroke="#fff" strokeWidth="1.5"/>}{hasCrash&&<rect x={hasInspection?1:-6} y={-6} width={12} height={12} rx={2} fill="#e36c26" stroke="#fff" strokeWidth="1.5" transform={hasInspection?'rotate(45 7 0)':'rotate(45 0 0)'}/>}<text y={22} textAnchor="middle" fontSize={9.5} fontWeight="700" fill="#173553">{state.code} {state.events.length}</text></g>}</g>;})}</svg></div>
      <aside className="t3-map-side">{selected&&!print?<><h4>{selected} · {selectedEvents.length} loaded events</h4><p>Showing up to 30 rows for this state. Location text is retained exactly as reported.</p><div className="t3-map-events">{selectedEvents.slice(0,30).map(event=><div className="t3-map-event" key={event.key}><strong>{event.kind==='inspection'?'Inspection':'Crash involvement'} · {event.date}</strong><br/>{event.precision} · report {event.report}<br/>{event.location} · {event.source}{event.kind==='inspection'&&event.id&&<a href={`#/carrier/${event.dot}/inspection/${event.id}`}>Open inspection →</a>}</div>)}</div></>:<><h4>Highest activity states</h4><p>{print?'Loaded state totals for the selected report window.':'Select a state to inspect its loaded event records.'}</p><div className="t3-map-state-list">{ranked.slice(0,12).map(state=><button disabled={print} className={selected===state.code?'active':''} key={state.code} onClick={()=>setSelected(state.code)} style={{'--pct':`${Math.max(4,(state.events.length/maxState)*100)}%`} as CSSProperties}><strong>{state.code}</strong><i/><span>{state.events.length.toLocaleString()}</span></button>)}</div></>}</aside>
    </div>}
    <div className="t3-map-legend"><span><i className="inspection"/>Inspection</span><span><i className="crash"/>Crash involvement</span><span><i className="empty"/>No loaded mappable rows</span><span>{geo.unlocated} rows lack a mappable state</span><span>{geo.rejected} unrelated rows rejected</span><span>{partial?'Partial/unavailable sources · displayed counts can be lower bounds':'Complete for the selected source requests'}</span></div>
    <p className="t3-map-footnote">Boundaries: U.S. Census Bureau, 2025, 1:20,000,000. No third-party geocoding or map-tile requests. Location text is retained as reported.</p>
    {!print&&<div className="c360-split">{result.sources.map(source=>source.slice&&!source.error?<Bars key={source.id} title={source.label} rows={windowMonths(source.slice).map(month=>({label:month.month,count:month.loaded}))} note={source.slice.truncated?'Loaded lower bounds, including zero-loaded months.':'Returned rows in the selected inclusive window.'}/>:<p key={source.id}>{source.label}: unavailable.</p>)}</div>}
  </section>;
}
