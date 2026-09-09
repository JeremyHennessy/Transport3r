import {useMemo, useState} from 'react';
import type {CSSProperties} from 'react';
import type {CarrierEvidence} from './carrierEvidence';
import {formatDateValue, readValue, type DataRow} from './datahub';
import boundaries from './stateBoundaries.json';

type EventKind = 'inspection' | 'crash';
type MapEvent = {key:string;kind:EventKind;state:string;date:string;report:string;inspectionId?:string;precision:string};
type GeoSummary = {counts:Map<string,number>;details:Map<string,MapEvent[]>;mappable:number;unlocated:number};
const KNOWN_STATES=new Set(boundaries.states.map(state=>state.code));
const DETAIL_LIMIT=20;

function stateFor(row:DataRow,kind:EventKind):{state?:string;precision:string}{
  const primary=kind==='inspection'?readValue(row,['COUNTY_CODE_STATE','STATE'])?.trim().toUpperCase():readValue(row,['STATE','REPORT_STATE'])?.trim().toUpperCase();
  const fallback=kind==='inspection'?readValue(row,['REPORT_STATE'])?.trim().toUpperCase():undefined;
  if(primary&&KNOWN_STATES.has(primary))return{state:primary,precision:'source location state'};
  if(fallback&&KNOWN_STATES.has(fallback))return{state:fallback,precision:'reporting jurisdiction only'};
  return{precision:'unmapped'};
}
function summarize(rows:DataRow[],kind:EventKind):GeoSummary{
  const counts=new Map<string,number>(),details=new Map<string,MapEvent[]>();let unlocated=0,mappable=0;
  rows.forEach((row,index)=>{const location=stateFor(row,kind);if(!location.state){unlocated++;return;}mappable++;counts.set(location.state,(counts.get(location.state)??0)+1);const saved=details.get(location.state)??[];if(saved.length<DETAIL_LIMIT){const inspectionId=kind==='inspection'?readValue(row,['INSPECTION_ID','INSP_ID','UNIQUE_ID']):undefined;const rawDate=readValue(row,kind==='inspection'?['INSP_DATE','INSPECTION_DATE','REPORT_DATE']:['REPORT_DATE','CRASH_DATE']);saved.push({key:`${kind}:${inspectionId??readValue(row,['CRASH_ID','REPORT_NUMBER'])??index}`,kind,state:location.state,date:formatDateValue(rawDate),report:readValue(row,['REPORT_NUMBER','CRASH_ID'])??'Report unavailable',inspectionId,precision:location.precision});details.set(location.state,saved);}});
  return{counts,details,mappable,unlocated};
}

export function RecentEventMap({evidence}:{evidence:CarrierEvidence}){
  const[showInspections,setShowInspections]=useState(true),[showCrashes,setShowCrashes]=useState(true),[selected,setSelected]=useState<string|null>(null);
  const inspections=useMemo(()=>summarize(evidence.errors.inspections?[]:evidence.slices.inspections?.rows??[],'inspection'),[evidence]);
  const crashes=useMemo(()=>summarize(evidence.errors.crash?[]:evidence.slices.crash?.rows??[],'crash'),[evidence]);
  const states=useMemo(()=>boundaries.states.map(state=>{const inspectionCount=showInspections?(inspections.counts.get(state.code)??0):0,crashCount=showCrashes?(crashes.counts.get(state.code)??0):0;return{...state,inspectionCount,crashCount,count:inspectionCount+crashCount};}),[showInspections,showCrashes,inspections,crashes]);
  const ranked=useMemo(()=>states.filter(state=>state.count).sort((a,b)=>b.count-a.count||a.code.localeCompare(b.code)),[states]);
  const maxState=Math.max(1,...ranked.map(state=>state.count));
  const selectedDetails=selected?[...(showInspections?inspections.details.get(selected)??[]:[]),...(showCrashes?crashes.details.get(selected)??[]:[])].slice(0,DETAIL_LIMIT):[];
  const selectedTotal=selected?(showInspections?(inspections.counts.get(selected)??0):0)+(showCrashes?(crashes.counts.get(selected)??0):0):0;
  const inspectionCount=showInspections?inspections.mappable:0,crashCount=showCrashes?crashes.mappable:0,total=inspectionCount+crashCount;
  return <section className="t3-safety-visuals t3-recent-map" data-testid="recent-safety-map">
    <div className="t3-map-head"><div><div className="t3-eyebrow">Recent published geography</div><h3>Where the loaded safety evidence was reported</h3><p>State-level view of the currently loaded daily inspection and crash records. Marker positions represent states, not exact event coordinates. Inspection location state falls back to reporting jurisdiction only when needed.</p></div><div className="t3-map-kpis"><span className="inspection">{inspectionCount.toLocaleString()} inspections</span><span className="crash">{crashCount.toLocaleString()} crashes</span><span>{ranked.length} states</span></div></div>
    <div className="t3-coverage-controls"><label><span>Layers</span><span><input type="checkbox" checked={showInspections} onChange={event=>setShowInspections(event.target.checked)}/> Inspections</span></label><label><span>&nbsp;</span><span><input type="checkbox" checked={showCrashes} onChange={event=>setShowCrashes(event.target.checked)}/> Crashes</span></label><label><span>Focus state</span><select value={selected??''} onChange={event=>setSelected(event.target.value||null)}><option value="">Top states</option>{ranked.map(state=><option key={state.code} value={state.code}>{state.code} · {state.count}</option>)}</select></label></div>
    {!total?<div className="c360-empty"><strong>No mappable state-level events are available in the loaded evidence.</strong><p>Missing map rows do not imply no inspections or crashes; review source availability and the detailed evidence below.</p></div>:<div className="t3-map-layout"><div className="t3-map-canvas"><svg viewBox="0 0 760 560" aria-label="State-level map of loaded inspection and crash evidence" role="img"><title>Loaded daily inspection and crash evidence grouped by state</title>{states.map(state=>{const intensity=state.count/maxState,fill=!state.count?'#f3f6f9':intensity>.66?'#c6dcf0':intensity>.33?'#d9e8f5':'#e9f2fa',active=selected===state.code;return <g key={state.code}><path d={state.path} fill={fill} stroke={active?'#f97316':'#8799ac'} strokeWidth={active?1.7:.55}/>{state.count>0&&<g role="button" tabIndex={0} aria-label={`${state.code}: ${state.count} loaded events`} onClick={()=>setSelected(state.code)} onKeyDown={event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();setSelected(state.code);}}} className="t3-map-marker" transform={`translate(${state.x},${state.y})`}><title>{state.code}: {state.count} loaded events</title>{state.inspectionCount>0&&<circle cx={state.crashCount>0?-7:0} cy={0} r={7} fill="#256da8" stroke="#fff" strokeWidth="1.5"/>}{state.crashCount>0&&<rect x={state.inspectionCount>0?1:-6} y={-6} width={12} height={12} rx={2} fill="#e36c26" stroke="#fff" strokeWidth="1.5" transform={state.inspectionCount>0?'rotate(45 7 0)':'rotate(45 0 0)'}/>}<text y={22} textAnchor="middle" fontSize={9.5} fontWeight="700" fill="#173553">{state.code} {state.count}</text></g>}</g>;})}</svg></div><aside className="t3-map-side">{selected?<><h4>{selected} · {selectedTotal.toLocaleString()} loaded events</h4><p>Showing up to {DETAIL_LIMIT} records while all mappable rows remain included in the state count.</p><div className="t3-map-events">{selectedDetails.map(event=><div className="t3-map-event" key={event.key}><strong>{event.kind==='inspection'?'Inspection':'Crash involvement'} · {event.date}</strong><br/>Report {event.report} · {event.precision}{event.kind==='inspection'&&event.inspectionId&&<a href={`#/carrier/${evidence.dotNumber}/inspection/${event.inspectionId}`}>Open inspection →</a>}</div>)}</div></>:<><h4>Highest activity states</h4><p>Counts use every loaded mappable row and follow the active layer toggles.</p><div className="t3-map-state-list">{ranked.slice(0,12).map(state=><button key={state.code} onClick={()=>setSelected(state.code)} style={{'--pct':`${Math.max(4,(state.count/maxState)*100)}%`} as CSSProperties}><strong>{state.code}</strong><i/><span>{state.count.toLocaleString()}</span></button>)}</div></>}</aside></div>}
    <div className="t3-map-legend"><span><i className="inspection"/>Inspection</span><span><i className="crash"/>Crash involvement</span><span><i className="empty"/>No loaded mappable rows</span><span>{(inspections.unlocated+crashes.unlocated).toLocaleString()} loaded rows lack a mappable state</span></div><p className="t3-map-footnote">State boundaries: U.S. Census Bureau, 2025, 1:20,000,000. No third-party geocoding or map-tile requests are used. Crash involvement does not establish fault.</p>
  </section>;
}
