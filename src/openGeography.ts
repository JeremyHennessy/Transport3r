/** Display-only regional geography. No registered address is used as an event location. */
import boundaries from './stateBoundaries.json';
import {fetchSourceJson, readValue, parseDateValue, type DataRow} from './datahub';
import {SOURCE_IDS, type CarrierEvidence} from './carrierEvidence';
import {dailyCalendarDate, dailyCarrierMatches} from './snapshotSafety';
import type {FeatureCollection, MultiPolygon} from 'geojson';

function unproject(code: string, x: number, y: number): [number, number] {
  if (code === 'AK') return [x / 3 - 180, 72 - (y - 420) / 4];
  if (code === 'HI') return [(x - 200) / 10 - 161, 23 - (y - 440) / 10];
  if (code === 'PR') return [(x - 650) / 14 - 68, 19 - (y - 450) / 14];
  return [x / 12 - 125, 50 - y / 19];
}
export const GEOGRAPHY_SOURCE = {url: boundaries.source, vintage: boundaries.vintage, sha256: boundaries.sha256};
export const REGIONS = new Map(boundaries.states.map(state => [state.code, unproject(state.code, state.x, state.y)]));
export const DISPLAY_BOUNDARIES: FeatureCollection<MultiPolygon> = {
  type: 'FeatureCollection',
  features: boundaries.states.map(state => ({type: 'Feature', properties: {code: state.code}, geometry: {
    type: 'MultiPolygon',
    // Invert the repository's rounded, Census-derived display geometry only.
    // These rings are not suitable for risk intersection or address geocoding.
    coordinates: [...state.path.matchAll(/M([^Z]+)Z/g)].map(match => {
      const ring = match[1].split('L').map(point => {const [x,y] = point.split(',').map(Number); return unproject(state.code,x,y);});
      if (ring.length && (ring[0][0] !== ring.at(-1)![0] || ring[0][1] !== ring.at(-1)![1])) ring.push([...ring[0]]);
      return [ring];
    }),
  }})),
};
export type MapRegion = {code: string; count: number; inspections?: number; crashes?: number; reporting?: number};
export type DirectoryGeography = {regions: MapRegion[]; matched: number; mapped: number; unlocated: number; acquiredAt: string; publication: string};

export function geographyQuery(query: string, grouped: boolean, offset = 0): URLSearchParams {
  const source = new URLSearchParams(query), result = new URLSearchParams();
  for (const key of ['$where','$q']) if (source.has(key)) result.set(key,source.get(key)!);
  result.set('$select', grouped ? 'phy_country,phy_state,count(*) as count' : 'count(*) as count');
  if (grouped) { result.set('$group','phy_country,phy_state'); result.set('$order','phy_country,phy_state'); result.set('$limit','250'); result.set('$offset',String(offset)); }
  return result;
}
function count(value: unknown): number {
  if (!(typeof value === 'number' || typeof value === 'string' && /^[0-9]+$/.test(value))) throw Error('Invalid source group count');
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed) || parsed < 0) throw Error('Invalid source group count');
  return parsed;
}
export function reconcileDirectoryGroups(rows: DataRow[], expected: number): Omit<DirectoryGeography, 'acquiredAt' | 'publication'> {
  count(expected);
  let matched = 0, unlocated = 0;
  const seen = new Set<string>(), regions = new Map<string, number>();
  for (const row of rows) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) throw Error('Invalid source geography group');
    const country = row.phy_country ?? '', state = row.phy_state ?? '';
    if (typeof country !== 'string' || typeof state !== 'string') throw Error('Invalid regional identifier');
    const key = JSON.stringify([country,state]);
    if (seen.has(key)) throw Error('Repeated geography group; pagination changed');
    seen.add(key); const n = count(row.count); matched += n;
    if (!Number.isSafeInteger(matched)) throw Error('Unsafe aggregate count');
    const code = state.trim().toUpperCase();
    if (['US','USA'].includes(country.trim().toUpperCase()) && REGIONS.has(code)) regions.set(code,(regions.get(code) ?? 0) + n);
    else unlocated += n;
  }
  if (matched !== expected) throw Error('Grouped geography does not reconcile to the filtered source total');
  return {matched, mapped: matched-unlocated, unlocated, regions: [...regions].map(([code,n]) => ({code,count:n})).sort((a,b)=>b.count-a.count || a.code.localeCompare(b.code))};
}
function publication(value: unknown): string {
  const m = value as {id?: string; tableId?: unknown; rowsUpdatedAt?: unknown; columns?: unknown[]};
  if (m?.id !== 'az4n-8mr2' || m.tableId == null || !Number.isSafeInteger(m.rowsUpdatedAt) || !Array.isArray(m.columns)) throw Error('Source geography publication metadata unavailable');
  return JSON.stringify([m.id,m.tableId,m.rowsUpdatedAt,m.columns]);
}
export async function loadDirectoryGeography(query: string, signal: AbortSignal): Promise<DirectoryGeography> {
  const metadata = 'https://data.transportation.gov/api/views/az4n-8mr2.json';
  const load = (url: string) => fetchSourceJson(url,{signal,cache:'no-store',credentials:'omit'},20000);
  const before = publication(await load(metadata));
  const base = 'https://data.transportation.gov/resource/az4n-8mr2.json?';
  const total = await load(base+geographyQuery(query,false)) as DataRow[];
  if (!Array.isArray(total) || total.length !== 1) throw Error('Filtered geography total unavailable');
  const expected = count(total[0]?.count), rows: DataRow[] = [];
  for (let page = 0; ; page++) {
    if (page >= 8) throw Error('Geography group ceiling exceeded; incomplete map withheld');
    const batch = await load(base+geographyQuery(query,true,page*250));
    if (!Array.isArray(batch) || batch.length > 250) throw Error('Invalid geography page');
    rows.push(...batch as DataRow[]);
    if (batch.length < 250) break;
  }
  const after = publication(await load(metadata));
  if (before !== after) throw Error('Census publication changed during map acquisition; retry');
  if (signal.aborted) throw new DOMException('Map request cancelled','AbortError');
  return {...reconcileDirectoryGroups(rows,expected), acquiredAt: new Date().toISOString(), publication: after};
}

export type SafetyMapOptions = {inspections: boolean; crashes: boolean; includeReporting: boolean; start: string; end: string};
export type SafetyRecord = {kind: 'inspection' | 'crash'; id: string; state: string; date: string; location: string; precision: 'event state' | 'reporting jurisdiction'};
export function safetyGeography(evidence: CarrierEvidence, options: SafetyMapOptions) {
  for (const value of [options.start, options.end]) if (value && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !parseDateValue(value))) throw Error('Use valid calendar dates');
  if (options.start && options.end && options.start > options.end) throw Error('Start date must not follow end date');
  const regions = new Map<string, MapRegion>(), records: SafetyRecord[] = [];
  let considered = 0, unlocated = 0, invalidDates = 0, outsideWindow = 0, reportingExcluded = 0, rejected = 0;
  const unavailable: string[] = [];
  for (const [key,kind,enabled] of [['inspections','inspection',options.inspections],['crash','crash',options.crashes]] as const) {
    if (!enabled) continue;
    const slice = evidence.slices[key];
    if (!slice || evidence.errors[key] || slice.sourceId !== SOURCE_IDS[key]) {unavailable.push(key); continue;}
    for (const row of slice.rows) {
      if (!dailyCarrierMatches(row, evidence.dotNumber)) {rejected++; continue;}
      const date = dailyCalendarDate(readValue(row,kind === 'inspection' ? ['INSP_DATE'] : ['REPORT_DATE'])) ?? '';
      if (!date) {invalidDates++; if (options.start || options.end) continue;}
      if (date && (options.start && date < options.start || options.end && date > options.end)) {outsideWindow++; continue;}
      considered++;
      const eventState = readValue(row,kind === 'inspection' ? ['COUNTY_CODE_STATE'] : ['STATE'])?.trim().toUpperCase();
      // Only inspections have the documented REPORT_STATE jurisdiction fallback.
      const reportState = kind === 'inspection' ? readValue(row,['REPORT_STATE'])?.trim().toUpperCase() : undefined;
      const eventKnown = REGIONS.has(eventState ?? '');
      const reporting = !eventKnown && REGIONS.has(reportState ?? '');
      if (reporting && !options.includeReporting) {reportingExcluded++; continue;}
      const state = eventKnown ? eventState! : reporting ? reportState! : '';
      if (!REGIONS.has(state)) {unlocated++; continue;}
      const region = regions.get(state) ?? {code:state,count:0,inspections:0,crashes:0,reporting:0};
      region.count++; if (kind === 'inspection') region.inspections!++; else region.crashes!++;
      if (reporting) region.reporting!++; regions.set(state,region);
      records.push({kind,id:readValue(row,kind === 'inspection' ? ['INSPECTION_ID'] : ['CRASH_ID']) ?? '',state,date,
        location:readValue(row,['LOCATION_DESC','LOCATION','CITY']) ?? 'Specific location not reported',
        precision:reporting?'reporting jurisdiction':'event state'});
    }
  }
  return {regions:[...regions.values()].sort((a,b)=>b.count-a.count || a.code.localeCompare(b.code)),records,considered,
    unlocated,invalidDates,outsideWindow,reportingExcluded,rejected,unavailable,mapped:records.length,
    partial:['inspections','crash'].some(key => (key === 'inspections' ? options.inspections : options.crashes) && evidence.slices[key as 'inspections'|'crash']?.truncated)};
}
