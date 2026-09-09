import { fetchSourceJson } from './datahub';

export function normalizedVin(value:string) {
  const vin=value.trim().toUpperCase();
  if (!/^[A-HJ-NPR-Z0-9]{17}$/.test(vin)) throw new Error('NHTSA lookup requires a full 17-character VIN without I, O or Q.');
  return vin;
}
const FIELDS={Make:'Make',Model:'Model',ModelYear:'Model year',Manufacturer:'Manufacturer',VehicleType:'Vehicle type',BodyClass:'Body class',GVWR:'Gross vehicle weight rating class',FuelTypePrimary:'Primary fuel',PlantCountry:'Manufacturing country'};
export function decodeSpecification(payload:unknown,requested:string) {
  const vin=normalizedVin(requested);
  if (!payload || typeof payload!=='object') throw new Error('NHTSA returned an invalid response.');
  const results=(payload as {Results?:unknown}).Results;
  if (!Array.isArray(results)||results.length!==1||!results[0]||typeof results[0]!=='object') throw new Error('NHTSA returned an ambiguous or empty VIN response.');
  const row=results[0] as Record<string,unknown>;
  if (typeof row.VIN!=='string'||row.VIN.toUpperCase()!==vin) throw new Error('NHTSA response VIN does not match the observed VIN.');
  if (typeof row.ErrorCode!=='string'||!/^\d+(;\s*\d+)*$/.test(row.ErrorCode.trim())) throw new Error('NHTSA decode status unavailable.');
  const warning=row.ErrorCode.split(';').some(code=>code.trim()!=='0');
  const fields=Object.entries(FIELDS).flatMap(([key,label])=>typeof row[key]==='string'&&row[key].trim()?[{key,label,value:row[key].trim()}]:[]);
  return {vin,warning,code:row.ErrorCode,message:typeof row.ErrorText==='string'?row.ErrorText:'Decoder warning; verify the original VIN.',fields};
}
export async function loadVinSpecifications(vin:string) {
  const normalized=normalizedVin(vin);
  const url=`https://vpic.nhtsa.dot.gov/api/vehicles/DecodeVinValues/${normalized}?format=json`;
  return {...decodeSpecification(await fetchSourceJson(url,{},15000),normalized),url,acquiredAt:new Date().toISOString()};
}
