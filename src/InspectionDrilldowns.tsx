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

export function InspectionDetail({ evidence, onRetry }: { evidence: CarrierEvidence; onRetry: () => void }) {
  const parent = evidence.slices.inspections?.rows[0];
  const id = evidence.inspectionId!, dot = evidence.dotNumber;
  return <section className="c360-card" data-testid="inspection-detail">
    <div className="c360-section-head"><div><div className="t3-eyebrow">Inspection drillthrough</div><h2>Inspection {id}</h2></div><a className="t3-button text" href={`#/carrier/${dot}/safety`}>Back to Safety</a></div>
    <button type="button" className="t3-button secondary" onClick={onRetry}>Refresh inspection evidence</button>
    {!parent ? <div className="c360-review warning"><strong>{evidence.errors.inspections ?? 'This inspection was not returned for this USDOT.'}</strong><p>The record may be outside the published source window. Child records require a verified carrier and inspection match.</p></div> : <>
      <p><strong>Report {readValue(parent,['REPORT_NUMBER']) ?? 'number unavailable'}</strong> · {formatDateValue(readValue(parent,['INSP_DATE']))} · {readValue(parent,['REPORT_STATE']) ?? 'State unavailable'} · Level {readValue(parent,['INSP_LEVEL_ID']) ?? 'unavailable'}</p>
      <div className="c360-metric-grid four">{(['units','violations','citations','specialStudies'] as const).map(key => <div className="c360-metric" key={key}><span>{({units:'Observed units',violations:'Violation rows',citations:'Citation rows',specialStudies:'Special study rows'})[key]}</span><strong>{evidence.errors[key] ? '—' : rowCountLabel(evidence.slices[key])}</strong></div>)}</div>
      <p className="c360-disclaimer">Retrieved directly by inspection ID and verified against USDOT {dot}. Each child request is limited to 5,000 rows; partial and failed requests are shown below. This is not a complete carrier history.</p>
      <h3 className="c360-subhead">Inspection record</h3><Records rows={[parent]}/>
      <h3 className="c360-subhead">Observed vehicle units</h3>
      {evidence.errors.units ? <p>{evidence.errors.units}</p> : <div className="t3-coverage-scroll"><table className="inspection-observations"><thead><tr><th>VIN / observations</th><th>Make</th><th>Type</th><th>Plate</th><th>State</th><th>Unit</th></tr></thead><tbody>{(evidence.slices.units?.rows ?? []).map((row,i) => <tr key={i}><td><VinLink row={row} dot={dot} inspection={id}/></td>{(['make','type','plate','plateState','unitNumber'] as const).map(key => <td key={key}>{readValue(row,[...UNIT_FIELD_ALIASES[key]]) ?? '—'}</td>)}</tr>)}</tbody></table></div>}
      {!evidence.errors.units && !evidence.slices.units?.rows.length && <p>No unit rows returned for this inspection.</p>}
      {(['violations','citations','specialStudies'] as const).map(key => <div key={key}><h3 className="c360-subhead">{({violations:'Violations',citations:'Citations',specialStudies:'Special studies'})[key]}</h3><Records rows={evidence.slices[key]?.rows ?? []} unavailable={evidence.errors[key]}/></div>)}
    </>}
    <p className="c360-disclaimer">An observed VIN proves a reported roadside-inspection association, not ownership or insurance coverage.</p>
    <EvidenceStatus evidence={evidence}/>
  </section>;
}

export function ObservedVinDetail({ evidence, vin }: { evidence: CarrierEvidence; vin: string }) {
  const observed = observedVinRows(evidence,vin), dot = evidence.dotNumber;
  return <section className="c360-card" data-testid="vin-detail"><div className="c360-section-head"><div><div className="t3-eyebrow">Observed vehicle evidence</div><h2>VIN {vin}</h2></div><a href={`#/carrier/${dot}/fleet`}>Back to Fleet</a></div>
    <p>{observed.rows.length} verified unit observation{observed.rows.length===1?'':'s'} in {evidence.inspectionId ? `inspection ${evidence.inspectionId}` : 'the loaded recent carrier inspection window'}.</p>
    <p className="c360-disclaimer">Scope: {evidence.inspectionId ? 'the selected inspection only' : 'up to 500 recent carrier inspections and their bounded unit requests'}. These are roadside observations, not a current fleet schedule, ownership determination, or complete VIN history.</p>
    {evidence.inspectionId && <p><a href={`#/carrier/${dot}/vin/${encodeURIComponent(vin)}`}>Search this VIN in the recent carrier inspection window →</a></p>}
    {(observed.incomplete || observed.rejected>0) && <p className="c360-review warning">Observation evidence is partial or unavailable. {observed.rejected} unit rows could not be matched to an unambiguous carrier inspection.</p>}
    {!observed.rows.length ? <p>No verified observations for this VIN in this request scope.</p> : <div className="t3-coverage-scroll"><table className="inspection-observations"><thead><tr><th>Date</th><th>Report</th><th>State</th><th>Unit / make</th><th>Inspection</th></tr></thead><tbody>{observed.rows.map(({unit,parent,inspectionId},i) => <tr key={i}><td>{formatDateValue(readValue(parent,['INSP_DATE']))}</td><td>{readValue(parent,['REPORT_NUMBER']) ?? '—'}</td><td>{readValue(parent,['REPORT_STATE']) ?? '—'}</td><td>{readValue(unit,[...UNIT_FIELD_ALIASES.unitNumber]) ?? '—'} / {readValue(unit,[...UNIT_FIELD_ALIASES.make]) ?? '—'}</td><td><a href={`#/carrier/${dot}/inspection/${inspectionId}`}>Open inspection {inspectionId} →</a></td></tr>)}</tbody></table></div>}
    {observed.rows.length>0&&<VinSpecifications key={`${dot}:${vin}`} vin={vin}/>}
    <EvidenceStatus evidence={evidence}/>
  </section>;
}
