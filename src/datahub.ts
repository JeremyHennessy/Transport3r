import { DAILY_DATE_FIELDS, validateEventWindow, type EventWindow } from './eventWindow';
export type DataRow = Record<string, unknown>;

export type SchemaColumn = {
  position: number | null;
  name: string | null;
  field_name: string | null;
  data_type: string | null;
  description: string | null;
};

export type SourceSchema = {
  id: string;
  name: string;
  family: string;
  rows_updated_at: string | null;
  metadata_url: string;
  resource_url: string;
  download_url: string;
  columns: SchemaColumn[];
};

export type SchemaRegistry = {
  generated_at: string;
  source_count: number;
  field_count: number;
  sources: SourceSchema[];
};

export type DataSlice = {
  sourceId: string;
  rows: DataRow[];
  total: number | null;
  truncated: boolean;
  scope?: 'carrier' | 'loaded_inspections' | 'dockets' | 'inspection' | 'carrier_date_window';
  eventWindow?: EventWindow;
  acquiredAt?: string;
};

const DATAHUB = 'https://data.transportation.gov/resource';
const USDOT_ALIASES = ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM', 'USDOT_NO', 'DOT_NO', 'US_DOT_NUMBER'];
const INSPECTION_ID_ALIASES = ['INSPECTION_ID', 'INSP_ID'];
const DOCKET_ALIASES = ['PREFIX_DOCKET_NUMBER', 'DOCKET_NUMBER', 'DOCKET_NO'];
const REQUEST_TIMEOUT_MS = 9000;

let schemaPromise: Promise<SchemaRegistry> | null = null;

function normalize(value: string | null | undefined): string {
  return String(value ?? '')
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

export function readValue(row: DataRow, aliases: string[]): string | undefined {
  const normalizedAliases = new Set(aliases.map(normalize));
  for (const [key, raw] of Object.entries(row)) {
    if (raw === null || raw === undefined || String(raw).trim() === '') continue;
    if (normalizedAliases.has(normalize(key))) return String(raw);
  }
  return undefined;
}

export function readNumber(row: DataRow, aliases: string[]): number | null {
  const raw = readValue(row, aliases);
  if (!raw) return null;
  const parsed = Number(raw.replaceAll(',', ''));
  return Number.isFinite(parsed) ? parsed : null;
}

export function parseDateValue(raw?: string): Date | null {
  const text = raw?.trim();
  if (!text || ['0', '00000000', '0000-00-00'].includes(text)) return null;
  function date(year: number, month: number, day: number): Date | null {
    if (year < 1000 || month < 1 || month > 12 || day < 1 || day > 31) return null;
    const value = new Date(Date.UTC(year, month - 1, day));
    return value.getUTCFullYear() === year && value.getUTCMonth() === month - 1 && value.getUTCDate() === day ? value : null;
  }
  if (/^\d{8}$/.test(text)) {
    // Daily files use YYYYMMDD; retained legacy files may use MMDDYYYY.
    const ymd = date(Number(text.slice(0, 4)), Number(text.slice(4, 6)), Number(text.slice(6, 8)));
    return ymd ?? date(Number(text.slice(4, 8)), Number(text.slice(0, 2)), Number(text.slice(2, 4)));
  }
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})(.*)$/);
  if (iso) {
    const day = date(Number(iso[1]), Number(iso[2]), Number(iso[3]));
    if (!day || !iso[4]) return day;
    if (!/^T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?$/.test(iso[4])) return null;
    const value = new Date(/[Zz]|[+-]\d{2}:\d{2}$/.test(iso[4]) ? text : `${text}Z`);
    return Number.isNaN(value.valueOf()) ? null : value;
  }
  const us = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (us) return date(Number(us[3]), Number(us[1]), Number(us[2]));
  const named = text.match(/^(\d{1,2})-([A-Za-z]{3})-(\d{2}|\d{4})$/);
  if (named) {
    let year = Number(named[3]);
    if (named[3].length === 2) year += year <= 68 ? 2000 : 1900;
    return date(year, ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'].indexOf(named[2].toUpperCase()) + 1, Number(named[1]));
  }
  return null;
}

export function formatDateValue(raw?: string): string {
  return parseDateValue(raw)?.toLocaleDateString(undefined, { timeZone: 'UTC' }) ?? '—';
}

export function censusStatusLabel(raw?: string): string {
  const code = raw?.trim().toUpperCase();
  return ({ A: 'Active', I: 'Inactive', P: 'Pending' } as Record<string, string>)[code ?? ''] ?? `Unknown${code ? ` (${code})` : ''}`;
}

export function driverReportDetail(date?: string, status?: string): string {
  return `Company Census · MCS-150 ${formatDateValue(date)} · ${censusStatusLabel(status)} registration`;
}

export function mileageYearLabel(raw?: string): string {
  return raw && /^\d{4}$/.test(raw) && Number(raw) >= 1900 && Number(raw) <= new Date().getUTCFullYear()
    ? raw : 'Year unavailable';
}

export function censusReviewNotes(reportDate?: string, status?: string, now = new Date()): string[] {
  const notes: string[] = [];
  if (status?.trim().toUpperCase() === 'I') notes.push('This USDOT registration is inactive. Reported fleet and driver counts do not establish current operating exposure.');
  const date = parseDateValue(reportDate);
  if (!date) notes.push('The MCS-150 report date is unavailable; exposure freshness cannot be verified.');
  else if (date > now) notes.push('The MCS-150 report date is in the future; verify the source record before relying on exposure.');
  else {
    const cutoff = new Date(now); cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 2);
    if (date < cutoff) notes.push(`The MCS-150 report is more than two years old (${formatDateValue(reportDate)}). These are source-reported figures, not verified current counts.`);
  }
  return notes;
}

export async function fetchSourceJson(url: string, init: RequestInit = {}, timeoutMs = REQUEST_TIMEOUT_MS): Promise<unknown> {
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { ...init, signal: controller.signal });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw new Error(`Request timed out after ${Math.round(timeoutMs / 1000)}s`);
    }
    throw cause;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export async function loadSchemaRegistry(): Promise<SchemaRegistry> {
  if (!schemaPromise) {
    schemaPromise = fetchSourceJson(`${import.meta.env.BASE_URL}data/source-schemas.json`, { cache: 'no-store' })
      .then(payload => {
        if (!payload || typeof payload !== 'object' || !Array.isArray((payload as SchemaRegistry).sources)) throw new Error('Invalid schema registry');
        return payload as SchemaRegistry;
      })
      .catch((error) => {
        schemaPromise = null;
        throw error;
      });
  }
  return schemaPromise;
}

export function sourceSchema(registry: SchemaRegistry, sourceId: string): SourceSchema {
  const schema = registry.sources.find((source) => source.id === sourceId);
  if (!schema) throw new Error(`No schema registered for ${sourceId}`);
  return schema;
}

export function findColumn(schema: SourceSchema, aliases: string[]): SchemaColumn | undefined {
  const normalizedAliases = new Set(aliases.map(normalize));
  return schema.columns.find((column) =>
    normalizedAliases.has(normalize(column.name)) || normalizedAliases.has(normalize(column.field_name)),
  );
}

function literal(column: SchemaColumn, value: string | number): string {
  if (column.data_type === 'number') {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) throw new Error(`Expected numeric value for ${column.field_name}`);
    return String(numeric);
  }
  return `'${String(value).replaceAll("'", "''")}'`;
}

async function fetchRows(sourceId: string, params: URLSearchParams): Promise<DataRow[]> {
  let payload: unknown;
  try {
    payload = await fetchSourceJson(`${DATAHUB}/${sourceId}.json?${params.toString()}`, {
      headers: { Accept: 'application/json' },
    });
  } catch (cause) {
    const message = cause instanceof Error ? cause.message : String(cause);
    throw new Error(`${sourceId} request failed: ${message}`);
  }
  if (!Array.isArray(payload)) throw new Error(`${sourceId} returned a non-array payload`);
  return payload as DataRow[];
}

async function countWhere(sourceId: string, where: string): Promise<number | null> {
  const params = new URLSearchParams({ '$select': 'count(*) as count', '$where': where });
  try {
    const rows = await fetchRows(sourceId, params);
    const raw = rows[0]?.count;
    if (raw === null || raw === undefined || !/^\d+$/.test(String(raw))) return null;
    const parsed = Number(raw);
    return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : null;
  } catch {
    return null;
  }
}

// Bounded paging with a stable order and one-row lookahead. A cap is never a total.
async function fetchWindow(sourceId: string, where: string, limit: number, order = ':id'): Promise<{ rows: DataRow[]; truncated: boolean }> {
  if (!Number.isSafeInteger(limit) || limit < 1) throw new Error('Row limit must be a positive integer');
  const rows: DataRow[] = [];
  while (rows.length <= limit) {
    const pageSize = Math.min(1000, limit + 1 - rows.length);
    const params = new URLSearchParams({ '$where': where, '$limit': String(pageSize), '$offset': String(rows.length), '$order': order });
    const page = await fetchRows(sourceId, params);
    rows.push(...page);
    if (page.length < pageSize) break;
  }
  return { rows: rows.slice(0, limit), truncated: rows.length > limit };
}

export async function queryByDot(
  registry: SchemaRegistry,
  sourceId: string,
  dotNumber: string,
  options: { limit?: number; orderAliases?: string[]; includeTotal?: boolean; eventWindow?: EventWindow } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  const dotColumn = findColumn(schema, USDOT_ALIASES);
  if (!dotColumn?.field_name) throw new Error(`${sourceId} has no registered USDOT field`);

  const legacyDotSources = new Set(['6eyk-hxee','qh9u-swkp','9mw4-x3tu','2emp-mxtb','6sqe-dvqs','96tg-4mhf','sa6p-acbp']);
  if (!/^[1-9][0-9]*$/.test(dotNumber)) throw new Error('Positive USDOT required');
  const legacy = legacyDotSources.has(sourceId);
  const values = [...new Set([dotNumber, dotNumber.padStart(8,'0')])];
  let where = legacy ? `${dotColumn.field_name} in (${values.map(value => literal(dotColumn,value)).join(',')})` : `${dotColumn.field_name}=${literal(dotColumn, dotNumber)}`;
  const eventWindow = options.eventWindow && validateEventWindow(options.eventWindow);
  if (eventWindow) {
    const field = DAILY_DATE_FIELDS[sourceId];
    const column = field && findColumn(schema,[field]);
    if (!column || column.field_name !== field || column.data_type !== 'text') throw new Error('No verified date-window mapping for this source.');
    where += ` AND ${field} between '${eventWindow.start.replaceAll('-','')}' and '${eventWindow.end.replaceAll('-','')}'`;
  }
  const limit = options.limit ?? 500;
  const orderColumn = options.orderAliases ? findColumn(schema, options.orderAliases) : undefined;
  const [window, reportedTotal] = await Promise.all([
    fetchWindow(sourceId, where, limit, orderColumn?.field_name ? `${orderColumn.field_name} DESC, :id` : ':id'),
    options.includeTotal ? countWhere(sourceId, where) : Promise.resolve(null),
  ]);
  const { rows } = window;
  if (legacy && rows.some(row => { const raw=readValue(row,USDOT_ALIASES) ?? ''; return !/^[0-9]+$/.test(raw) || raw.replace(/^0+/,'') !== dotNumber; })) throw new Error('Legacy response contains an unrelated carrier record.');
  if (eventWindow && rows.some(row => {
    const raw = readValue(row,[DAILY_DATE_FIELDS[sourceId]]) ?? '';
    const date = parseDateValue(raw)?.toISOString().slice(0,10);
    return !/^\d{8}$/.test(raw) || !date || date < eventWindow.start || date > eventWindow.end || readValue(row,USDOT_ALIASES) !== dotNumber;
  })) throw new Error('Date-window response contains an invalid date or unrelated carrier record.');
  // A separately queried count cannot override rows (including the lookahead) already observed.
  const total = reportedTotal !== null && reportedTotal >= rows.length + (window.truncated ? 1 : 0) ? reportedTotal : null;
  return {
    sourceId,
    rows,
    total,
    truncated: window.truncated || (total !== null && rows.length < total),
    scope: eventWindow ? 'carrier_date_window' : 'carrier',
    ...(eventWindow ? { eventWindow } : {}),
    acquiredAt: new Date().toISOString(),
  };
}

function chunks<T>(items: T[], size: number): T[][] {
  const output: T[][] = [];
  for (let index = 0; index < items.length; index += size) output.push(items.slice(index, index + size));
  return output;
}

export async function queryByInspectionIds(
  registry: SchemaRegistry,
  sourceId: string,
  inspectionIds: string[],
  options: { limitPerChunk?: number; maxInspectionIds?: number; idsPerChunk?: number } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  const inspectionColumn = findColumn(schema, INSPECTION_ID_ALIASES);
  if (!inspectionColumn?.field_name) throw new Error(`${sourceId} has no registered inspection ID field`);

  const allIds = [...new Set(inspectionIds.filter(Boolean))];
  const unique = allIds.slice(0, options.maxInspectionIds ?? 500);
  if (!unique.length) return { sourceId, rows: [], total: 0, truncated: false, scope: 'loaded_inspections' };

  const limitPerChunk = options.limitPerChunk ?? 5000;
  const batches = chunks(unique, options.idsPerChunk ?? 100);
  const responses = await Promise.all(
    batches.map(async (batch) => {
      const values = batch.map((id) => literal(inspectionColumn, id)).join(',');
      const where = `${inspectionColumn.field_name} in (${values})`;
      return fetchWindow(sourceId, where, limitPerChunk);
    }),
  );
  const rows = responses.flatMap((response) => response.rows);
  const truncated = unique.length < allIds.length || responses.some((batch) => batch.truncated);
  return {
    sourceId,
    rows,
    total: truncated ? null : rows.length,
    truncated,
    scope: 'loaded_inspections',
    acquiredAt: new Date().toISOString(),
  };
}

export async function queryByDocketNumbers(
  registry: SchemaRegistry,
  sourceId: string,
  docketNumbers: string[],
  options: { limitPerChunk?: number; maxDocketNumbers?: number; idsPerChunk?: number } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  const docketColumn = findColumn(schema, DOCKET_ALIASES);
  if (!docketColumn?.field_name) throw new Error(`${sourceId} has no registered docket-number field`);

  const allDockets = [...new Set(docketNumbers.filter(Boolean))];
  const unique = allDockets.slice(0, options.maxDocketNumbers ?? 100);
  if (!unique.length) return { sourceId, rows: [], total: 0, truncated: false, scope: 'dockets' };

  const limitPerChunk = options.limitPerChunk ?? 2000;
  const batches = chunks(unique, options.idsPerChunk ?? 50);
  const responses = await Promise.all(
    batches.map(async (batch) => {
      const values = batch.map((id) => literal(docketColumn, id)).join(',');
      const where = `${docketColumn.field_name} in (${values})`;
      return fetchWindow(sourceId, where, limitPerChunk);
    }),
  );
  const rows = responses.flatMap((response) => response.rows);
  const truncated = unique.length < allDockets.length || responses.some((batch) => batch.truncated);
  return {
    sourceId,
    rows,
    total: truncated ? null : rows.length,
    truncated,
    scope: 'dockets',
    acquiredAt: new Date().toISOString(),
  };
}

export async function queryByDotOrInspectionIds(
  registry: SchemaRegistry,
  sourceId: string,
  dotNumber: string,
  inspectionIds: string[],
  options: { limit?: number; maxInspectionIds?: number } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  // Child evidence uses the same loaded parent set, even if a future schema adds USDOT.
  const inspectionColumn = findColumn(schema, INSPECTION_ID_ALIASES);
  if (!inspectionColumn?.field_name) return queryByDot(registry, sourceId, dotNumber, { limit: options.limit ?? 2500 });
  return queryByInspectionIds(registry, sourceId, inspectionIds, {
    maxInspectionIds: options.maxInspectionIds ?? 500,
    limitPerChunk: options.limit ?? 5000,
  });
}

export function inspectionId(row: DataRow): string | undefined {
  return readValue(row, INSPECTION_ID_ALIASES);
}

export function schemaLabel(registry: SchemaRegistry, sourceId: string, fieldName: string): string {
  try {
    const schema = sourceSchema(registry, sourceId);
    const column = schema.columns.find((candidate) => candidate.field_name === fieldName);
    return column?.name ?? fieldName;
  } catch {
    return fieldName;
  }
}
