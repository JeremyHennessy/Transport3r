import { fetchSourceJson, queryByDot, readValue, type DataSlice, type SchemaRegistry } from './datahub';
import { DAILY_DATE_FIELDS, validateEventWindow, type EventWindow } from './eventWindow';
import {completeQuery} from './completeEvidence';

export const WINDOW_SOURCES = [{id:'fx4q-ay7w',label:'Daily inspections'}, {id:'aayw-vxb3',label:'Daily crash involvement'}] as const;
async function watermark(id: string) {
  const value = await fetchSourceJson(`https://data.transportation.gov/api/views/${id}`) as Record<string,unknown>;
  if (!value || value.id !== id || !Number.isSafeInteger(value.rowsUpdatedAt) || !Number.isSafeInteger(value.viewLastModified)) throw new Error('Source publication metadata unavailable.');
  return { rowsUpdatedAt:value.rowsUpdatedAt as number, viewLastModified:value.viewLastModified as number };
}
export async function loadSafetyWindow(registry: SchemaRegistry, dot: string, selected: EventWindow, complete = false) {
  if (!/^[1-9]\d*$/.test(dot)) throw new Error('Invalid USDOT.');
  const window = validateEventWindow(selected);
  const sources = await Promise.all(WINDOW_SOURCES.map(async source => {
    try {
      const before = await watermark(source.id);
      const field=DAILY_DATE_FIELDS[source.id];
      const slice:DataSlice = complete ? {...await completeQuery(source.id,[`dot_number=${dot} AND ${field} between '${window.start.replaceAll('-','')}' and '${window.end.replaceAll('-','')}'`],row=>{
        const value=readValue(row,[field])??'',date=`${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}`;
        return /^\d{8}$/.test(value)&&Number.isFinite(Date.parse(date))&&new Date(date).toISOString().slice(0,10)===date&&date>=window.start&&date<=window.end&&readValue(row,['DOT_NUMBER'])===dot;
      },new AbortController().signal),scope:'carrier_date_window',eventWindow:window} : await queryByDot(registry,source.id,dot,{eventWindow:window,includeTotal:true,limit:500,orderAliases:[field]});
      const after = await watermark(source.id);
      if (JSON.stringify(before)!==JSON.stringify(after)) throw new Error('Source changed during acquisition. Apply the window again.');
      return { ...source, slice, before, after, error:undefined };
    } catch (error) { return { ...source, slice:undefined, before:undefined, after:undefined, error:error instanceof Error ? error.message : String(error) }; }
  }));
  return { dot, window, acquiredAt:new Date().toISOString(), sources };
}
export type SafetyWindowResult = Awaited<ReturnType<typeof loadSafetyWindow>>;
export function windowMonths(slice: DataSlice) {
  const window = validateEventWindow(slice.eventWindow!);
  const counts = new Map<string,number>();
  for (let date=new Date(`${window.start.slice(0,7)}-01`);date.toISOString().slice(0,7)<=window.end.slice(0,7);date.setUTCMonth(date.getUTCMonth()+1)) counts.set(date.toISOString().slice(0,7),0);
  for (const row of slice.rows) {
    const value=readValue(row,[DAILY_DATE_FIELDS[slice.sourceId]])!;
    const month=`${value.slice(0,4)}-${value.slice(4,6)}`;
    if (!counts.has(month)) throw new Error('Observation outside selected months.');
    counts.set(month,counts.get(month)!+1);
  }
  return [...counts].map(([month,loaded])=>({month,loaded,complete:!slice.truncated}));
}
