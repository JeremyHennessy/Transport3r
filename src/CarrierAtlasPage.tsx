import {FormEvent,useEffect,useState,useReducer,useRef} from 'react';
import {atlasLoadReducer,initialAtlasLoadState} from './atlasLoadState';
import {loadCarrierEvidence,clearCarrierEvidenceCache} from './carrierEvidence';
import {RecentEventMap} from './RecentEventMap';
import {atlasDotFromHash,atlasHash} from './atlasRoute';

const SOURCES=[
 {name:'FEMA National Risk Index v1.20',category:'County / census tract relative hazard baseline',url:'https://www.fema.gov/about/reports-and-data/openfema/nri/v120/NRI_Table_Counties.zip',limit:'County-level source ingestion and read-only indexing have been implemented; production installation and this Atlas layer remain unverified. County community risk is not carrier route exposure.'},
 {name:'FEMA National Flood Hazard Layer',category:'Effective floodplain zones and polygons',url:'https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer',limit:'Not ingested. Hazard-zone intersection requires verified geocodes and effective zone vintages.'},
 {name:'NOAA NCEI Storm Events',category:'Reported historical weather impacts',url:'https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/',limit:'Not ingested. Event locations, reporting bias and date validity require normalization.'},
 {name:'FHWA National Bridge Inventory',category:'Public highway bridge inventory',url:'https://www.fhwa.dot.gov/bridge/nbi/nbi_data.cfm',limit:'Not ingested. The bridge inventory is not a truck-route clearance service.'},
 {name:'PHMSA hazmat incident reports',category:'Reported transport hazardous-material incidents',url:'https://www.phmsa.dot.gov/hazmat-program-management-data-and-statistics/data-operations/incident-statistics',limit:'Not ingested. A reported location or similar carrier name does not establish USDOT identity.'}
] as const;

export default function CarrierAtlasPage(){
 const [input,setInput]=useState(()=>atlasDotFromHash(window.location.hash));
 const [dot,setDot]=useState(()=>atlasDotFromHash(window.location.hash));
 const [load,dispatch]=useReducer(atlasLoadReducer,initialAtlasLoadState);
 const generation=useRef(0);
 const {evidence,error}=load,loading=load.status==='loading';
 const [refreshVersion,setRefreshVersion]=useState(0);
 useEffect(()=>{
  const change=()=>{const next=atlasDotFromHash(window.location.hash);setDot(next);setInput(next);};
  window.addEventListener('hashchange',change);return()=>window.removeEventListener('hashchange',change);
 },[]);
 useEffect(()=>{
  const current=++generation.current;
  if(!dot){dispatch({type:'clear',generation:current});return;}
  let active=true;dispatch({type:'start',generation:current});
  loadCarrierEvidence(dot,'atlas')
   .then(result=>{if(active)dispatch({type:'complete',generation:current,evidence:result});})
   .catch(cause=>{if(active)dispatch({type:'fail',generation:current,error:cause instanceof Error?cause.message:String(cause)});});
  return()=>{active=false;};
 },[dot,refreshVersion]);
 const search=(event:FormEvent<HTMLFormElement>)=>{
  event.preventDefault();const normalized=input.trim();
  if(!/^[1-9][0-9]{0,9}$/.test(normalized)){dispatch({type:'invalidate',generation:++generation.current,error:'Enter a valid positive USDOT number (up to ten digits).'});return;}
  if(normalized===dot){clearCarrierEvidenceCache(normalized);setRefreshVersion(value=>value+1);}
  else window.location.hash=atlasHash(normalized);
 };
 const inspections=evidence?.slices.inspections,crashes=evidence?.slices.crash;
 const partial=evidence&&(Boolean(evidence.errors.inspections)||Boolean(evidence.errors.crash)||!inspections||!crashes||Boolean(inspections?.truncated)||Boolean(crashes?.truncated));
 return <main className="t3-main t3-atlas-main" data-testid="carrier-atlas" data-load-generation={load.generation} data-load-state={load.status}>
   <section className="t3-atlas-banner">
    <div><span className="t3-atlas-overline">Transport3r · geographic evidence</span><h1>Carrier Geography Atlas</h1><p>Inspect where official roadside events were reported. Select state-level inspection and crash layers, open linked records and share a USDOT-specific view. Verified operating routes and natural-hazard overlays are separate future data products.</p></div>
    <form onSubmit={search} className="t3-atlas-search"><label htmlFor="t3-atlas-dot">USDOT number</label><div><input id="t3-atlas-dot" inputMode="numeric" value={input} onChange={event=>setInput(event.target.value)} placeholder="e.g. 3938496" maxLength={10} aria-label="USDOT number"/><button type="submit" disabled={loading}>{loading?'Loading carrier map...':'Load carrier map'}</button></div><small>View is linkable; no policy, location or private account data is uploaded.</small></form>
   </section>
   <div className="t3-atlas-proof"><div><strong>Published state locations</strong><span>Inspections and crash involvement</span></div><div><strong>No invented routes</strong><span>Carrier headquarters is not a freight corridor</span></div><div><strong>Hazards not scored</strong><span>External source layers await verified ingestion</span></div></div>
   {!dot&&!loading&&<section className="t3-atlas-empty"><h2>Select a carrier</h2><p>Open the official state-level event map using its USDOT. Suggested regression fixtures: <a href={atlasHash('3938496')}>3938496</a>, <a href={atlasHash('3706')}>3706</a>, <a href={atlasHash('2855794')}>2855794</a>. Their values may change with the source publication.</p></section>}
   {loading&&<section className="t3-atlas-empty" role="status"><h2>Loading published carrier geography</h2><p>Retrieving current bounded inspections and crash records for USDOT {dot}. The data has not yet passed a full-slice completeness audit.</p></section>}
   {error&&<section className="t3-atlas-error" role="alert"><strong>Carrier geography could not load.</strong><p>{error}</p><p>Source errors cannot be interpreted as a zero-event carrier.</p></section>}
   {evidence&&<div className="t3-atlas-map-panel">
     <div className="t3-atlas-viewline"><div><strong>USDOT {dot}</strong><span>Published event-state grouping; no route inference</span></div><a href={'#/carrier/'+dot+'/safety'}>Open full safety evidence →</a></div>
     {partial&&<div className="t3-atlas-warning" role="status">Some source data is missing, truncated or unavailable. Counts below describe only the successfully loaded request; they are not comprehensive lifetime totals.</div>}
     <RecentEventMap evidence={evidence}/>
     <div className="t3-atlas-provenance"><span>Inspections retrieved in browser: {inspections?.acquiredAt??'not loaded'}</span><span>Crashes retrieved in browser: {crashes?.acquiredAt??'not loaded'}</span><span>Data lineage: FMCSA source IDs fx4q-ay7w and aayw-vxb3. Retrieval times are not official publication dates.</span></div>
   </div>}
   <section className="t3-atlas-layer-section"><div className="t3-atlas-section-head"><div><span className="t3-atlas-overline">Source integration status</span><h2>External hazard & freight layers</h2><p>The FEMA county ingestion/index is implemented but not yet connected to this map; the other sources remain candidates. No geographic hazard score is calculated until datasets, provenance, coordinates, temporal coverage and carrier/route joins pass validation.</p></div><a href="#/integrity">Inspect source totals and integrity →</a></div><div className="t3-atlas-layers">{SOURCES.map(item=><article key={item.name}><div className="t3-atlas-layer-top"><span className="t3-atlas-unavailable">Not integrated</span><span>Official source candidate</span></div><h3>{item.name}</h3><p>{item.category}</p><small>{item.limit}</small><a href={item.url} target="_blank" rel="noreferrer">Source documentation →</a></article>)}</div></section>
   <p className="t3-atlas-bottom">Coverage is observational and has reporting limitations. H3 cells, verified geocoded terminals, actual traveled routes, FEMA risk polygons and prospective modeled exposure are not yet available. Unavailable evidence is not zero risk.</p>
 </main>;
}
