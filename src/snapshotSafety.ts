import {type CarrierEvidence, type EvidenceKey, SOURCE_IDS} from './carrierEvidence';
import {readValue, type DataRow} from './datahub';
import {DAILY_DATE_FIELDS, validateEventWindow, type EventWindow} from './eventWindow';
import {WINDOW_SOURCES, type SafetyWindowResult, type SafetyWindowSource} from './safetyWindow';

/** Only the documented daily YYYYMMDD encoding; do not guess MMDDYYYY. */
export function dailyCalendarDate(value: unknown): string | null {
  if (typeof value !== 'string' || !/^\d{8}$/.test(value)) return null;
  const iso = `${value.slice(0,4)}-${value.slice(4,6)}-${value.slice(6,8)}`;
  const time = Date.parse(iso);
  return Number.isFinite(time) && new Date(time).toISOString().slice(0,10) === iso ? iso : null;
}

export function dailyCarrierMatches(row: DataRow, dot: string): boolean {
  const raw = readValue(row, ['DOT_NUMBER', 'USDOT_NUMBER'])?.trim();
  return !!raw && /^\d+$/.test(raw) && raw.replace(/^0+/, '') === dot;
}

function snapshotIdentity(evidence: CarrierEvidence): NonNullable<SafetyWindowResult['provenance']> {
  const receipt = evidence.completenessReceipt;
  if (receipt?.backend === 'verified_nationwide_warehouse') {
    if (receipt.status !== 'VERIFIED' || evidence.completeAll !== true || !receipt.cutId ||
        !receipt.cutAvailableAt || !/T.*(?:Z|[+-]\d{2}:\d{2})$/.test(receipt.cutAvailableAt) ||
        !Number.isFinite(Date.parse(receipt.cutAvailableAt)) ||
        !/^[a-f0-9]{64}$/.test(receipt.warehouseSha256 ?? '') ||
        receipt.sourcesExpected !== 36 || receipt.sourcesReturned !== 36) {
      throw new Error('Report snapshot requires a complete accepted warehouse receipt.');
    }
    return {kind:'accepted_warehouse', cutId:receipt.cutId, cutAvailableAt:receipt.cutAvailableAt,
      warehouseSha256:receipt.warehouseSha256, windowExtendsBeyondCut:false};
  }
  return {kind:'retained_evidence', cutId:null, cutAvailableAt:null, warehouseSha256:null,
    windowExtendsBeyondCut:false};
}

/** Select from the exact retained rows. This function never requests live data. */
export function safetyWindowFromEvidence(evidence: CarrierEvidence, selected: EventWindow): SafetyWindowResult {
  if (!/^[1-9]\d*$/.test(evidence.dotNumber)) throw new Error('Invalid snapshot carrier identity.');
  const window = validateEventWindow(selected), provenance = snapshotIdentity(evidence);
  const cutDate = provenance.cutAvailableAt ? new Date(provenance.cutAvailableAt).toISOString().slice(0,10) : null;
  provenance.windowExtendsBeyondCut = !!cutDate && window.end > cutDate;
  const sources: SafetyWindowSource[] = WINDOW_SOURCES.map(source => {
    const key: EvidenceKey = source.id === SOURCE_IDS.inspections ? 'inspections' : 'crash';
    const retained = evidence.slices[key];
    const unavailable = evidence.errors[key] || (!retained ? 'Source not included in the retained evidence.' : undefined);
    if (unavailable || !retained) return {...source, error:unavailable};
    try {
      if (retained.sourceId !== source.id) throw new Error('Retained source identity does not match the requested family.');
      if (provenance.kind === 'accepted_warehouse') {
        let lineage: unknown;
        try { lineage = JSON.parse(retained.sourcePublication ?? ''); }
        catch { throw new Error('Accepted source snapshot lineage is missing.'); }
        if (!Array.isArray(lineage) || lineage.length !== 3 || lineage[0] !== provenance.cutId ||
            !/^[a-f0-9]{64}$/.test(String(lineage[1])) || !Number.isSafeInteger(lineage[2]) || lineage[2] < 0 ||
            retained.truncated || retained.total !== retained.rows.length) {
          throw new Error('Source cut, lineage or row completeness differs from the accepted snapshot.');
        }
      }
      const accounting = {inputRows:retained.rows.length, selectedRows:0, outsideWindow:0,
        missingDates:0, invalidDates:0, afterCutDates:0, rejectedIdentities:0};
      const rows = retained.rows.filter(row => {
        if (!dailyCarrierMatches(row, evidence.dotNumber)) { accounting.rejectedIdentities++; return false; }
        const raw = readValue(row, [DAILY_DATE_FIELDS[source.id]]);
        if (raw === undefined) { accounting.missingDates++; return false; }
        const day = dailyCalendarDate(raw);
        if (!day) { accounting.invalidDates++; return false; }
        if (cutDate && day > cutDate) { accounting.afterCutDates++; return false; }
        if (day < window.start || day > window.end) { accounting.outsideWindow++; return false; }
        accounting.selectedRows++; return true;
      });
      const incomplete = retained.truncated || retained.total === null || retained.total !== retained.rows.length ||
        accounting.missingDates > 0 || accounting.invalidDates > 0 || accounting.afterCutDates > 0 ||
        accounting.rejectedIdentities > 0 || provenance.windowExtendsBeyondCut;
      return {...source, sourcePublication:retained.sourcePublication, sourceAcquiredAt:retained.acquiredAt,
        accounting, slice:{...retained, rows, total:incomplete ? null : rows.length,
          truncated:incomplete, scope:'carrier_date_window' as const, eventWindow:window}};
    } catch (cause) {
      return {...source, error:cause instanceof Error ? cause.message : String(cause)};
    }
  });
  return {dot:evidence.dotNumber, window, acquiredAt:evidence.loadedAt, sources, provenance};
}

/** A warehouse report/export cannot silently substitute a newer live safety query. */
export function assertReportSnapshot(evidence: CarrierEvidence, actual: SafetyWindowResult): void {
  if (evidence.dotNumber !== actual.dot) throw new Error('Report window and carrier identity differ.');
  if (evidence.completenessReceipt?.backend !== 'verified_nationwide_warehouse') return;
  const expected = safetyWindowFromEvidence(evidence, actual.window);
  if (JSON.stringify(actual.provenance) !== JSON.stringify(expected.provenance) ||
      actual.acquiredAt !== expected.acquiredAt || actual.sources.length !== expected.sources.length) {
    throw new Error('Report safety window is not bound to the accepted evidence snapshot.');
  }
  const seen = new Set<string>();
  for (const source of actual.sources) {
    const match = expected.sources.find(value => value.id === source.id);
    if (!match || seen.has(source.id)) throw new Error('Report snapshot source coverage differs.');
    seen.add(source.id);
    if (source.error !== match.error || source.sourcePublication !== match.sourcePublication ||
        source.sourceAcquiredAt !== match.sourceAcquiredAt ||
        JSON.stringify(source.accounting) !== JSON.stringify(match.accounting) ||
        source.slice?.total !== match.slice?.total || source.slice?.truncated !== match.slice?.truncated ||
        source.slice?.sourceId !== match.slice?.sourceId ||
        source.slice?.sourcePublication !== match.slice?.sourcePublication ||
        source.slice?.acquiredAt !== match.slice?.acquiredAt ||
        source.slice?.scope !== match.slice?.scope ||
        JSON.stringify(source.slice?.eventWindow) !== JSON.stringify(match.slice?.eventWindow) ||
        source.slice?.rows.length !== match.slice?.rows.length ||
        (match.slice && !match.slice.rows.every((row,index) => row === source.slice?.rows[index] ||
          JSON.stringify(row) === JSON.stringify(source.slice?.rows[index])))) {
      throw new Error('Report source rows or lineage differ from the accepted snapshot.');
    }
  }
}

export function safetyProvenanceText(result: SafetyWindowResult): string {
  const proof = result.provenance;
  if (!proof) return `Separate live date-window acquisition: ${result.acquiredAt}.`;
  const boundary = proof.windowExtendsBeyondCut ? ' Selected dates extend beyond this cut; later observations are unavailable.' : '';
  return proof.kind === 'accepted_warehouse'
    ? `Accepted evidence cut ${proof.cutId}, available ${proof.cutAvailableAt}; warehouse SHA-256 ${proof.warehouseSha256}. Safety rows are selected from that same cut, without a live refetch.${boundary}`
    : `Filtered from retained carrier evidence acquired ${result.acquiredAt}; no additional live requests. Source vintages remain distinct; a common accepted warehouse cut is not established.`;
}
