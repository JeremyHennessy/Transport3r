import {SOURCE_IDS, type CarrierEvidence, type EvidenceKey} from './carrierEvidence';
import {fetchSourceJson, parseDateValue, readValue, type DataRow} from './datahub';

const CENSUS='az4n-8mr2';
const DATAHUB='https://data.transportation.gov/resource';
const META='https://data.transportation.gov/api/views/az4n-8mr2.json';
const SUSPENSION_START=new Date(Date.UTC(2026,5,1));
const SUSPENSION_GUIDANCE_OBSERVED=new Date(Date.UTC(2026,10,10));
const SUSPENSION_GUIDANCE_EXPIRES=new Date(Date.UTC(2026,11,11));

export type ReviewState='INFORMATION'|'REVIEW'|'DATA_GAP'|'TEMPORARY_SUSPENSION';
export type ComplianceCheck={id:string;title:string;state:ReviewState;sourceId:string;summary:string;action:string};
export type ComplianceReview={status:'REVIEW_NEEDED'|'INCOMPLETE_EVIDENCE'|'NO_RULE_TRIGGER';reviewCount:number;gapCount:number;asOf:string|null;checks:ComplianceCheck[];limitation:string};

function validDot(dot:string){return /^[1-9]\d{0,9}$/.test(dot);}
function iso(date:Date){return date.toISOString().slice(0,10);}
function lastDay(year:number,month:number){return new Date(Date.UTC(year,month,0));}
function numeric(value:unknown):number|null{
  if(typeof value==='number')return Number.isFinite(value)?value:null;
  if(typeof value!=='string'||!value.trim()||!/^[-+]?\d+(?:\.\d+)?$/.test(value.trim()))return null;
  const parsed=Number(value);return Number.isFinite(parsed)?parsed:null;
}
function escapeSoql(value:string){return value.replaceAll("'","''");}
function sourceRows(evidence:CarrierEvidence,key:EvidenceKey):DataRow[]|null{
  const slice=evidence.slices[key];
  return !slice||evidence.errors[key]||slice.sourceId!==SOURCE_IDS[key]||slice.truncated?null:slice.rows;
}

export function biennialReview(dot:string,mcs150Date:string|undefined,asOf=new Date()):ComplianceCheck {
  if(!validDot(dot)||dot.length<2)return{id:'BIENNIAL',title:'Biennial registration update',state:'DATA_GAP',sourceId:CENSUS,summary:'USDOT digits are unavailable for the filing-schedule calculation.',action:'Verify the USDOT identity with FMCSA before applying a filing schedule.'};
  const digits=dot.split('').map(Number),month=digits.at(-1)===0?10:digits.at(-1)!;
  const parity=digits.at(-2)!%2;
  let year=asOf.getUTCFullYear();
  if(year%2!==parity)year--;
  let due=lastDay(year,month);
  if(due.getTime()>asOf.getTime()){year-=2;due=lastDay(year,month);}
  const next=lastDay(year+2,month);
  const report=parseDateValue(mcs150Date);
  if(report&&report.getTime()>asOf.getTime()){
    return{id:'BIENNIAL',title:'Biennial registration update',state:'DATA_GAP',sourceId:CENSUS,
      summary:`Scheduled cycle ${iso(due)}. Latest Census report ${iso(report)} is later than the evidence review time ${iso(asOf)} and cannot establish filing status at this snapshot.`,
      action:'Verify the source date/cut and current FMCSA record before applying a filing conclusion.'};
  }
  const transitionCycle=due>=SUSPENSION_START&&due<=asOf;
  const guidanceFresh=asOf>=SUSPENSION_GUIDANCE_OBSERVED&&asOf<SUSPENSION_GUIDANCE_EXPIRES;
  const windowStart=new Date(due.getTime()-366*86400000);
  const recentEnough=!!report&&report>=windowStart;
  if(transitionCycle&&!guidanceFresh){
    return{id:'BIENNIAL',title:'Biennial registration update',state:'DATA_GAP',sourceId:CENSUS,
      summary:`Scheduled cycle ${iso(due)}. The temporary FMCSA transition guidance snapshot was verified ${iso(SUSPENSION_GUIDANCE_OBSERVED)} and requires re-verification after ${'2026-12-10'}. Latest Census report: ${report?iso(report):'unavailable'}.`,
      action:'Recheck the current FMCSA Motus transition notice before applying a due/overdue or suspension conclusion.'};
  }
  const suspended=transitionCycle&&guidanceFresh;
  const state:ReviewState=suspended?'TEMPORARY_SUSPENSION':!report?'DATA_GAP':!recentEnough&&due<=asOf?'REVIEW':'INFORMATION';
  const summary=suspended
    ? `Scheduled cycle ${iso(due)}. FMCSA transition guidance verified ${iso(SUSPENSION_GUIDANCE_OBSERVED)} gives additional time for biennial updates due on or after 2026-06-01 and temporarily suspends inactivation for that missed update. Latest Census report: ${report?iso(report):'unavailable'}.`
    : `Scheduled cycle ${iso(due)}; next scheduled cycle ${iso(next)}. Latest Census report: ${report?iso(report):'unavailable'}.`;
  return{id:'BIENNIAL',title:'Biennial registration update',state,sourceId:CENSUS,summary,
    action:suspended?'Do not label this carrier overdue from this rule. Verify current FMCSA transition guidance and the carrier record before action.'
      :recentEnough?'Verify applicability and confirm the filing in FMCSA/Motus; a Census report date is evidence, not filing certification.'
      :'Review the FMCSA/Motus record and applicable MCS-150 schedule; do not infer a violation from source age alone.'};
}

function datedWindow(rows:DataRow[],fields:string[],asOf:Date,days=30){
  let recent=0,unresolved=0;
  for(const row of rows){
    const values=fields.map(field=>readValue(row,[field])).filter((value):value is string=>value!==undefined);
    const dates=values.map(value=>parseDateValue(value)).filter((value):value is Date=>!!value);
    if(!dates.length){unresolved++;continue;}
    if(dates.some(date=>Math.abs((date.getTime()-asOf.getTime())/86400000)<=days))recent++;
  }
  return{recent,unresolved};
}
export function evidenceReviewDate(evidence:CarrierEvidence):Date|null {
  const raw=evidence.completenessReceipt?.backend==='verified_nationwide_warehouse'
    ? evidence.completenessReceipt.cutAvailableAt
    : evidence.loadedAt;
  if(!raw)return null;
  const value=new Date(raw);
  return Number.isFinite(value.getTime())?value:null;
}
export function complianceReview(carrier:DataRow,evidence:CarrierEvidence,asOf:Date|null=evidenceReviewDate(evidence)):ComplianceReview {
  const retainedCensus=evidence.completenessReceipt?.backend==='verified_nationwide_warehouse'
    ? evidence.census??evidence.slices.census?.rows[0]??null
    : null;
  const reviewCarrier=evidence.completenessReceipt?.backend==='verified_nationwide_warehouse'
    ? retainedCensus??{}
    : carrier;
  const dot=readValue(reviewCarrier,['DOT_NUMBER','USDOT_NUMBER'])??evidence.dotNumber;
  const checks:ComplianceCheck[]=[];
  const add=(id:string,title:string,key:EvidenceKey,state:ReviewState,summary:string,action:string)=>checks.push({id,title,state,sourceId:SOURCE_IDS[key],summary,action});
  const status=readValue(reviewCarrier,['STATUS_CODE']);
  add('REGISTRATION','Registration status','census',status==='A'?'INFORMATION':status==='I'||status==='P'?'REVIEW':'DATA_GAP',
    `Published Census status: ${status??'unknown'}.`,'Confirm the registration record and whether the planned operation requires operating authority.');
  checks.push(asOf?biennialReview(dot,readValue(reviewCarrier,['MCS150_DATE']),asOf):{
    id:'BIENNIAL',title:'Biennial registration update',state:'DATA_GAP',sourceId:CENSUS,
    summary:'Evidence acquisition/cut time is unavailable; the filing schedule cannot be evaluated against a defensible review clock.',
    action:'Restore a valid evidence acquisition/cut timestamp and re-run the review.'
  });
  const authority=sourceRows(evidence,'motusCarrier');
  if(authority===null)add('AUTHORITY','Operating authority','motusCarrier','DATA_GAP','Current authority evidence is unavailable or partial.','Refresh/complete the source; do not infer active authority from missing or truncated evidence.');
  else {
    const statuses=[...new Set(authority.map(row=>readValue(row,['OP_AUTH_STATUS','AUTH_STATUS'])?.trim().toLowerCase()).filter((x):x is string=>!!x))];
    add('AUTHORITY','Operating authority','motusCarrier',!authority.length||!statuses.length?'DATA_GAP':statuses.some(x=>x!=='active')?'REVIEW':'INFORMATION',
      `${authority.length} authority rows; ${statuses.join(', ')||'no status returned'}.`,'Review each authority type and applicability in FMCSA/Motus. Census registration status is separate.');
  }
  const filings=sourceRows(evidence,'motusInsurance');
  add('FILINGS','Active/pending insurance filings','motusInsurance',filings===null?'DATA_GAP':!filings.length?'REVIEW':'INFORMATION',
    filings===null?'Active/pending filing evidence is unavailable or partial.':`${filings.length} active/pending filing rows returned.`,
    'Confirm filing type, dates, policy documents and required authority. No returned filing does not by itself establish uninsured operation.');
  const history=sourceRows(evidence,'motusInsuranceHistory');
  if(history===null)add('FILING_CHANGES','Recent filing-history changes','motusInsuranceHistory','DATA_GAP','Insurance history evidence is unavailable or partial.','Refresh/complete the source before drawing a continuity conclusion.');
  else if(!asOf)add('FILING_CHANGES','Recent filing-history changes','motusInsuranceHistory','DATA_GAP','Evidence review time is unavailable; recent-change windows cannot be evaluated.','Restore a valid evidence acquisition/cut timestamp before drawing a continuity conclusion.');
  else {
    const window=datedWindow(history,['CANCL_EFFECTIVE_DATE','CANCEL_EFFECTIVE_DATE','EFFECTIVE_DATE','TRANS_DATE'],asOf);
    add('FILING_CHANGES','Recent filing-history changes','motusInsuranceHistory',window.unresolved?'DATA_GAP':window.recent?'REVIEW':'INFORMATION',
      `${window.recent} filing-history rows have a recognized date within 30 days; ${window.unresolved} rows lack a parseable recognized lifecycle date.`,
      window.unresolved?'Resolve the undated/unparseable filing-history rows before concluding there were no recent changes.':'Review cancellation, replacement, transfer and name-change reasons separately; history alone does not establish a coverage gap.');
  }
  const revoke=sourceRows(evidence,'motusRevokeSuspend');
  add('REVOCATION','Revoke/suspend history','motusRevokeSuspend',revoke===null?'DATA_GAP':revoke.length?'REVIEW':'INFORMATION',
    revoke===null?'Revoke/suspend evidence is unavailable or partial.':`${revoke.length} historical revoke/suspend rows returned.`,
    'Verify current effect and any reinstatement with current official authority evidence; historical orders are not automatically current prohibitions.');
  const oos=sourceRows(evidence,'newEntrantOos');
  add('NEW_ENTRANT_OOS','New Entrant OOS / rescission','newEntrantOos',oos===null?'DATA_GAP':oos.length?'REVIEW':'INFORMATION',
    oos===null?'New Entrant OOS evidence is unavailable or partial.':`${oos.length} New Entrant OOS/rescission rows returned.`,
    'Review issue and rescission dates. A source row is not by itself proof of current order effect.');
  const authHistory=sourceRows(evidence,'motusAuthHistory');
  if(authHistory===null)add('AUTHORITY_CHANGES','Recent authority-history changes','motusAuthHistory','DATA_GAP','Authority history is unavailable or partial.','Refresh/complete the source before drawing a lifecycle conclusion.');
  else if(!asOf)add('AUTHORITY_CHANGES','Recent authority-history changes','motusAuthHistory','DATA_GAP','Evidence review time is unavailable; recent-change windows cannot be evaluated.','Restore a valid evidence acquisition/cut timestamp before drawing a lifecycle conclusion.');
  else {
    const window=datedWindow(authHistory,['STATUS_CHANGE_DATE'],asOf);
    add('AUTHORITY_CHANGES','Recent authority-history changes','motusAuthHistory',window.unresolved?'DATA_GAP':window.recent?'REVIEW':'INFORMATION',
      `${window.recent} authority-history rows have a recognized status-change date within 30 days; ${window.unresolved} rows lack a parseable status-change date.`,
      window.unresolved?'Resolve the undated/unparseable authority-history rows before concluding there were no recent changes.':'Inspect the affected authority type, reason and effective date.');
  }
  const reviewCount=checks.filter(c=>c.state==='REVIEW').length;
  const gapCount=checks.filter(c=>c.state==='DATA_GAP').length;
  return{status:reviewCount?'REVIEW_NEEDED':gapCount?'INCOMPLETE_EVIDENCE':'NO_RULE_TRIGGER',reviewCount,gapCount,asOf:asOf?.toISOString()??null,checks,
    limitation:'Public evidence review at the recorded request time; accepted warehouse reviews bind Census status/report dates and all other evidence to the retained cut. Not legal-compliance certification, operating permission or insurance coverage. Partial, truncated or undated evidence remains a data gap. No rule trigger is not a clean-carrier conclusion.'};
}

type Publication={token:string;observedAt:string};
async function publication(signal?:AbortSignal):Promise<Publication>{
  const value=await fetchSourceJson(META,{signal,cache:'no-store',credentials:'omit'},20000) as Record<string,unknown>;
  if(value.id!==CENSUS||!Number.isSafeInteger(value.rowsUpdatedAt)||!Number.isSafeInteger(value.viewLastModified))throw new Error('Company Census publication metadata unavailable.');
  const observedAt=new Date((value.rowsUpdatedAt as number)*1000).toISOString();
  return{token:JSON.stringify([value.id,value.rowsUpdatedAt,value.viewLastModified]),observedAt};
}
async function censusQuery(params:URLSearchParams,signal?:AbortSignal){
  const payload=await fetchSourceJson(`${DATAHUB}/${CENSUS}.json?${params}`,{signal,cache:'no-store',credentials:'omit'},20000);
  if(!Array.isArray(payload))throw new Error('Company Census returned an unexpected payload.');
  return payload as DataRow[];
}
async function seedRow(dot:string,signal?:AbortSignal){
  const params=new URLSearchParams({'$where':`dot_number=${Number(dot)}`,'$limit':'2'});
  const rows=await censusQuery(params,signal);
  if(rows.length!==1||readValue(rows[0],['DOT_NUMBER'])?.replace(/^0+/,'')!==dot.replace(/^0+/,''))throw new Error('Company Census seed carrier identity is unavailable or ambiguous.');
  return rows[0];
}
function required(row:DataRow,field:string){
  const value=readValue(row,[field])?.trim();
  if(!value)throw new Error(`Public intelligence requires ${field}.`);
  return value;
}
export type PeerBenchmark={candidateCount:number;eligibleCount:number;excludedCount:number;averagePowerUnits:number|null;averageDrivers:number|null;targetPowerUnits:number|null;targetDrivers:number|null;country:string;operation:string;fleetBand:string;sourceObservedAt:string;insufficient:boolean;limitation:string};
export async function loadPeerBenchmark(carrier:DataRow,signal?:AbortSignal):Promise<PeerBenchmark>{
  const dot=required(carrier,'DOT_NUMBER');if(!validDot(dot))throw new Error('Peer comparison requires a valid USDOT.');
  const before=await publication(signal),seed=await seedRow(dot,signal);
  const country=required(seed,'PHY_COUNTRY'),operation=required(seed,'CARRIER_OPERATION'),fleetBand=required(seed,'FLEETSIZE');
  const asOf=new Date(before.observedAt),start=new Date(asOf.getTime()-730*86400000),day=(d:Date)=>d.toISOString().slice(0,10).replaceAll('-','');
  const base=`phy_country='${escapeSoql(country)}' AND carrier_operation='${escapeSoql(operation)}' AND fleetsize='${escapeSoql(fleetBand)}' AND status_code='A' AND dot_number<>${Number(dot)}`;
  const countParams=new URLSearchParams({'$select':'count(*) as count','$where':base});
  const eligible=`${base} AND power_units is not null AND total_drivers is not null AND power_units::number>0 AND total_drivers::number>0 AND mcs150_date between '${day(start)}' and '${day(asOf)}'`;
  const statParams=new URLSearchParams({'$select':'count(*) as count,avg(power_units::number) as avg_power_units,avg(total_drivers::number) as avg_drivers','$where':eligible});
  const [candidateRows,statRows]=await Promise.all([censusQuery(countParams,signal),censusQuery(statParams,signal)]);
  const after=await publication(signal);if(before.token!==after.token)throw new Error('Company Census changed during peer acquisition; retry.');
  if(candidateRows.length!==1||statRows.length!==1)throw new Error('Peer aggregates are unavailable.');
  const candidateCount=numeric(readValue(candidateRows[0],['COUNT']))??-1,eligibleCount=numeric(readValue(statRows[0],['COUNT']))??-1;
  if(!Number.isSafeInteger(candidateCount)||candidateCount<0||!Number.isSafeInteger(eligibleCount)||eligibleCount<0||eligibleCount>candidateCount)throw new Error('Peer aggregate counts are invalid.');
  return{candidateCount,eligibleCount,excludedCount:candidateCount-eligibleCount,averagePowerUnits:numeric(readValue(statRows[0],['AVG_POWER_UNITS'])),averageDrivers:numeric(readValue(statRows[0],['AVG_DRIVERS'])),
    targetPowerUnits:numeric(readValue(seed,['POWER_UNITS'])),targetDrivers:numeric(readValue(seed,['TOTAL_DRIVERS'])),country,operation,fleetBand,sourceObservedAt:after.observedAt,insufficient:eligibleCount<30,
    limitation:'Descriptive single-publication benchmark only. The target carrier and peers are acquired inside the same Company Census publication bracket. Peers are active registrations with the same country, operation and fleet-size band, positive reported power units/drivers and an MCS-150 date within the preceding 730 days. It is not an SMS percentile, claims benchmark or predictive risk score.'};
}

function clean(value:string|null|undefined){const v=value?.trim();return v&&v.length<=160&&!['NONE','UNKNOWN','N/A','NA','NULL'].includes(v.toUpperCase())?v:null;}
function normText(value:string|null|undefined){return clean(value)?.replace(/\s+/g,' ').toUpperCase()??null;}
function normDigits(value:string|null|undefined){const d=(value??'').replace(/\D/g,'');return d||null;}
function normEmail(value:string|null|undefined){return clean(value)?.toLowerCase()??null;}
function exactAddress(row:DataRow){const fields=['PHY_STREET','PHY_CITY','PHY_STATE','PHY_COUNTRY','PHY_ZIP'];const values=fields.map(f=>normText(readValue(row,[f])));return values.every(Boolean)?values.join(' | '):null;}
function digitPattern(value:string){return `%${value.split('').join('%')}%`;}
function tokenPattern(value:string){return `%${value.split(/\s+/).filter(Boolean).join('%')}%`;}
function like(field:string,pattern:string,fn?:'upper'|'lower'){const expr=fn?`${fn}(${field})`:field;return `${expr} like '${escapeSoql(pattern)}'`;}
function matchingCategories(seed:DataRow,row:DataRow){
  const result:string[]=[];
  const seedPhones=[readValue(seed,['PHONE']),readValue(seed,['CELL_PHONE'])].map(normDigits).filter((x):x is string=>!!x);
  const candidatePhones=[readValue(row,['PHONE']),readValue(row,['CELL_PHONE'])].map(normDigits).filter((x):x is string=>!!x);
  if(seedPhones.some(x=>candidatePhones.includes(x)))result.push('phone');
  const email=normEmail(readValue(seed,['EMAIL_ADDRESS']));if(email&&email===normEmail(readValue(row,['EMAIL_ADDRESS'])))result.push('email');
  const duns=normDigits(readValue(seed,['DUN_BRADSTREET_NO']));if(duns&&duns===normDigits(readValue(row,['DUN_BRADSTREET_NO'])))result.push('DUNS');
  const officers=[readValue(seed,['COMPANY_OFFICER_1']),readValue(seed,['COMPANY_OFFICER_2'])].map(normText).filter((x):x is string=>!!x);
  const otherOfficers=[readValue(row,['COMPANY_OFFICER_1']),readValue(row,['COMPANY_OFFICER_2'])].map(normText).filter((x):x is string=>!!x);
  if(officers.some(x=>otherOfficers.includes(x)))result.push('officer');
  const address=exactAddress(seed);if(address&&address===exactAddress(row))result.push('physical address');
  const seedDot=readValue(seed,['DOT_NUMBER']);const prior=readValue(seed,['PRIOR_REVOKE_DOT_NUMBER']);
  const otherDot=readValue(row,['DOT_NUMBER']);const otherPrior=readValue(row,['PRIOR_REVOKE_DOT_NUMBER']);
  if(prior&&normDigits(prior)===normDigits(otherDot))result.push('published prior-revocation reference');
  if(seedDot&&normDigits(otherPrior)===normDigits(seedDot))result.push('reverse prior-revocation reference');
  return [...new Set(result)];
}
export type RelatedLead={dot:string;name:string;status:string|null;reportDate:string|null;addedDate:string|null;matches:string[]};
export type RelatedLeadResult={totalReturned:number;partial:boolean;sourceObservedAt:string;leads:RelatedLead[];limitation:string};
export async function loadRelatedCarrierLeads(carrier:DataRow,signal?:AbortSignal):Promise<RelatedLeadResult>{
  const dot=required(carrier,'DOT_NUMBER');if(!validDot(dot))throw new Error('Relationship screening requires a valid USDOT.');
  const before=await publication(signal),seed=await seedRow(dot,signal),conditions:string[]=[];
  const phones=[readValue(seed,['PHONE']),readValue(seed,['CELL_PHONE'])].map(normDigits).filter((x):x is string=>!!x);
  for(const value of phones)conditions.push(like('phone',digitPattern(value)),like('cell_phone',digitPattern(value)));
  const email=normEmail(readValue(seed,['EMAIL_ADDRESS']));if(email)conditions.push(like('email_address',`%${email}%`,'lower'));
  const officers=[readValue(seed,['COMPANY_OFFICER_1']),readValue(seed,['COMPANY_OFFICER_2'])].map(normText).filter((x):x is string=>!!x);
  for(const value of officers)conditions.push(like('company_officer_1',tokenPattern(value),'upper'),like('company_officer_2',tokenPattern(value),'upper'));
  const duns=normDigits(readValue(seed,['DUN_BRADSTREET_NO']));if(duns)conditions.push(like('dun_bradstreet_no',digitPattern(duns)));
  const addressFields=['PHY_STREET','PHY_CITY','PHY_STATE','PHY_COUNTRY','PHY_ZIP'] as const;
  const address=addressFields.map(field=>normText(readValue(seed,[field])));
  if(address.every((value):value is string=>!!value))conditions.push(addressFields.map((field,i)=>like(field.toLowerCase(),tokenPattern(address[i]!),'upper')).join(' AND '));
  const prior=normDigits(readValue(seed,['PRIOR_REVOKE_DOT_NUMBER']));if(prior)conditions.push(`dot_number=${Number(prior)}`);
  conditions.push(`prior_revoke_dot_number=${Number(dot)}`);
  const params=new URLSearchParams({'$select':'dot_number,legal_name,status_code,add_date,mcs150_date,phone,cell_phone,email_address,company_officer_1,company_officer_2,dun_bradstreet_no,phy_street,phy_city,phy_state,phy_country,phy_zip,prior_revoke_dot_number',
    '$where':`dot_number<>${Number(dot)} AND (${conditions.map(c=>`(${c})`).join(' OR ')})`,'$order':'dot_number','$limit':'201'});
  const rows=await censusQuery(params,signal),after=await publication(signal);
  if(before.token!==after.token)throw new Error('Company Census changed during relationship screening; retry.');
  const leads=rows.map(row=>({dot:readValue(row,['DOT_NUMBER'])??'',name:readValue(row,['LEGAL_NAME'])??'Unnamed carrier',status:readValue(row,['STATUS_CODE'])??null,
    reportDate:readValue(row,['MCS150_DATE'])??null,addedDate:readValue(row,['ADD_DATE'])??null,matches:matchingCategories(seed,row)}))
    .filter(row=>validDot(row.dot)&&row.matches.length).sort((a,b)=>b.matches.length-a.matches.length||Number(a.dot)-Number(b.dot)).slice(0,200);
  return{totalReturned:leads.length,partial:rows.length>200,sourceObservedAt:after.observedAt,leads,
    limitation:'Investigation leads from exact-normalized public registration details inside one Company Census publication bracket. Candidate retrieval deliberately uses broader digit/token patterns and every displayed lead is rechecked with deterministic normalized equality. Shared contact details, officers, addresses, DUNS values or prior-revocation references can have legitimate explanations and do not prove fraud, evasion, ownership or a corporate relationship.'};
}
