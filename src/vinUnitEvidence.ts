import {SOURCE_IDS, type CarrierEvidence} from './carrierEvidence';
import {readValue, type DataRow} from './datahub';
import {dailyCalendarDate} from './snapshotSafety';

function identifier(raw: string | undefined): string | null {
  const value = raw?.trim();
  return value && /^\d{1,32}$/.test(value) && !/^0+$/.test(value) ? value.replace(/^0+/, '') : null;
}
function vinValue(raw: string | undefined): string | null {
  const value = raw?.trim().toUpperCase();
  return value && /^[A-HJ-NPR-Z0-9]{17}$/.test(value) ? value : null;
}
function canonicalRecord(row: DataRow): string {
  return JSON.stringify(Object.fromEntries(Object.entries(row).sort(([a],[b])=>a.localeCompare(b))));
}
function groupRows(rows: DataRow[], key: (row: DataRow)=>string|null): Map<string,DataRow[]> {
  const grouped = new Map<string,DataRow[]>();
  for (const row of rows) { const id=key(row); if(id) grouped.set(id,[...(grouped.get(id)??[]),row]); }
  return grouped;
}
export type VinViolationObservation = {
  id:string; inspectionId:string; unitId:string|null; unitNumber:string|null;
  method:'unit_id'|'unique_unit_number'; date:string|null; code:string|null;
  description:string|null; outOfService:boolean|null; defectVerificationCode:string|null;
  sourceId:string; sourceAcquiredAt:string|null; sourcePublication:string|null;
  raw:DataRow;
};

/** Attribution uses inspection + explicit unit identity, never VIN alone across a fleet. */
export function vinUnitEvidence(evidence: CarrierEvidence, requestedVin: string) {
  const vin=vinValue(requestedVin), dot=identifier(evidence.dotNumber);
  const sourceKeys=['inspections','units','violations'] as const;
  const unavailable=sourceKeys.filter(key=>evidence.errors[key] || !evidence.slices[key] ||
    evidence.slices[key]?.sourceId!==SOURCE_IDS[key]);
  const parentRows=unavailable.includes('inspections')?[]:evidence.slices.inspections!.rows;
  const unitRows=unavailable.includes('units')?[]:evidence.slices.units!.rows;
  const violationRows=unavailable.includes('violations')?[]:evidence.slices.violations!.rows;
  const parents=groupRows(parentRows,row=>identifier(readValue(row,['INSPECTION_ID'])));
  const unitsById=groupRows(unitRows,row=>{
    const parent=identifier(readValue(row,['INSPECTION_ID'])),id=identifier(readValue(row,['INSP_UNIT_ID']));
    return parent&&id?`${parent}:${id}`:null;
  });
  const unitsByNumber=groupRows(unitRows,row=>{
    const parent=identifier(readValue(row,['INSPECTION_ID'])),number=identifier(readValue(row,['INSP_UNIT_NUMBER']));
    return parent&&number?`${parent}:${number}`:null;
  });
  const violationsById=groupRows(violationRows,row=>identifier(readValue(row,['INSP_VIOLATION_ID'])));
  const conflicts=new Set([...violationsById].filter(([,rows])=>new Set(rows.map(canonicalRecord)).size>1).map(([id])=>id));
  const reasons:Record<string,number>={},seen=new Set<string>();
  const linked:VinViolationObservation[]=[];
  let duplicateRows=0,otherVinRows=0,unassignedRows=0;
  function reject(reason:string){unassignedRows++;reasons[reason]=(reasons[reason]??0)+1;}
  for (const row of violationRows) {
    if(!dot||!vin){reject('INVALID_REQUEST_IDENTITY');continue;}
    const id=identifier(readValue(row,['INSP_VIOLATION_ID']));
    if(!id){reject('MISSING_VIOLATION_ID');continue;}
    if(conflicts.has(id)){reject('CONFLICTING_VIOLATION_ID');continue;}
    if(seen.has(id)){duplicateRows++;continue;} seen.add(id);
    const inspection=identifier(readValue(row,['INSPECTION_ID']));
    const parent=inspection?parents.get(inspection):undefined;
    if(!inspection||parent?.length!==1||identifier(readValue(parent[0],['DOT_NUMBER']))!==dot){
      reject('UNVERIFIED_INSPECTION_PARENT');continue;
    }
    const assertedDot=readValue(row,['DOT_NUMBER','USDOT_NUMBER']);
    if(assertedDot!==undefined&&identifier(assertedDot)!==dot){reject('CONFLICTING_CARRIER_ID');continue;}
    const rawUnitId=readValue(row,['INSP_UNIT_ID']),unitId=identifier(rawUnitId);
    const rawNumber=readValue(row,['INSP_VIOL_UNIT']),number=identifier(rawNumber);
    let candidates:DataRow[]|undefined,method:VinViolationObservation['method'];
    if(rawUnitId!==undefined){
      if(!unitId){reject('INVALID_EXPLICIT_UNIT_ID');continue;}
      candidates=unitsById.get(`${inspection}:${unitId}`);method='unit_id';
    }else{
      if(!number){reject('NO_SUPPORTED_VEHICLE_REFERENCE');continue;}
      if(evidence.slices.units?.truncated||unavailable.includes('units')){reject('INCOMPLETE_UNIT_NUMBER_LOOKUP');continue;}
      candidates=unitsByNumber.get(`${inspection}:${number}`);method='unique_unit_number';
    }
    if(candidates?.length!==1){reject(candidates?.length?'AMBIGUOUS_UNIT_REFERENCE':'UNIT_REFERENCE_NOT_FOUND');continue;}
    const unit=candidates[0],unitDot=readValue(unit,['DOT_NUMBER','USDOT_NUMBER']);
    if(unitDot!==undefined&&identifier(unitDot)!==dot){reject('CONFLICTING_UNIT_CARRIER');continue;}
    const matchedNumber=identifier(readValue(unit,['INSP_UNIT_NUMBER']));
    if(rawNumber!==undefined&&(!number||number!==matchedNumber)){reject('CONFLICTING_UNIT_REFERENCES');continue;}
    const matchedVin=vinValue(readValue(unit,['INSP_UNIT_VEHICLE_ID_NUMBER']));
    if(!matchedVin){reject('MISSING_OR_INVALID_UNIT_VIN');continue;}
    if(matchedVin!==vin){otherVinRows++;continue;}
    const oos=readValue(row,['OUT_OF_SERVICE_INDICATOR'])?.trim().toUpperCase();
    linked.push({id,inspectionId:inspection,unitId:identifier(readValue(unit,['INSP_UNIT_ID'])),
      unitNumber:matchedNumber,method,date:dailyCalendarDate(readValue(parent[0],['INSP_DATE'])),
      code:readValue(row,['VIOL_CODE'])??null,description:readValue(row,['VIOL_DESC'])??null,
      outOfService:oos==='Y'?true:oos==='N'?false:null,
      defectVerificationCode:readValue(row,['DEFECT_VERIFICATION_ID'])??null,
      sourceId:SOURCE_IDS.violations,sourceAcquiredAt:evidence.slices.violations?.acquiredAt??null,
      sourcePublication:evidence.slices.violations?.sourcePublication??null,raw:row});
  }
  const byCode=new Map<string,Set<string>>();
  for(const row of linked)if(row.code){const ids=byCode.get(row.code)??new Set<string>();ids.add(row.inspectionId);byCode.set(row.code,ids);}
  const repeatedCodes=[...byCode].filter(([,ids])=>ids.size>1).map(([code,ids])=>({code,inspectionCount:ids.size}));
  const partial=unavailable.length>0||sourceKeys.some(key=>evidence.slices[key]?.truncated)||unassignedRows>0;
  if(linked.length+otherVinRows+unassignedRows+duplicateRows!==violationRows.length)throw new Error('VIN attribution count conservation failed.');
  return {vin,sourceAvailable:!unavailable.includes('violations'),unavailable,partial,
    inputRows:unavailable.includes('violations')?null:violationRows.length,linked,otherVinRows,
    unassignedRows,duplicateRows,reasons,repeatedCodes,repairStatusEstablished:false,recallStatusEstablished:false};
}
