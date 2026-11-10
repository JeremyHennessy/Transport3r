import {useMemo, useState, useEffect} from 'react';
import {type CarrierEvidence} from './carrierEvidence';
import {vinUnitEvidence} from './vinUnitEvidence';

export function VinUnitEvidencePanel({evidence,vin}:{evidence:CarrierEvidence;vin:string}) {
  const result=useMemo(()=>vinUnitEvidence(evidence,vin),[evidence,vin]);
  const [page,setPage]=useState(1),size=20;
  useEffect(()=>setPage(1),[vin,evidence.loadedAt]);
  const pages=Math.max(1,Math.ceil(result.linked.length/size)),current=Math.min(page,pages);
  return <section className="t3-vin-defects" data-testid="vin-unit-evidence">
    <h3>Vehicle-linked inspection findings</h3>
    <p>Each finding must match this carrier, an unambiguous inspection and its specific vehicle unit. A finding on another unit is not assigned to this VIN.</p>
    {!result.sourceAvailable?<p role="status">Violation evidence is unavailable. Missing records do not establish zero defects.</p>:<>
      <p><strong>{result.linked.length.toLocaleString()} linked violation records</strong> across {new Set(result.linked.map(row=>row.inspectionId)).size} inspections in the loaded evidence.
        {' '}{result.linked.filter(row=>row.outOfService===true).length} reported OOS flags; {result.linked.filter(row=>row.outOfService===null).length} unknown OOS values.</p>
      {result.partial&&<p className="c360-review warning">Evidence is partial or contains unassigned records; this is not a complete vehicle history.</p>}
      <p>{result.otherVinRows} records linked to other VINs; {result.unassignedRows} carrier-scope records could not be assigned to a vehicle; {result.duplicateRows} repeated source rows excluded from the derived count.</p>
      {result.unassignedRows>0&&<details><summary>Why carrier-scope records were not assigned</summary><ul>{Object.entries(result.reasons).map(([reason,count])=><li key={reason}>{reason.replaceAll('_',' ').toLowerCase()}: {count}</li>)}</ul><p>These are not findings attributed to the selected VIN.</p></details>}
      {result.repeatedCodes.length>0&&<p>Codes observed in more than one linked inspection: {result.repeatedCodes.map(row=>`${row.code} (${row.inspectionCount} inspections)`).join('; ')}. Repeated observations do not establish an unrepaired defect.</p>}
      {result.linked.slice((current-1)*size,current*size).map(row=><article className="t3-vin-finding" key={row.id}>
        <h4>{row.code??'Code unavailable'} - {row.description??'Description unavailable'}</h4>
        <p>{row.date??'Date unavailable'}; unit {row.unitNumber??'not reported'}; OOS: {row.outOfService===null?'unknown':row.outOfService?'reported yes':'reported no'}.</p>
        <p>Defect-verification source code: {row.defectVerificationCode??'not reported'}. No current repair or recall-completion status is inferred.</p>
        <p>Link method: {row.method==='unit_id'?'inspection and explicit unit ID':'inspection and unique unit number'}.</p>
        <a href={`#/carrier/${evidence.dotNumber}/inspection/${row.inspectionId}`}>Review inspection {row.inspectionId}</a>
        <details><summary>Source record and provenance</summary><p>Source {row.sourceId}; acquired {row.sourceAcquiredAt??'at an unavailable time'}.</p><pre>{JSON.stringify({publication:row.sourcePublication,record:row.raw},null,2)}</pre></details>
      </article>)}
      {!result.linked.length&&<p>No violation rows could be linked to this VIN in the loaded scope. This is not a clean maintenance or recall finding.</p>}
      {pages>1&&<div><button type="button" disabled={current<=1} onClick={()=>setPage(current-1)}>Previous findings</button><span> Page {current} of {pages} </span><button type="button" disabled={current>=pages} onClick={()=>setPage(current+1)}>Next findings</button></div>}
    </>}
    <p className="c360-disclaimer">Public roadside observations are not a maintenance log, driver identity, current ownership, insured schedule or proof of recall repair. Raw defect-verification codes are retained until a version-matched dictionary is verified.</p>
  </section>;
}
