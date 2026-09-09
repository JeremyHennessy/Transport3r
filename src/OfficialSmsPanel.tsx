import {useEffect,useRef,useState} from 'react';
import type {CarrierEvidence} from './carrierEvidence';
import {loadOfficialSmsBatch,officialSmsView,type OfficialSmsView} from './officialSms';

export function SmsDirectoryCell({view,dot,failed}:{view?:OfficialSmsView;dot:string;failed?:boolean}) {
  return <span data-testid="directory-sms"><a href={`#/carrier/${dot}/sms`}>{failed?'SMS unavailable - retry':!view?'Loading SMS…':view.status==='empty'?'No public SMS row':view.status==='unavailable'?'SMS unavailable — retry':view.basics.map(basic=>`${basic.short} ${basic.measure??'—'}`).join(' · ')}</a>{view?.status==='available'&&<small>Official measures{view.passenger?' · passenger percentiles in SMS':''}</small>}</span>;
}
export function OfficialSmsPanel({evidence}:{evidence:CarrierEvidence}) {
  const [fresh,setFresh]=useState<CarrierEvidence|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');const generation=useRef(0);
  useEffect(()=>{setFresh(null);setBusy(false);setError('');return()=>{generation.current++;};},[evidence]);
  async function refresh(){const request=++generation.current;setBusy(true);setError('');setFresh(null);try{const result=await loadOfficialSmsBatch(evidence.registry,[evidence.dotNumber]);if(request===generation.current)setFresh(result[evidence.dotNumber]);}catch(cause){if(request===generation.current)setError(String(cause));}finally{if(request===generation.current)setBusy(false);}}
  const view=officialSmsView(fresh?.dotNumber===evidence.dotNumber?fresh:evidence);
  return <section className="t3-window-panel" data-testid="official-sms"><div className="c360-section-head"><h3>Official FMCSA SMS measures</h3><button className="t3-button secondary" type="button" onClick={()=>void refresh()}>{busy?'Refreshing SMS…':'Refresh SMS values'}</button></div>
    <p>SMS publishes separate BASIC measures, not one overall carrier score. A measure is not a percentile or the Transport3r risk score.</p>
    {busy?<p role="status">Fetching official output populations…</p>:view.status!=='available'?<p role="status">{view.status==='empty'?'No public SMS output row returned for this USDOT.':'Official SMS output is unavailable or conflicting. Refresh to retry.'} Missing values are not zero.</p>:<>
      <div className="t3-coverage-scroll"><table className="t3-sms-values"><thead><tr><th>BASIC</th><th>Official measure</th><th>Published percentile</th><th>Published BASIC alert</th></tr></thead><tbody>{view.basics.map(basic=><tr key={basic.key} data-basic={basic.key}><th scope="row">{basic.label}</th><td data-value="measure">{basic.measure??'Not reported'}</td><td data-value="percentile">{view.passenger?(basic.percentile??'Not assigned / not reported'):'Not in public general output'}</td><td>{view.passenger?(basic.alert??'Not reported'):'Not in public general output'}</td></tr>)}</tbody></table></div>
      <p><a href={`https://data.transportation.gov/d/${view.sourceId}`} target="_blank" rel="noreferrer">Official source {view.sourceId} ↗</a> · {view.passenger?'Passenger-specific output':'General carrier output'} · retrieved {view.sources.find(source=>source.id===view.sourceId)?.acquiredAt??'time unavailable'}</p>
    </>}
    {error&&<p role="alert">{error}</p>}{view.status==='unavailable'&&!busy&&<details><summary>SMS availability details</summary><ul>{view.issues.map(issue=><li key={issue}>{issue}</li>)}{view.sources.filter(source=>source.error).map(source=><li key={source.id}>{source.id}: {source.error}</li>)}</ul></details>}
    <p className="c360-disclaimer">Hazmat and Crash Indicator values are not included in these public output files. Published measures remain visible when replay inputs are partial. An exact common SMS snapshot month is not established by the retrieval timestamp.</p>
  </section>;
}
