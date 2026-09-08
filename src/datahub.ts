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
};

const DATAHUB = 'https://data.transportation.gov/resource';
const USDOT_ALIASES = ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM', 'USDOT_NO', 'DOT_NO', 'US_DOT_NUMBER'];
const INSPECTION_ID_ALIASES = ['INSPECTION_ID', 'INSP_ID'];

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
  if (!raw) return null;
  const direct = new Date(raw);
  if (!Number.isNaN(direct.valueOf())) return direct;
  const compact = raw.match(/^(\d{2})(\d{2})(\d{4})$/);
  if (compact) {
    const [, mm, dd, yyyy] = compact;
    const parsed = new Date(`${yyyy}-${mm}-${dd}T00:00:00Z`);
    return Number.isNaN(parsed.valueOf()) ? null : parsed;
  }
  return null;
}

export async function loadSchemaRegistry(): Promise<SchemaRegistry> {
  if (!schemaPromise) {
    schemaPromise = fetch(`${import.meta.env.BASE_URL}data/source-schemas.json`, { cache: 'no-store' })
      .then((response) => {
        if (!response.ok) throw new Error(`Schema registry returned HTTP ${response.status}`);
        return response.json() as Promise<SchemaRegistry>;
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
  const response = await fetch(`${DATAHUB}/${sourceId}.json?${params.toString()}`);
  if (!response.ok) throw new Error(`${sourceId} returned HTTP ${response.status}`);
  const payload = await response.json();
  if (!Array.isArray(payload)) throw new Error(`${sourceId} returned a non-array payload`);
  return payload as DataRow[];
}

async function countWhere(sourceId: string, where: string): Promise<number | null> {
  const params = new URLSearchParams({ '$select': 'count(*) as count', '$where': where });
  try {
    const rows = await fetchRows(sourceId, params);
    const raw = rows[0]?.count;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export async function queryByDot(
  registry: SchemaRegistry,
  sourceId: string,
  dotNumber: string,
  options: { limit?: number; orderAliases?: string[] } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  const dotColumn = findColumn(schema, USDOT_ALIASES);
  if (!dotColumn?.field_name) throw new Error(`${sourceId} has no registered USDOT field`);

  const where = `${dotColumn.field_name}=${literal(dotColumn, dotNumber)}`;
  const limit = options.limit ?? 500;
  const params = new URLSearchParams({ '$where': where, '$limit': String(limit) });
  const orderColumn = options.orderAliases ? findColumn(schema, options.orderAliases) : undefined;
  if (orderColumn?.field_name) params.set('$order', `${orderColumn.field_name} DESC`);

  const [rows, total] = await Promise.all([fetchRows(sourceId, params), countWhere(sourceId, where)]);
  return { sourceId, rows, total, truncated: total !== null ? rows.length < total : rows.length >= limit };
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
  options: { limitPerChunk?: number; maxInspectionIds?: number } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  const inspectionColumn = findColumn(schema, INSPECTION_ID_ALIASES);
  if (!inspectionColumn?.field_name) throw new Error(`${sourceId} has no registered inspection ID field`);

  const unique = [...new Set(inspectionIds.filter(Boolean))].slice(0, options.maxInspectionIds ?? 500);
  if (!unique.length) return { sourceId, rows: [], total: 0, truncated: false };

  const limitPerChunk = options.limitPerChunk ?? 5000;
  const batches = chunks(unique, 35);
  const responses = await Promise.all(
    batches.map(async (batch) => {
      const values = batch.map((id) => literal(inspectionColumn, id)).join(',');
      const where = `${inspectionColumn.field_name} in (${values})`;
      const params = new URLSearchParams({ '$where': where, '$limit': String(limitPerChunk) });
      return fetchRows(sourceId, params);
    }),
  );
  const rows = responses.flat();
  return { sourceId, rows, total: rows.length, truncated: responses.some((batch) => batch.length >= limitPerChunk) };
}

export async function queryByDotOrInspectionIds(
  registry: SchemaRegistry,
  sourceId: string,
  dotNumber: string,
  inspectionIds: string[],
  options: { limit?: number; maxInspectionIds?: number } = {},
): Promise<DataSlice> {
  const schema = sourceSchema(registry, sourceId);
  const dotColumn = findColumn(schema, USDOT_ALIASES);
  if (dotColumn?.field_name) return queryByDot(registry, sourceId, dotNumber, { limit: options.limit ?? 2500 });
  return queryByInspectionIds(registry, sourceId, inspectionIds, {
    maxInspectionIds: options.maxInspectionIds ?? 500,
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
