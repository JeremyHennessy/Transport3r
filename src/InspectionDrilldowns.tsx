import {Timeline} from './CarrierInsight';
import { UNIT_FIELD_ALIASES, rowCountLabel, type CarrierEvidence } from './carrierEvidence';
import { EvidenceStatus } from './EvidenceStatus';
import { formatDateValue, readValue, type DataRow } from './datahub';
import { observedVinRows } from './inspectionEvidence';
import { VinSpecifications } from './VinSpecificationsPanel';

export function VinLink({ row, dot, inspection }: { row: DataRow; dot: string; inspection?: string }) {
  const vin = readValue(row, [...UNIT_FIELD_ALIASES.vin]);
  return vin ? <a href={`#/carrier/${dot}/vin/${encodeURIComponent(vin)}${inspection ? `?inspection=${encodeURIComponent(inspection)}` : ''}`}>{vin}</a> : <>—</>;
}

function Records({ rows, unavailable }: { rows: DataRow[]; unavailable?: string }) {
  if (unavailable) return <p className="c360-review warning">{unavailable}</p>;
  if (!rows.length) return <p>No rows returned for this inspection.</p>;
  return <div className="c360-raw-list">{rows.map((row,i) => <details key={i}><summary>Source record {i+1}</summary><pre>{JSON.stringify(row,null,2)}</pre></details>)}</div>;
}

function DrillMetric({label,value,detail}:{label:string;value:string;detail?:string}) {
  return <div className="c360-metric"><span>{label}</span><strong>{value}</strong>{detail&&<small>{detail}</small>}</div>;
}

export function InspectionDetail({ evidence, onRetry }: { evidence: CarrierEvidence; onRetry: () => void }) {
  const parent = evidence.slices.inspections?.rows[0];
  const id = evidence.inspectionId!, dot = evidence.dotNumber;
  const units=evidence.slices.units?.rows??[],violations=evidence.slices.violations?.rows??[];
  const oosRows=violations.filter(row=>['Y','YES','1','TRUE'].includes((readValue(row,['OUT_OF_SERVICE_INDICATOR','OOS_IND','OUT_OF_SERVICE'])??'').toUpperCase())).length;
  return <section className="c360-card" data-testid="inspection-detail">
    <div className="c360-section-head"><div><div className="t3-eyebrow">Inspection drillthrough</div><h2>Inspection {id}</h2></div><div className="t3-actions"><button type="button" className="t3-button secondary" onClick={onRetry}>Refresh evidence</button><a className="t3-button text" href={`#/carrier/${dot}/safety`}>Back to Safety</a></div></div>
    {!parent ? <div className="c360-review warning"><strong>{evidence.errors.inspections ?? 'This inspection was not returned for this USDOT.'}</strong><p>The record may be outside the published source window. Child records require a verified carrier and inspection match.</p></div> : <>
      <div className="c360-metric-grid six t3-drill-metrics"><DrillMetric label="Report" value={readValue(parent,['REPORT_NUMBER']) ?? '—'} detail="Official inspection report"/><DrillMetric label="Inspection date" value={formatDateValue(readValue(parent,['INSP_DATE']))}/><DrillMetric label="State" value={readValue(parent,['REPORT_STATE']) ?? '—'} detail="Reporting jurisdiction"/><DrillMetric label="Level" value={readValue(parent,['INSP_LEVEL_ID']) ?? '—'} detail="Inspection level"/><DrillMetric label="Observed units" value={evidence.errors.units?'—':rowCountLabel(evidence.slices.units)} detail="Inspection-unit rows"/><DrillMetric label="Violation rows" value={evidence.errors.violations?'—':rowCountLabel(evidence.slices.violations)} detail={`${oosRows}${evidence.slices.violations?.truncated?'+':''} loaded OOS flags`}/></div>
      <div className="t3-drill-callout"><strong>What this inspection contains</strong><span>{units.length.toLocaleString()} observed unit row{units.length===1?'':'s'} · {violations.length.toLocaleString()} violation row{violations.length===1?'':'s'} · {rowCountLabel(evidence.slices.citations)} citation row{evidence.slices.citations?.rows.length===1?'':'s'} · {rowCountLabel(evidence.slices.specialStudies)} special-study row{evidence.slices.specialStudies?.rows.length===1?'':'s'}.</span></div>
      <p className="c360-disclaimer">Retrieved directly by inspection ID and verified against USDOT {dot}. Each child request is limited to 5,000 rows; partial and failed requests are shown below. This is not a complete carrier history.</p>
      <h3 className="c360-subhead">Observed vehicle units</h3>
      {evidence.errors.units ? <p>{evidence.errors.units}</p> : <div className="t3-coverage-scroll"><table className="inspection-observations"><thead><tr><th>VIN / observations</th><th>Make</th><th>Type</th><th>Plate</th><th>State</th><th>Unit</th></tr></thead><tbody>{units.map((row,i) => <tr key={i}><td><VinLink row={row} dot={dot} inspection={id}/></td>{(['make','type','plate','plateState','unitNumber'] as const).map(key => <td key={key}>{readValue(row,[...UNIT_FIELD_ALIASES[key]]) ?? '—'}</td>)}</tr>)}</tbody></table></div>}
      {!evidence.errors.units && !units.length && <p>No unit rows returned for this inspection.</p>}
      <h3 className="c360-subhead">Violations</h3><Records rows={violations} unavailable={evidence.errors.violations}/>
      <div className="c360-split"><div><h3 className="c360-subhead">Citations</h3><Records rows={evidence.slices.citations?.rows ?? []} unavailable={evidence.errors.citations}/></div><div><h3 className="c360-subhead">Special studies</h3><Records rows={evidence.slices.specialStudies?.rows ?? []} unavailable={evidence.errors.specialStudies}/></div></div>
      <details className="t3-parent-record"><summary>View complete parent inspection source record</summary><Records rows={[parent]}/></details>
    </>}
    <p className="c360-disclaimer">An observed VIN proves a reported roadside-inspection association, not ownership or insurance coverage.</p>
    <EvidenceStatus evidence={evidence}/>
  </section>;
}

export function ObservedVinDetail({ evidence, vin }: { evidence: CarrierEvidence; vin: string }) {
  const observed = observedVinRows(evidence,vin), dot = evidence.dotNumber;
  const inspectionIds=new Set(observed.rows.map(row=>row.inspectionId));
  const rawDates=observed.rows.map(({parent})=>readValue(parent,['INSP_DATE'])).filter((value):value is string=>Boolean(value)).sort();
  const makes=[...new Set(observed.rows.map(({unit})=>readValue(unit,[...UNIT_FIELD_ALIASES.make])).filter((value):value is string=>Boolean(value)))];
  const types=[...new Set(observed.rows.map(({unit})=>readValue(unit,[...UNIT_FIELD_ALIASES.type])).filter((value):value is string=>Boolean(value)))];
  return <section className="c360-card" data-testid="vin-detail"><div className="c360-section-head"><div><div className="t3-eyebrow">Observed vehicle evidence</div><h2>VIN {vin}</h2></div><a className="t3-button text" href={`#/carrier/${dot}/fleet`}>Back to Fleet</a></div>
    <div className="c360-metric-grid four t3-drill-metrics"><DrillMetric label="Verified observations" value={observed.rows.length.toLocaleString()} detail={evidence.inspectionId?'Selected inspection scope':'Loaded recent carrier window'}/><DrillMetric label="Linked inspections" value={inspectionIds.size.toLocaleString()}/><DrillMetric label="Latest observation" value={rawDates.length?formatDateValue(rawDates.at(-1)):'—'}/><DrillMetric label="Observed make / type" value={makes[0]??'—'} detail={types.join(', ')||'Type unavailable'}/></div>
    <div className="t3-drill-callout"><strong>Roadside evidence, not an insured schedule</strong><span>This VIN has {observed.rows.length} verified unit observation{observed.rows.length===1?'':'s'} across {inspectionIds.size} linked inspection{inspectionIds.size===1?'':'s'} in this request scope.</span></div>
    <p className="c360-disclaimer">Scope: {evidence.inspectionId ? 'the selected inspection only' : 'up to 500 recent carrier inspections and their bounded unit requests'}. These are roadside observations, not a current fleet schedule, ownership determination, or complete VIN history.</p>
    {evidence.inspectionId && <p><a href={`#/carrier/${dot}/vin/${encodeURIComponent(vin)}`}>Search this VIN in the recent carrier inspection window →</a></p>}
    {(observed.incomplete || observed.rejected>0) && <p className="c360-review warning">Observation evidence is partial or unavailable. {observed.rejected} unit rows could not be matched to an unambiguous carrier inspection.</p>}
    {!observed.rows.length ? <p>No verified observations for this VIN in this request scope.</p> : <div className="t3-coverage-scroll"><table className="inspection-observations"><thead><tr><th>Date</th><th>Report</th><th>State</th><th>Unit / make</th><th>Inspection</th></tr></thead><tbody>{observed.rows.map(({unit,parent,inspectionId},i) => <tr key={i}><td>{formatDateValue(readValue(parent,['INSP_DATE']))}</td><td>{readValue(parent,['REPORT_NUMBER']) ?? '—'}</td><td>{readValue(parent,['REPORT_STATE']) ?? '—'}</td><td>{readValue(unit,[...UNIT_FIELD_ALIASES.unitNumber]) ?? '—'} / {readValue(unit,[...UNIT_FIELD_ALIASES.make]) ?? '—'}</td><td><a href={`#/carrier/${dot}/inspection/${inspectionId}`}>Open inspection {inspectionId} →</a></td></tr>)}</tbody></table></div>}
    {observed.rows.length>0&&<Timeline evidence={{...evidence,slices:{...evidence.slices,inspections:{...evidence.slices.inspections!,rows:observed.rows.map(row=>row.parent)}}}} keys={['inspections']}/>} 
    {observed.rows.length>0&&<VinSpecifications key={`${dot}:${vin}`} vin={vin}/>}
    <EvidenceStatus evidence={evidence}/>
  </section>;
}
