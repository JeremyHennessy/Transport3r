import {fetchSourceJson} from './datahub';
import {loadVinSpecifications,normalizedVin} from './vinSpecifications';

export type RecallCampaign={
  campaignNumber:string;manufacturer:string|null;subject:string|null;component:string|null;
  reportReceivedDate:string|null;summary:string|null;consequence:string|null;remedy:string|null;notes:string|null;
};
export type VinRecallCandidates={
  vin:string;make:string;model:string;modelYear:string;decoderWarning:boolean;decoderMessage:string;
  campaigns:RecallCampaign[];url:string;acquiredAt:string;
  limitation:string;
};

function text(row:Record<string,unknown>,key:string){
  const value=row[key];
  return typeof value==='string'&&value.trim()?value.trim():null;
}
function requiredField(fields:{key:string;value:string}[],key:string){
  const value=fields.find(field=>field.key===key)?.value?.trim();
  if(!value)throw new Error(`NHTSA VIN decode did not return ${key} required for campaign research.`);
  return value;
}
export function decodeRecallCampaigns(payload:unknown){
  if(!payload||typeof payload!=='object')throw new Error('NHTSA recall service returned an invalid response.');
  const source=(payload as {results?:unknown;Results?:unknown}).results??(payload as {Results?:unknown}).Results;
  if(!Array.isArray(source))throw new Error('NHTSA recall service did not return a campaign list.');
  if(source.length>5000)throw new Error('NHTSA recall campaign response exceeded the review ceiling.');
  return source.map((item,index)=>{
    if(!item||typeof item!=='object')throw new Error(`NHTSA recall campaign ${index+1} is invalid.`);
    const row=item as Record<string,unknown>;
    const campaignNumber=text(row,'NHTSACampaignNumber')??text(row,'CampaignNumber')??'Campaign number unavailable';
    return{campaignNumber,manufacturer:text(row,'Manufacturer'),subject:text(row,'Subject'),component:text(row,'Component'),
      reportReceivedDate:text(row,'ReportReceivedDate'),summary:text(row,'Summary'),consequence:text(row,'Consequence'),
      remedy:text(row,'Remedy'),notes:text(row,'Notes')} satisfies RecallCampaign;
  });
}
export async function loadVinRecallCandidates(value:string):Promise<VinRecallCandidates>{
  const vin=normalizedVin(value),decoded=await loadVinSpecifications(vin);
  const make=requiredField(decoded.fields,'Make'),model=requiredField(decoded.fields,'Model'),modelYear=requiredField(decoded.fields,'ModelYear');
  if(!/^\d{4}$/.test(modelYear)||Number(modelYear)<1900||Number(modelYear)>new Date().getUTCFullYear()+1)throw new Error('NHTSA returned an invalid model year for campaign research.');
  const params=new URLSearchParams({make,model,modelYear});
  const url=`https://api.nhtsa.gov/recalls/recallsByVehicle?${params}`;
  const campaigns=decodeRecallCampaigns(await fetchSourceJson(url,{cache:'no-store',credentials:'omit'},20000));
  return{vin,make,model,modelYear,decoderWarning:decoded.warning,decoderMessage:decoded.message,campaigns,url,acquiredAt:new Date().toISOString(),
    limitation:'Model-year/make/model campaign candidates only. This lookup does not establish that this VIN is included in a campaign, whether a recall is open, whether a remedy was completed, or current ownership/insurance status. Confirm VIN-specific applicability with NHTSA or the manufacturer.'};
}
