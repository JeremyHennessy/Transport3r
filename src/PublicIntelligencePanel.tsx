import {useEffect,useMemo,useRef,useState} from 'react';
import type {CarrierEvidence} from './carrierEvidence';
import {Timeline} from './CarrierInsight';
import {complianceReview,loadPeerBenchmark,loadRelatedCarrierLeads,type PeerBenchmark,type RelatedLeadResult} from './publicIntelligence';
import {readValue,type DataRow} from './datahub';

function number(value:number|null){return value===null?'—':Math.round(value).toLocaleString();}
function ratio(target:number|null,average:number|null){
  if(target===null||average===null||average<=0)return 'Unavailable';
  const pct=Math.round((target/average-1)*100);
  return `${pct>=0?'+':''}${pct}% vs peer average`;
}
function stateLabel(value:string){return value.replaceAll('_',' ').toLowerCase().replace(/^./,x=>x.toUpperCase());}

export function PublicIntelligencePanel({carrier,evidence}:{carrier:DataRow;evidence:CarrierEvidence}){
  const review=useMemo(()=>complianceReview(carrier,evidence),[carrier,evidence]);
  const [peer,setPeer]=useState<PeerBenchmark|null>(null),[peerError,setPeerError]=useState(''),[peerBusy,setPeerBusy]=useState(false);
  const [related,setRelated]=useState<RelatedLeadResult|null>(null),[relatedError,setRelatedError]=useState(''),[relatedBusy,setRelatedBusy]=useState(false);
  const peerGeneration=useRef(0),relatedGeneration=useRef(0),dot=readValue(carrier,['DOT_NUMBER'])??evidence.dotNumber;
  useEffect(()=>{peerGeneration.current++;relatedGeneration.current++;setPeer(null);setPeerError('');setPeerBusy(false);setRelated(null);setRelatedError('');setRelatedBusy(false);},[dot]);
  async function peers(){
    const request=++peerGeneration.current;setPeer(null);setPeerError('');setPeerBusy(true);
    try{const value=await loadPeerBenchmark(carrier);if(request===peerGeneration.current)setPeer(value);}
    catch(cause){if(request===peerGeneration.current)setPeerError(cause instanceof Error?cause.message:String(cause));}
    finally{if(request===peerGeneration.current)setPeerBusy(false);}
  }
  async function relationships(){
    const request=++relatedGeneration.current;setRelated(null);setRelatedError('');setRelatedBusy(true);
    try{const value=await loadRelatedCarrierLeads(carrier);if(request===relatedGeneration.current)setRelated(value);}
    catch(cause){if(request===relatedGeneration.current)setRelatedError(cause instanceof Error?cause.message:String(cause));}
    finally{if(request===relatedGeneration.current)setRelatedBusy(false);}
  }
  return <section className="c360-card t3-intelligence" data-testid="public-intelligence">
    <div className="c360-section-head"><div><div className="t3-eyebrow">Open-data underwriting intelligence</div><h2>Compliance, peers, relationships and incidents</h2></div><div className="c360-badge-stack"><span className="c360-badge official">Official-source evidence</span><span className="c360-badge calculated">Transport calculated</span></div></div>
    <p className="c360-disclaimer">This view turns public evidence into review queues and descriptive comparisons. It does not certify legal compliance, prove fraud/ownership, predict claims or change an insurance decision. Compliance review clock: {review.asOf?new Date(review.asOf).toLocaleString():'unavailable'}.</p>

    <div className="t3-intel-block">
      <div className="t3-intel-head"><div><div className="t3-eyebrow">W09 · regulatory compliance tracking</div><h3>Evidence-backed review checks</h3></div><span className={`t3-intel-status ${review.status.toLowerCase()}`}>{stateLabel(review.status)}</span></div>
      <div className="t3-intel-checks">{review.checks.map(check=><article key={check.id} className={`state-${check.state.toLowerCase()}`}><div><strong>{check.title}</strong><span>{stateLabel(check.state)}</span></div><p>{check.summary}</p><small>{check.action}</small><a href={`https://data.transportation.gov/d/${check.sourceId}`} target="_blank" rel="noreferrer">{check.sourceId} ↗</a></article>)}</div>
      <p className="t3-insight-limit">{review.limitation} FMCSA transition guidance was verified November 10, 2026. For affected cycles, this ruleset suppresses an overdue label only through December 10, 2026; after that date it becomes a data gap until the guidance is re-verified.</p>
      <p><a href="https://www.fmcsa.dot.gov/registration/temporary-suspension-biennial-update-requirement" target="_blank" rel="noreferrer">FMCSA temporary biennial-update suspension ↗</a> · <a href="https://www.fmcsa.dot.gov/registration/updating-your-registration" target="_blank" rel="noreferrer">FMCSA filing schedule ↗</a></p>
    </div>

    <div className="c360-split t3-intel-split">
      <div className="t3-intel-block">
        <div className="t3-intel-head"><div><div className="t3-eyebrow">W15 · peer benchmarking</div><h3>Comparable reported exposure</h3></div><button className="t3-button secondary" type="button" onClick={()=>void peers()}>{peerBusy?'Loading peers…':'Compare peers'}</button></div>
        <p>Active Company Census registrations with the same country, operation and fleet-size band; recent positive reported power units and drivers only.</p>
        {peerError&&<p role="alert" className="c360-review warning">{peerError}</p>}
        {peer&&<><div className="c360-metric-grid four"><div className="c360-metric"><span>Eligible peers</span><strong>{peer.eligibleCount.toLocaleString()}</strong><small>{peer.excludedCount.toLocaleString()} excluded from {peer.candidateCount.toLocaleString()} candidates</small></div><div className="c360-metric"><span>Power units</span><strong>{number(peer.targetPowerUnits)}</strong><small>Peer avg {number(peer.averagePowerUnits)} · {ratio(peer.targetPowerUnits,peer.averagePowerUnits)}</small></div><div className="c360-metric"><span>Drivers</span><strong>{number(peer.targetDrivers)}</strong><small>Peer avg {number(peer.averageDrivers)} · {ratio(peer.targetDrivers,peer.averageDrivers)}</small></div><div className="c360-metric"><span>Peer definition</span><strong>{peer.country} · {peer.operation} · {peer.fleetBand}</strong><small>Source observed {new Date(peer.sourceObservedAt).toLocaleString()}</small></div></div>{peer.insufficient&&<p className="c360-review warning"><strong>Insufficient comparison sample.</strong> Fewer than 30 eligible registrations were returned; do not use the average as a benchmark.</p>}<p className="c360-disclaimer">{peer.limitation}</p></>}
      </div>

      <div className="t3-intel-block">
        <div className="t3-intel-head"><div><div className="t3-eyebrow">W05 · Chameleon-style screening</div><h3>Related-registration leads</h3></div><button className="t3-button secondary" type="button" onClick={()=>void relationships()}>{relatedBusy?'Screening…':'Find registration leads'}</button></div>
        <p>Exact public registration details only: contact fields, officers, DUNS, full physical address and published prior-revocation references. No name-similarity guesswork.</p>
        {relatedError&&<p role="alert" className="c360-review warning">{relatedError}</p>}
        {related&&<>{related.partial&&<p className="c360-review warning">More than 200 source candidates matched the query. The displayed lead set is partial.</p>}<p><strong>{related.leads.length.toLocaleString()} review lead{related.leads.length===1?'':'s'}</strong> · source observed {new Date(related.sourceObservedAt).toLocaleString()}</p><div className="t3-related-list">{related.leads.slice(0,50).map(lead=><article key={lead.dot}><div><a href={`#/carrier/${lead.dot}/intelligence`}><strong>{lead.name}</strong></a><span>USDOT {lead.dot} · status {lead.status??'unknown'}</span></div><p>{lead.matches.join(' · ')}</p><small>Report {lead.reportDate??'unavailable'} · added {lead.addedDate??'unavailable'}</small></article>)}</div>{!related.leads.length&&<p>No exact related-registration leads were returned from the current public Census query. This is not proof that no affiliated or predecessor carrier exists.</p>}<p className="c360-disclaimer">{related.limitation}</p></>}
      </div>
    </div>

    <div className="t3-intel-block">
      <div className="t3-eyebrow">W06 · accident and incident reporting</div><h3>Combined dated public-evidence timeline</h3>
      <p>Safety involvement, authority lifecycle, insurance history and enforcement stay separate by source and date. Crash involvement does not establish fault, and filing changes do not establish a paid insurance loss.</p>
      <Timeline evidence={evidence} keys={['inspections','crash','motusAuthHistory','motusInsuranceHistory','motusRevokeSuspend','newEntrantOos']}/>
    </div>
  </section>;
}
