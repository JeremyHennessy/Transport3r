export const FLEET_BANDS = [
  {code:'A',min:1,max:1,label:'1 power unit'},
  {code:'B',min:2,max:3,label:'2–3 power units'},
  {code:'C',min:4,max:6,label:'4–6 power units'},
  {code:'D',min:7,max:8,label:'7–8 power units'},
  {code:'E',min:9,max:11,label:'9–11 power units'},
  {code:'F',min:12,max:14,label:'12–14 power units'},
  {code:'G',min:15,max:17,label:'15–17 power units'},
  {code:'H',min:18,max:19,label:'18–19 power units'},
  {code:'I',min:20,max:23,label:'20–23 power units'},
  {code:'J',min:24,max:28,label:'24–28 power units'},
  {code:'K',min:29,max:32,label:'29–32 power units'},
  {code:'L',min:33,max:38,label:'33–38 power units'},
  {code:'M',min:39,max:44,label:'39–44 power units'},
  {code:'N',min:45,max:55,label:'45–55 power units'},
  {code:'O',min:56,max:75,label:'56–75 power units'},
  {code:'P',min:76,max:100,label:'76–100 power units'},
  {code:'Q',min:101,max:200,label:'101–200 power units'},
  {code:'R',min:201,max:300,label:'201–300 power units'},
  {code:'S',min:301,max:400,label:'301–400 power units'},
  {code:'T',min:401,max:550,label:'401–550 power units'},
  {code:'U',min:551,max:999,label:'551–999 power units'},
  {code:'V',min:1000,max:2000,label:'1,000–2,000 power units'},
  {code:'W',min:2001,max:3000,label:'2,001–3,000 power units'},
  {code:'X',min:3001,max:4000,label:'3,001–4,000 power units'},
  {code:'Y',min:4001,max:5000,label:'4,001–5,000 power units'},
  {code:'Z',min:5001,max:Number.POSITIVE_INFINITY,label:'Over 5,000 power units'},
] as const;

export type FleetBandCode = typeof FLEET_BANDS[number]['code'];
export type FleetBandAssessment = {
  status:'MATCH'|'MISMATCH'|'UNKNOWN';
  powerUnits:number|null;
  reported:FleetBandCode|null;
  expected:FleetBandCode|null;
};

export const FLEET_BAND_LABELS:Readonly<Record<string,string>>=Object.freeze(
  Object.fromEntries(FLEET_BANDS.map(({code,label})=>[code,label])),
);

const FLEET_BAND_CODES=new Set<string>(FLEET_BANDS.map(({code})=>code));

export function parseReportedPowerUnits(value:unknown):number|null{
  if(typeof value==='number')return Number.isSafeInteger(value)&&value>=1?value:null;
  if(typeof value!=='string')return null;
  const text=value.trim();
  if(!/^(?:\d+|\d{1,3}(?:,\d{3})+)$/.test(text))return null;
  const parsed=Number(text.replaceAll(',',''));
  return Number.isSafeInteger(parsed)&&parsed>=1?parsed:null;
}

export function reportedFleetBand(value:unknown):FleetBandCode|null{
  if(typeof value!=='string')return null;
  const code=value.trim().toUpperCase();
  return FLEET_BAND_CODES.has(code)?code as FleetBandCode:null;
}

export function expectedFleetBand(value:unknown):FleetBandCode|null{
  const powerUnits=parseReportedPowerUnits(value);
  if(powerUnits===null)return null;
  return FLEET_BANDS.find(({min,max})=>powerUnits>=min&&powerUnits<=max)?.code??null;
}

export function assessFleetBand(powerUnitValue:unknown,fleetCodeValue:unknown):FleetBandAssessment{
  const powerUnits=parseReportedPowerUnits(powerUnitValue);
  const reported=reportedFleetBand(fleetCodeValue);
  const expected=powerUnits===null?null:expectedFleetBand(powerUnits);
  return {
    status:reported===null||expected===null?'UNKNOWN':reported===expected?'MATCH':'MISMATCH',
    powerUnits,
    reported,
    expected,
  };
}
