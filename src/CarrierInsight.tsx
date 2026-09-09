import {type CarrierEvidence, type EvidenceKey, UNIT_FIELD_ALIASES, VIOLATION_FIELD_ALIASES} from './carrierEvidence';
import {dailyActivity,distribution,evidenceTimeline,insight,oosLoaded} from './insightModel';

export function Bars({title,rows,note}:{title:string;rows:{label:string;count:number}[];note:string}) {
  const max=Math.max(1,...rows.map(row=>row.count));
  return <figure className="t3-insight-bars"><figcaption><strong>{title}</strong><p>{note}</p></figcaption>{!rows.length?<p>No usable records in this request.</p>:rows.slice(0,12).map(row=><div key={row.label}><span>{row.label}</span><meter min={0} max={max} value={row.count} aria-label={`${row.label}: ${row.count}`}/><b>{row.count}</b></div>)}{rows.length>12&&<small>First 12 of {rows.length} categories; full evidence remains below.</small>}</figure>;
}
export function Timeline({evidence,keys}:{evidence:CarrierEvidence;keys:EvidenceKey[]}) {
  const events=evidenceTimeline(evidence,keys);
  return <div className="t3-insight-timeline"><h4>Dated evidence timeline</h4><p>Latest 12 of {events.length} dated loaded events. Historical and future-effective records do not certify current state.</p><ol>{events.slice(0,12).map(event=><li key={event.key}><time>{event.date}</time> <strong>{event.label}</strong> {event.detail} <small>{event.source}</small>{event.inspection&&<a href={`#/carrier/${evidence.dotNumber}/inspection/${event.inspection}`}>Open inspection</a>}</li>)}</ol>{!events.length&&<p>No usable event dates returned.</p>}</div>;
}
export function CarrierInsight({evidence,section}:{evidence:CarrierEvidence;section:string}) {
  const view=insight(evidence,section),oos=oosLoaded(evidence);
  const timeline:EvidenceKey[]=section==='authority'?['motusAuthHistory','motusAuthDelta','motusRevokeSuspend','newEntrantOos']:section==='insurance'?['motusInsurance','motusInsuranceHistory']:[];
  return <section className="c360-card t3-insight" data-testid="carrier-insight"><div className="t3-eyebrow">Evidence-backed context</div><h2>At a glance</h2>{view.paragraphs.map(text=><p key={text}>{text}</p>)}
    {(section==='summary'||section==='safety')&&<div className="c360-split">{(['inspections','crash'] as const).map(key=>{const activity=dailyActivity(evidence,key);return activity?<Bars key={key} title={key==='inspections'?'Loaded daily inspections by month':'Loaded daily crash involvement by month'} rows={activity.months} note={`${activity.range.start??'No dates'} to ${activity.range.end??'no dates'}. ${activity.partial?'Partial records; counts are lower bounds.':'Loaded request only.'} ${activity.range.missing+activity.range.invalid+activity.range.conflicting} unusable dates. Missing months are not shown as zero.`}/>:<p key={key}>{key} activity unavailable.</p>;})}</div>}
    {(section==='safety'||section==='inspection')&&<><p>Loaded OOS violation flags: {oos?`${oos.yes}${oos.partial?'+':''}; ${oos.unknown} unknown flags`:'Unavailable'}. This is a violation-row count, not an inspection OOS rate.</p><Bars title="Loaded violation themes" rows={distribution(evidence.errors.violations?[]:evidence.slices.violations?.rows??[],[...VIOLATION_FIELD_ALIASES.description])} note="Loaded violation rows; repeated violations are counted separately. Unknown categories remain visible."/></>}
    {section==='fleet'&&<Bars title="Observed unit make mix" rows={distribution(evidence.errors.units?[]:evidence.slices.units?.rows??[],[...UNIT_FIELD_ALIASES.make])} note="Unit observations, including repeat observations; not a current owned fleet mix."/>}
    {timeline.length>0&&<Timeline evidence={evidence} keys={timeline}/>}
    {section==='evidence'&&<div className="t3-source-matrix">{view.coverage.map(row=><a href={`https://data.transportation.gov/d/${row.sourceId}`} target="_blank" rel="noreferrer" key={row.key} className={`status-${row.status}`}><strong>{row.key}</strong><span>{row.status} · {row.loaded??'?'}/{row.requestTotal??'?'} loaded/total</span><small>{row.sourceId} · {row.acquiredAt??'acquisition unavailable'}</small></a>)}</div>}
    <p className="t3-insight-limit">{view.limitation}</p>
  </section>;
}

