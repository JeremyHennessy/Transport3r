import {SOURCE_IDS,type CarrierEvidence,type EvidenceKey} from './carrierEvidence';
import {coverageRows} from './evidenceCoverage';
import {insight,oosLoaded,value,sourceCount} from './insightModel';
import {officialSmsView} from './officialSms';
import {parseDateValue,readValue,type DataRow} from './datahub';
import type {SafetyWindowResult} from './safetyWindow';

export function reportModel(e:CarrierEvidence,window:SafetyWindowResult) {
  if(e.dotNumber!==window.dot)throw Error('Report window and carrier identity differ.');
  const c=e.census??e.slices.census?.rows[0];
  if(!c||readValue(c,['DOT_NUMBER'])!==e.dotNumber)throw Error('Report requires matching Census identity.');
  const view=insight(e,'summary'),oos=oosLoaded(e),coverage=coverageRows(e);
  const eventCount=(id:string)=>{const source=window.sources.find(s=>s.id===id);return source?.slice&&!source.error?String(source.slice.total??`${source.slice.rows.length}${source.slice.truncated?'+':''}`):'Unavailable';};
  const reportDate=parseDateValue(readValue(c,['MCS150_DATE'])),at=parseDateValue(e.loadedAt);
  const age=reportDate&&at?Math.floor((at.getTime()-reportDate.getTime())/86400000):null;
  const checklist=[`Reconcile ${value(c,['POWER_UNITS'])} reported power units and ${value(c,['TOTAL_DRIVERS'])} drivers to the current operating fleet, insured schedule and staffing records.`];
  if(age===null||age>730)checklist.push(`Confirm the Census exposure: MCS-150 report age is ${age===null?'unavailable':`${age} days`}. Obtain current mileage and fleet records.`);
  if(e.slices.units?.rows.length)checklist.push(`Review the ${view.vins.length} distinct observed VINs and ${view.vins.filter(v=>v.count>1).length} repeated VINs against vehicle maintenance files; roadside observation does not establish ownership.`);
  if(oos?.yes)checklist.push(`Review corrective-action records for ${oos.yes}${oos.partial?'+':''} loaded OOS violation flags; the observations may span different dates from the selected daily window.`);
  if(e.slices.motusInsuranceHistory?.rows.length||e.slices.motusInsuranceHistoryDelta?.rows.length)checklist.push('Confirm filing cancellations/replacements with current policy documents; historical filings alone cannot establish a coverage gap.');
  if(e.slices.motusRevokeSuspend?.rows.length||e.slices.newEntrantOos?.rows.length)checklist.push('Verify the present effect of historical orders and any rescission with the official authority record.');
  if(readValue(c,['HM_IND'])==='Y'||readValue(c,['CRGO_PASSENGERS'])==='X')checklist.push('Confirm reported hazmat/passenger operations, equipment and applicable operating procedures.');
  if(view.gaps.length)checklist.push(`Resolve ${view.gaps.length} partial/unavailable sources before relying on an overall assessment.`);
  return {dot:e.dotNumber,name:value(c,['LEGAL_NAME']),dba:readValue(c,['DBA_NAME']),address:['PHY_STREET','PHY_CITY','PHY_STATE','PHY_ZIP'].map(field=>readValue(c,[field])).filter(Boolean).join(', ')||'Address unavailable',generatedAt:e.loadedAt,window:window.window,view,coverage,checklist,sms:officialSmsView(e),metrics:[['Power units',value(c,['POWER_UNITS'])],['Drivers',value(c,['TOTAL_DRIVERS'])],['Reported mileage',value(c,['MCS150_MILEAGE'])],['MCS-150 age',age===null?'Unavailable':age<0?'Future date - verify':`${age} days`],['Window inspections',eventCount('fx4q-ay7w')],['Window crashes',eventCount('aayw-vxb3')],['Observed VINs',e.errors.units||!e.slices.units?'Unavailable':`${view.vins.length}${e.slices.units.truncated?'+':''}`],['Returned filings',sourceCount(e,'motusInsurance')]]};
}
const COLUMNS:Partial<Record<EvidenceKey,string[]>>={
  inspections:['inspection_id','insp_date','report_state','report_number','oos_total'],crash:['crash_id','report_date','state','location','fatalities'],
  units:['inspection_id','insp_unit_vehicle_id_number','insp_unit_make','insp_unit_type_id','insp_unit_number'],
  violations:['inspection_id','viol_code','viol_desc','out_of_service_indicator','insp_viol_unit'],
  citations:['inspection_id','citation_id','citation_number','citation_date'],specialStudies:['inspection_id','ss_code','ss_desc'],
  motusCarrier:['docket_number','op_auth_type','op_auth_status','legal_name'],motusAuthHistory:['docket_number','op_auth_type','op_auth_status','status_change_date'],
  motusInsurance:['docket_number','insurance_company_name','ins_type_code','effective_date','max_cov_amount'],motusInsuranceHistory:['docket_number','insurance_company_name','filing_status_reason','effective_date','cancl_effective_date'],
};
export function appendixColumns(key:EvidenceKey,rows:DataRow[]) {
  const fields=[...new Set(rows.flatMap(row=>Object.keys(row)))];
  const preferred=COLUMNS[key]??['docket_number','usdot_number','dot_number','effective_date','status_change_date','op_auth_status','insurance_company_name','inspection_id'];
  return [...preferred.filter(field=>fields.includes(field)),...fields.filter(field=>!preferred.includes(field))].slice(0,5);
}
export function reportArchive(e:CarrierEvidence,window:SafetyWindowResult){return {version:'carrier-report-v1',evidenceClass:['OFFICIAL_FMCSA','TRANSPORT_CALCULATED'],dot:e.dotNumber,generatedAt:e.loadedAt,window,evidence:e,sourceIds:SOURCE_IDS,modelScore:null};}
