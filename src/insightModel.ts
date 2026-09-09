import {SOURCE_IDS, UNIT_FIELD_ALIASES, VIOLATION_FIELD_ALIASES, type CarrierEvidence, type EvidenceKey} from './carrierEvidence';
import {coverageRows, loadedDateRange} from './evidenceCoverage';
import {censusStatusLabel, parseDateValue, readValue, type DataRow} from './datahub';
import {orderSummary, filingChangeSummary} from './evidenceLifecycle';
import {officialSmsView} from './officialSms';

export const value = (row:DataRow|undefined, fields:string[]) => {
  if(!row)return 'Unavailable';const raw=readValue(row,fields);if(raw===undefined)return 'Not reported';
  if(fields[0]?.endsWith('_DATE'))return parseDateValue(raw)?.toISOString().slice(0,10)??`${raw} (unresolved date)`;
  if(['POWER_UNITS','TOTAL_DRIVERS','MCS150_MILEAGE'].includes(fields[0])&&/^\d+$/.test(raw))return Number(raw).toLocaleString('en-US');
  return raw;
};
export function sourceCount(e:CarrierEvidence,key:EvidenceKey) {
  const s=e.slices[key];return !s||e.errors[key]?'Unavailable':`${s.rows.length.toLocaleString()}${s.truncated?'+':''}`;
}
export function distribution(rows:DataRow[],fields:string[]) {
  const counts=new Map<string,number>();
  for(const row of rows){const label=readValue(row,fields)??'Not reported';counts.set(label,(counts.get(label)??0)+1);}
  return [...counts].map(([label,count])=>({label,count})).sort((a,b)=>b.count-a.count||a.label.localeCompare(b.label));
}
export function insight(e:CarrierEvidence,section:string) {
  const c=e.census??e.slices.census?.rows[0];
  const coverage=coverageRows(e), gaps=coverage.filter(row=>row.status==='partial'||row.status==='unavailable');
  const units=e.errors.units?[]:e.slices.units?.rows??[];
  const vins=distribution(units,[...UNIT_FIELD_ALIASES.vin]).filter(row=>row.label!=='Not reported');
  const identity=`${value(c,['LEGAL_NAME'])}${readValue(c??{},['DBA_NAME'])?` (DBA ${value(c,['DBA_NAME'])})`:''}, USDOT ${e.dotNumber}. ${censusStatusLabel(readValue(c??{},['STATUS_CODE']))} registration; operation ${value(c,['CARRIER_OPERATION'])} (${({A:'interstate',B:'intrastate hazmat',C:'intrastate non-hazmat'} as Record<string,string>)[value(c,['CARRIER_OPERATION'])]??'classification unresolved'}).`;
  const exposure=`Reports ${value(c,['POWER_UNITS'])} power units, ${value(c,['TOTAL_DRIVERS'])} drivers and ${value(c,['MCS150_MILEAGE'])} miles for mileage year ${value(c,['MCS150_MILEAGE_YEAR'])}. MCS-150 report date: ${value(c,['MCS150_DATE'])}; these exposures are not an insured schedule.`;
  const safety=`Loaded daily evidence: ${sourceCount(e,'inspections')} inspections, ${sourceCount(e,'crash')} crash-involvement records and ${sourceCount(e,'violations')} violation rows. Counts describe each source request, not a shared SMS month; crash involvement does not imply fault.`;
  const statuses=e.errors.motusCarrier?[]:distribution(e.slices.motusCarrier?.rows??[],['OP_AUTH_STATUS']);
  const auth=`Current/baseline authority rows: ${sourceCount(e,'motusCarrier')}${statuses.length?`; returned statuses: ${statuses.slice(0,4).map(row=>`${row.label} (${row.count})`).join(', ')}`:''}; authority-history rows: ${sourceCount(e,'motusAuthHistory')}; revoke/suspend rows: ${sourceCount(e,'motusRevokeSuspend')}. Historical actions do not establish current prohibition. ${orderSummary(e).text}`;
  const insurance=`Currently returned filings: ${sourceCount(e,'motusInsurance')}; previous filings: ${sourceCount(e,'motusInsuranceHistory')}. ${filingChangeSummary(e)} Current coverage and monetary source units require confirmation.`;
  const sms=officialSmsView(e);
  const smsText=sms.status==='available'?`Official SMS population: ${sms.passenger?'passenger-specific':'general carrier'} (${sms.sourceId}). Published BASIC measures are official evidence; replay is calculated separately. A shared exact SMS release month is not established.`:`Official SMS ${sms.status==='empty'?'returned no applicable row':'population is unavailable or unresolved'}. Missing outputs are not zero risk.`;
  const fleet=`${vins.length} distinct reported VINs in ${sourceCount(e,'units')} loaded unit rows; ${vins.filter(row=>row.count>1).length} VINs occur more than once. ${exposure} Roadside observations do not establish ownership or insurance.`;
  const paragraphs=section==='summary'?[identity,exposure,safety,auth,insurance,smsText]:section==='safety'?[safety]:section==='fleet'?[fleet]:section==='authority'?[auth]:section==='insurance'?[insurance]:section==='sms'?[smsText,'Replay compares measures only where relevant inspection inputs, denominators and official population can be resolved. Missing or capped inputs can make a replay unavailable without removing separately published measures.']:section==='inspection'?[`Inspection ${e.inspectionId} for USDOT ${e.dotNumber}: ${sourceCount(e,'units')} unit rows, ${sourceCount(e,'violations')} violation rows, ${sourceCount(e,'citations')} citations and ${sourceCount(e,'specialStudies')} special-study rows. Child evidence is limited to the verified parent inspection.`]:['Coverage describes request completeness, not a complete carrier history. Empty, partial and failed sources have different meanings.'];
  return {paragraphs,gaps,coverage,vins,limitation:`${gaps.length} source requests are partial or unavailable. Retrieved ${e.loadedAt}. Publication metadata, event dates and carrier report dates are distinct.`};
}

const TIMELINE_FIELDS:Partial<Record<EvidenceKey,Array<[string,string]>>>={
  inspections:[['INSP_DATE','Inspection']],crash:[['REPORT_DATE','Crash involvement']],
  motusAuthHistory:[['STATUS_CHANGE_DATE','Authority history']],motusAuthDelta:[['STATUS_CHANGE_DATE','Authority history change feed']],
  motusRevokeSuspend:[['ORDER1_SERVE_DATE','Order served'],['ORDER1_EFFECTIVE_DATE','Order effective']],
  motusInsurance:[['EFFECTIVE_DATE','Returned filing effective']],
  motusInsuranceHistory:[['EFFECTIVE_DATE','Previous filing effective'],['CANCL_EFFECTIVE_DATE','Previous filing ended/changed']],
  newEntrantOos:[['OOS_DATE','OOS order issued'],['RESCIND_DATE','Order rescission']],
};
export function evidenceTimeline(e:CarrierEvidence,keys:EvidenceKey[]) {
  return keys.flatMap(key=>e.errors[key]?[]:(e.slices[key]?.rows??[]).flatMap((row,index)=>(TIMELINE_FIELDS[key]??[]).flatMap(([field,label])=>{
    const date=parseDateValue(readValue(row,[field]));if(!date)return [];
    return [{key:`${key}:${index}:${field}`,date:date.toISOString().slice(0,10),label,source:SOURCE_IDS[key],detail:readValue(row,['OP_AUTH_STATUS','FILING_STATUS_REASON','ORDER1_TYPE_DESC','REPORT_NUMBER'])??'',inspection:key==='inspections'?readValue(row,['INSPECTION_ID']):undefined}];
  }))).sort((a,b)=>b.date.localeCompare(a.date)||a.key.localeCompare(b.key));
}
export function dailyActivity(e:CarrierEvidence,key:'inspections'|'crash') {
  const s=e.slices[key];if(!s||e.errors[key])return null;
  const field=key==='inspections'?'INSP_DATE':'REPORT_DATE';
  const range=loadedDateRange(s.rows,[field]);
  const rows=s.rows.flatMap(row=>{const date=parseDateValue(readValue(row,[field]));return date?[{month:date.toISOString().slice(0,7)}]:[];});
  return {range,partial:s.truncated,months:distribution(rows,['month']).sort((a,b)=>a.label.localeCompare(b.label))};
}
export function oosLoaded(e:CarrierEvidence) {
  const s=e.slices.violations;if(!s||e.errors.violations)return null;
  const flags=s.rows.map(row=>readValue(row,[...VIOLATION_FIELD_ALIASES.oos])?.toUpperCase());
  return {yes:flags.filter(x=>['Y','YES','TRUE','1'].includes(x??'')).length,unknown:flags.filter(x=>!['Y','YES','TRUE','1','N','NO','FALSE','0'].includes(x??'')).length,partial:s.truncated};
}
