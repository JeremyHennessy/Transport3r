import { DataRow, parseDateValue, readNumber, readValue } from './datahub';
import type { CarrierEvidence } from './carrierEvidence';

// Descriptive source normalization only. None of these states certifies legal authority or insurance coverage.
export const EVIDENCE_NORMALIZATION_VERSION = 'FMCSA_EVIDENCE_20260908_2';
export const MOTUS_COVERAGE_UNIT_STATUS = 'UNRESOLVED';
export const MOTUS_COVERAGE_UNIT_NOTE = 'Limits show raw MAX_COV_AMOUNT values. FMCSA metadata describes thousands of dollars, but live-value scale is inconsistent with that description; no dollar conversion is applied. Underlying limits are not substituted for maximum amounts.';

export function motusMaximumCoverageLabel(row: DataRow): string {
  // Metadata says thousands, while common live values are 750000 and 1000000.
  // Preserve the source amount pending authoritative reconciliation; never guess a scale.
  const amount = readNumber(row, ['MAX_COV_AMOUNT', 'MAX_COVERAGE_AMOUNT']);
  if (amount === null || amount < 0) return '—';
  return `${amount.toLocaleString('en-US', { maximumFractionDigits: 20 })} (source amount)`;
}
export type OrderState = 'RESCINDED' | 'ISSUED_NO_RESCISSION_RECORDED' | 'RESCISSION_SCHEDULED' | 'FUTURE_ISSUE' | 'UNKNOWN';
export function newEntrantOrderState(row: DataRow, asOf: string): OrderState {
  const at = parseDateValue(asOf);
  const issued = parseDateValue(readValue(row, ['OOS_DATE']));
  const rawRescission = readValue(row, ['RESCIND_DATE', 'OOS_RESCIND_DATE']);
  const rescinded = parseDateValue(rawRescission);
  if (!at || !issued || (rawRescission && !rescinded) || (rescinded && rescinded < issued)) return 'UNKNOWN';
  if (issued > at) return 'FUTURE_ISSUE';
  if (rescinded) return rescinded <= at ? 'RESCINDED' : 'RESCISSION_SCHEDULED';
  // STATUS is the USDOT entity status, not an OOS-order lifecycle field (FMCSA dictionary Rev 3).
  return 'ISSUED_NO_RESCISSION_RECORDED';
}

export function orderSummary(evidence: CarrierEvidence): { text: string; review: string | null } {
  const slice = evidence.slices.newEntrantOos;
  if (!slice || evidence.errors.newEntrantOos) return { text: 'Order evidence unavailable; current effect is unknown.', review: null };
  const states = slice.rows.map((row) => newEntrantOrderState(row, evidence.loadedAt));
  const count = (state: OrderState) => states.filter((value) => value === state).length;
  const issued = count('ISSUED_NO_RESCISSION_RECORDED');
  const scheduled = count('RESCISSION_SCHEDULED');
  const unknown = count('UNKNOWN') + count('FUTURE_ISSUE');
  const text = `${count('RESCINDED')} rescinded · ${issued} issued without recorded rescission · ${scheduled} future rescission dates · ${unknown} unresolved${slice.truncated ? ' (partial history)' : ''}. USDOT status does not establish order effect or authority.`;
  const review = issued || scheduled || unknown
    ? `New Entrant order evidence needs review: ${issued} without recorded rescission, ${scheduled} with future rescission dates, ${unknown} unresolved. Verify current effect with FMCSA.`
    : null;
  return { text, review };
}

export type FilingReason = 'CANCELLED' | 'REPLACED' | 'NAME_CHANGE' | 'TRANSFERRED' | 'UNKNOWN';
export function filingHistoryEvent(row: DataRow, asOf: string): { reason: FilingReason; timing: 'EFFECTIVE' | 'SCHEDULED' | 'UNKNOWN' } {
  const reasons: Record<string, FilingReason> = { cancelled: 'CANCELLED', replaced: 'REPLACED', 'name change': 'NAME_CHANGE', transferred: 'TRANSFERRED' };
  const reason = reasons[(readValue(row, ['FILING_STATUS_REASON']) ?? '').trim().toLowerCase()] ?? 'UNKNOWN';
  const effective = parseDateValue(readValue(row, ['CANCL_EFFECTIVE_DATE']));
  const at = parseDateValue(asOf);
  return { reason, timing: effective && at ? effective <= at ? 'EFFECTIVE' : 'SCHEDULED' : 'UNKNOWN' };
}

export function filingChangeSummary(evidence: CarrierEvidence): string {
  const slice = evidence.slices.motusInsuranceHistoryDelta;
  if (!slice || evidence.errors.motusInsuranceHistoryDelta) return 'History-change evidence unavailable.';
  const events = slice.rows.map((row) => filingHistoryEvent(row, evidence.loadedAt));
  const count = (reason: FilingReason) => events.filter((event) => event.reason === reason).length;
  return `Loaded history changes: ${count('CANCELLED')} cancelled, ${count('REPLACED')} replaced, ${count('NAME_CHANGE')} name changes, ${count('TRANSFERRED')} transferred, ${count('UNKNOWN')} unknown reasons; ${events.filter((event) => event.timing === 'SCHEDULED').length} future effective dates and ${events.filter((event) => event.timing === 'UNKNOWN').length} unknown dates${slice.truncated ? ' (partial feed)' : ''}. These records describe the previous filing and do not establish a coverage gap or replacement coverage.`;
}
