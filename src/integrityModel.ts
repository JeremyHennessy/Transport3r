import catalog from '../data/fmcsa_sources.json';

export const GLOBAL_CHECKS = ['source_coverage','receipt_scope','aggregate_rows','audited_sources','census_carriers','mapping_totals','immutable_file'] as const;
export const SOURCE_CHECKS = ['source_counts','raw_identity','mapping_cardinality','joined_rows','mapping_status','mapping_reasons','provenance','exact_duplicates','identity_mapping'] as const;
const sourceIds = new Set(catalog.map(source => source.id));
const countFields = ['published','acquired','warehouse','actual_raw','actual_mapping','actual_joined','distinct_mapping_rows'] as const;
const statuses = ['RESOLVED','IDENTIFIED_ONLY','UNRESOLVED'] as const;
const hash = /^[a-f0-9]{64}$/;

type Counts = Record<typeof countFields[number], number>;
export type SourceAudit = Counts & {
  source: string; sha256: string; available_at: string; rows_updated_at: number;
  missing_mapping_rows: number; orphan_mapping_rows: number; identity_mapping_disagreements: number;
  mapping_status: Record<string,number>; exact_duplicate_rows: number; distinct_source_rows: number;
  checks: Record<string,boolean>;
};
export type IntegrityReport = {
  schema_version: 'TRANSPORT3R_WAREHOUSE_AUDIT_2'; status: 'PASS'; release_ready: true;
  audited_at: string; warehouse_sha256: string; identity_contract: string; scope: string;
  cut_id: string; cut_available_at: string; source_count: number; raw_rows: number;
  receipt_rows: number; census_carriers: number; deep_exact_duplicates_checked: true;
  duplicate_rule: string; checks: Record<string,boolean>; sources: SourceAudit[]; failures: [];
};
export type ReleaseInfo = {commit:string;builtAt:string;metadataAt:string|null;sources:number;fields:number};

function ensure(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(`Integrity verification failed: ${message}`);
}
function object(value: unknown): Record<string,unknown> {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value), 'expected an object');
  return value as Record<string,unknown>;
}
function integer(value: unknown): value is number {return typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;}
function date(value: unknown): value is string {
  if (typeof value !== 'string') return false;
  const parts = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.exec(value);
  if (!parts) return false;
  const [year,month,day,hour,minute,second] = parts.slice(1).map(Number);
  const days = [31,year%4===0&&(year%100!==0||year%400===0)?29:28,31,30,31,30,31,31,30,31,30,31];
  return year > 0 && month >= 1 && month <= 12 && day >= 1 && day <= days[month-1] && hour < 24 && minute < 60 && second < 60 && Number.isFinite(Date.parse(value));
}
function checks(value: unknown, names: readonly string[]): Record<string,boolean> {
  const row = object(value);
  ensure(Object.keys(row).length === names.length && names.every(name => row[name] === true), 'missing or failed checks');
  return Object.fromEntries(names.map(name => [name,true]));
}

export function validateIntegrity(value: unknown, healthValue: unknown, now = Date.now()): IntegrityReport {
  const report = object(value), health = object(healthValue);
  ensure(report.schema_version === 'TRANSPORT3R_WAREHOUSE_AUDIT_2' && report.status === 'PASS' && report.release_ready === true, 'audit is not release-ready');
  ensure(report.deep_exact_duplicates_checked === true && report.duplicate_rule === 'EXACT_ORIGINAL_SOURCE_COLUMNS_V2', 'duplicates and identities were not audited');
  ensure(Array.isArray(report.failures) && report.failures.length === 0, 'audit has failures');
  ensure(report.identity_contract === 'FMCSA_CARRIER_IDENTITY_1' && report.scope === 'ALL_PUBLISHED_ROWS_ALL_REGISTERED_SOURCES', 'wrong evidence scope');
  ensure(typeof report.warehouse_sha256 === 'string' && hash.test(report.warehouse_sha256), 'missing warehouse SHA-256');
  ensure(typeof report.cut_id === 'string' && report.cut_id.trim().length > 0 && report.cut_id.length <= 250, 'invalid cut identity');
  ensure(date(report.cut_available_at) && date(report.audited_at), 'invalid cut or audit timestamp');
  ensure(Date.parse(report.cut_available_at) <= Date.parse(report.audited_at) && Date.parse(report.audited_at) <= now + 300000, 'audit timestamp is outside its cut');
  ensure(health.status === 'ok' && health.independent_audit === 'PASS' && health.warehouse_sha256 === report.warehouse_sha256 &&
    health.cut_id === report.cut_id && health.cut_available_at === report.cut_available_at && health.sources === sourceIds.size &&
    health.identity_contract === report.identity_contract, 'health and audit describe different installations');
  const globalChecks = checks(report.checks, GLOBAL_CHECKS);
  ensure(Array.isArray(report.sources) && report.sources.length === sourceIds.size && report.source_count === sourceIds.size, 'incomplete source coverage');
  const seen = new Set<string>();
  const sources = report.sources.map(value => {
    const row = object(value);
    ensure(typeof row.source === 'string' && sourceIds.has(row.source) && !seen.has(row.source), 'unknown or duplicate source');
    seen.add(row.source);
    ensure(typeof row.sha256 === 'string' && hash.test(row.sha256) && date(row.available_at) && integer(row.rows_updated_at), 'invalid source provenance');
    ensure(Date.parse(row.available_at) <= Date.parse(report.cut_available_at as string), 'source retrieval occurs after cut availability');
    ensure(countFields.every(field => integer(row[field]) && row[field] === row.actual_raw), 'source counts disagree');
    ensure(row.missing_mapping_rows === 0 && row.orphan_mapping_rows === 0 && row.identity_mapping_disagreements === 0, 'identity or join discrepancies');
    const mapping = object(row.mapping_status);
    ensure(Object.keys(mapping).every(key => statuses.includes(key as typeof statuses[number])) && Object.values(mapping).every(integer), 'invalid mapping statuses');
    ensure(Object.values(mapping).reduce<number>((sum,value) => sum + (value as number),0) === row.actual_raw, 'mapping total disagrees');
    ensure(integer(row.exact_duplicate_rows) && integer(row.distinct_source_rows) && row.exact_duplicate_rows + row.distinct_source_rows === row.actual_raw, 'duplicate accounting disagrees');
    const selected = Object.fromEntries(countFields.map(key => [key,row[key]])) as Counts;
    return {...selected,source:row.source,sha256:row.sha256,available_at:row.available_at,rows_updated_at:row.rows_updated_at,
      missing_mapping_rows:0,orphan_mapping_rows:0,identity_mapping_disagreements:0,
      mapping_status:Object.fromEntries(Object.entries(mapping)) as Record<string,number>,
      exact_duplicate_rows:row.exact_duplicate_rows,distinct_source_rows:row.distinct_source_rows,
      checks:checks(row.checks,SOURCE_CHECKS)} satisfies SourceAudit;
  });
  const total = sources.reduce((sum,source) => sum + source.actual_raw,0);
  ensure(integer(total) && integer(report.raw_rows) && report.raw_rows === total && report.receipt_rows === total, 'aggregate row total disagrees');
  ensure(integer(report.census_carriers) && report.census_carriers <= (sources.find(s => s.source === 'az4n-8mr2')?.actual_raw ?? -1), 'invalid Census carrier count');
  return {schema_version:'TRANSPORT3R_WAREHOUSE_AUDIT_2',status:'PASS',release_ready:true,audited_at:report.audited_at,
    warehouse_sha256:report.warehouse_sha256,identity_contract:report.identity_contract as string,scope:report.scope as string,
    cut_id:report.cut_id,cut_available_at:report.cut_available_at,source_count:sources.length,raw_rows:total,receipt_rows:total,
    census_carriers:report.census_carriers,deep_exact_duplicates_checked:true,duplicate_rule:report.duplicate_rule as string,
    checks:globalChecks,sources,failures:[]};
}

export function validateRelease(value: unknown): ReleaseInfo {
  const release = object(value), metadata = object(release.source_metadata);
  ensure(release.schema_version === 1 && typeof release.commit === 'string' && /^[a-f0-9]{40}$/.test(release.commit) && date(release.built_at), 'invalid app release manifest');
  ensure(metadata.source_count === sourceIds.size && integer(metadata.field_count), 'release source registry mismatch');
  return {commit:release.commit,builtAt:release.built_at,metadataAt:date(metadata.health_generated_at)?metadata.health_generated_at:null,
    sources:sourceIds.size,fields:metadata.field_count};
}

export function evidenceApiBase(value: string): string | null {
  const raw = value.trim(); if (!raw) return null;
  const url = new URL(raw);
  const local = ['localhost','127.0.0.1','[::1]'].includes(url.hostname);
  ensure(!url.username && !url.password && !url.search && !url.hash && (url.protocol === 'https:' || (local && url.protocol === 'http:')), 'evidence API must use HTTPS (or explicit localhost) without credentials');
  return url.href.replace(/\/$/,'');
}

async function jsonResponse(response: Response): Promise<unknown> {
  if (!response.ok) throw new Error(`Evidence service returned HTTP ${response.status}. Totals remain unverified.`);
  const text = await response.text();
  if (text.length > 2 * 1024 * 1024) throw new Error('Integrity response exceeds its size limit');
  return JSON.parse(text);
}

export async function loadIntegrity(base: string, signal: AbortSignal): Promise<IntegrityReport> {
  const url = evidenceApiBase(base); if (!url) throw new Error('Evidence API is not configured');
  const requestSignal = AbortSignal.any([signal,AbortSignal.timeout(15000)]);
  const options: RequestInit = {signal:requestSignal,credentials:'omit',cache:'no-store',headers:{Accept:'application/json'}};
  const [health,report] = await Promise.all([
    fetch(`${url}/healthz`,options).then(jsonResponse),fetch(`${url}/v1/integrity`,options).then(jsonResponse),
  ]);
  return validateIntegrity(report,health);
}
