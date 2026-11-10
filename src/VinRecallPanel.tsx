import {useEffect,useRef,useState} from 'react';
import {loadVinRecallCandidates,type VinRecallCandidates} from './vinRecalls';

export function VinRecallPanel({vin}:{vin:string}){
  const [result,setResult]=useState<VinRecallCandidates|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const generation=useRef(0);
  useEffect(()=>{generation.current++;setResult(null);setError('');setBusy(false);},[vin]);
  async function load(){
    const request=++generation.current;setResult(null);setError('');setBusy(true);
    try{const value=await loadVinRecallCandidates(vin);if(request===generation.current)setResult(value);}
    catch(cause){if(request===generation.current)setError(cause instanceof Error?cause.message:String(cause));}
    finally{if(request===generation.current)setBusy(false);}
  }
  return <section className="t3-window-panel" data-testid="vin-recalls">
    <h3>Recall campaign research · NHTSA</h3>
    <p>Decode this verified observed VIN, then query NHTSA recall campaigns for the returned model year, make and model.</p>
    <button className="t3-button secondary" type="button" onClick={()=>void load()}>{busy?'Checking campaigns…':'Search recall campaigns'}</button>
    {busy&&<p role="status">Contacting NHTSA VIN and recall services…</p>}
    {error&&<p role="alert" className="c360-review warning">Recall research unavailable: {error}</p>}
    {result&&<>
      <p className={result.decoderWarning?'c360-review warning':''}><strong>{result.modelYear} {result.make} {result.model}</strong>{result.decoderWarning&&<span> · VIN decoder warning: {result.decoderMessage}</span>}</p>
      <p><strong>{result.campaigns.length.toLocaleString()} campaign candidate{result.campaigns.length===1?'':'s'}</strong> returned for that model-year/make/model combination.</p>
      <div className="t3-recall-list">{result.campaigns.slice(0,30).map((campaign,index)=><article key={campaign.campaignNumber+index}>
        <div><strong>{campaign.subject??'Recall campaign'}</strong><span>{campaign.campaignNumber}</span></div>
        <p>{[campaign.component,campaign.manufacturer,campaign.reportReceivedDate].filter(Boolean).join(' · ')||'Campaign metadata unavailable'}</p>
        {campaign.summary&&<details><summary>Campaign summary</summary><p>{campaign.summary}</p>{campaign.consequence&&<><strong>Consequence</strong><p>{campaign.consequence}</p></>}{campaign.remedy&&<><strong>Remedy</strong><p>{campaign.remedy}</p></>}</details>}
      </article>)}</div>
      {result.campaigns.length>30&&<p>First 30 of {result.campaigns.length.toLocaleString()} campaign candidates shown.</p>}
      <p>Retrieved {new Date(result.acquiredAt).toLocaleString()} · <a href={result.url} target="_blank" rel="noreferrer">NHTSA recall response ↗</a></p>
      <p className="c360-disclaimer">{result.limitation}</p>
    </>}
    <p className="c360-disclaimer">A campaign candidate is not a VIN-specific open-recall determination. A missing campaign result does not establish repaired, ignored or never-applicable status.</p>
    <a href="https://www.nhtsa.gov/recalls" target="_blank" rel="noreferrer">NHTSA VIN recall lookup ↗</a>
  </section>;
}
