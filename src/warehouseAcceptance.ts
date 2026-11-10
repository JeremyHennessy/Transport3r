import {validateIntegrity, type IntegrityReport} from './integrityModel';

/** Carrier data, audit and service health must describe one immutable installation. */
export type WarehouseAuditEvidence = {
  cut_id: string; cut_available_at: string; warehouse_sha256: string;
  sources: Array<{source_id: string; source_sha256: string;
    source_available_at: string; source_rows_updated_at: number; carrier_rows: number}>;
  completeness_receipt: {mapping_totals: {resolved: number; identified_only: number; unresolved: number}};
};

export function verifyWarehouseAudit(evidence: WarehouseAuditEvidence, reportValue: unknown,
  healthValue: unknown): IntegrityReport {
  const report = validateIntegrity(reportValue, healthValue);
  const require = (condition: boolean, reason: string) => {
    if (!condition) throw new Error(`Warehouse audit reconciliation failed: ${reason}`);
  };
  require(report.cut_id === evidence.cut_id && report.cut_available_at === evidence.cut_available_at &&
    report.warehouse_sha256 === evidence.warehouse_sha256, 'carrier response belongs to another release');
  const audits = new Map(report.sources.map(source => [source.source, source]));
  const totals = evidence.completeness_receipt.mapping_totals;
  for (const [key, status] of [['resolved','RESOLVED'],['identified_only','IDENTIFIED_ONLY'],['unresolved','UNRESOLVED']] as const) {
    const actual = report.sources.reduce((sum, source) => sum + (source.mapping_status[status] ?? 0), 0);
    require(Number.isSafeInteger(actual) && actual === totals[key], `nationwide ${key} total differs`);
  }
  require(evidence.sources.length === audits.size, 'source coverage differs');
  const seen = new Set<string>();
  for (const source of evidence.sources) {
    const audit = audits.get(source.source_id);
    require(!!audit && !seen.has(source.source_id), 'unknown or repeated carrier source');
    seen.add(source.source_id);
    if (!audit) throw new Error('Missing source audit');
    require(audit.sha256 === source.source_sha256 && audit.available_at === source.source_available_at &&
      audit.rows_updated_at === source.source_rows_updated_at, `source lineage differs: ${source.source_id}`);
    require(Number.isSafeInteger(source.carrier_rows) && source.carrier_rows >= 0 &&
      source.carrier_rows <= (audit.mapping_status.RESOLVED ?? 0), `resolved carrier count exceeds audited source: ${source.source_id}`);
  }
  return report;
}

/** Bound audit bytes during transfer, before JSON allocation. */
async function boundedJson(response: Response): Promise<unknown> {
  const maximum = 2 * 1024 * 1024;
  const declared = response.headers.get('content-length');
  if (declared !== null && (!/^[0-9]+$/.test(declared) || !Number.isSafeInteger(Number(declared)) || Number(declared) > maximum)) {
    await response.body?.cancel();
    throw new Error('Warehouse audit response exceeds its size limit');
  }
  if (!response.body) throw new Error('Warehouse audit response is empty');
  const reader = response.body.getReader(), decoder = new TextDecoder('utf-8', {fatal: true});
  let bytes = 0, text = '';
  try {
    for (;;) {
      const chunk = await reader.read();
      if (chunk.done) break;
      bytes += chunk.value.byteLength;
      if (bytes > maximum) {
        await reader.cancel();
        throw new Error('Warehouse audit response exceeds its size limit');
      }
      text += decoder.decode(chunk.value, {stream: true});
    }
    return JSON.parse(text + decoder.decode());
  } finally { reader.releaseLock(); }
}

/** A failed audit never falls back to an unaudited success. */
export async function reconcileWarehouseAudit(base: string, evidence: WarehouseAuditEvidence,
  signal: AbortSignal): Promise<IntegrityReport> {
  if (signal.aborted) throw new DOMException('Warehouse audit request cancelled', 'AbortError');
  const controller = new AbortController(), cancel = () => controller.abort();
  signal.addEventListener('abort', cancel, {once: true});
  const deadline = setTimeout(cancel, 15000);
  async function load(path: string): Promise<unknown> {
    const response = await fetch(`${base}${path}`, {signal: controller.signal, credentials: 'omit',
      cache: 'no-store', headers: {Accept: 'application/json'}});
    if (!response.ok) throw new Error(`Warehouse audit unavailable: HTTP ${response.status}`);
    return boundedJson(response);
  }
  try {
    const [health, report] = await Promise.all([load('/healthz'), load('/v1/integrity')]);
    return verifyWarehouseAudit(evidence, report, health);
  } finally {
    clearTimeout(deadline);
    signal.removeEventListener('abort', cancel);
    controller.abort();
  }
}
