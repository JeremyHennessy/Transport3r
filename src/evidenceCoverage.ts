import { evidenceKeys, SOURCE_IDS, type CarrierEvidence, type EvidenceKey } from './carrierEvidence';
import { censusReviewNotes, parseDateValue, readValue, type DataRow } from './datahub';

export type CoverageStatus = 'complete' | 'partial' | 'empty' | 'unavailable';
export const COVERAGE_LABELS: Record<CoverageStatus, string> = {
  complete: 'Request complete', partial: 'Partial window', empty: 'No rows returned', unavailable: 'Unavailable',
};
// Only explicit event/report fields are ranged. Metadata/change timestamps are never substituted.
const DATE_FIELDS: Partial<Record<EvidenceKey, string[]>> = {
  census: ['MCS150_DATE'], inspections: ['INSP_DATE', 'INSPECTION_DATE'],
  crash: ['CRASH_DATE', 'REPORT_DATE'], smsInspection: ['INSP_DATE'],
  smsViolation: ['INSP_DATE'], smsCrash: ['REPORT_DATE', 'CRASH_DATE'],
};

export function loadedDateRange(rows: DataRow[], aliases: string[]) {
  const dates: string[] = [];
  let missing = 0, invalid = 0, conflicting = 0;
  for (const row of rows) {
    const values = aliases.map(alias => readValue(row, [alias])).filter((v): v is string => v !== undefined);
    if (!values.length) { missing++; continue; }
    const parsed = values.map(value => parseDateValue(value)?.toISOString().slice(0, 10));
    if (parsed.some(value => !value)) { invalid++; continue; }
    if (new Set(parsed).size !== 1) { conflicting++; continue; }
    dates.push(parsed[0]!);
  }
  dates.sort();
  return { start: dates[0] ?? null, end: dates.at(-1) ?? null, valid: dates.length, missing, invalid, conflicting };
}

export function coverageRows(evidence: CarrierEvidence) {
  return evidenceKeys(evidence.mode).map(key => {
    const slice = evidence.slices[key], error = evidence.errors[key];
    const schema = evidence.registry.sources.find(source => source.id === SOURCE_IDS[key]);
    const status: CoverageStatus = error || !slice ? 'unavailable' : slice.truncated ? 'partial' : !slice.rows.length ? 'empty' : 'complete';
    const fields = DATE_FIELDS[key];
    const range = slice && !error && fields ? loadedDateRange(slice.rows, fields) : null;
    const count = !error && slice ? slice.total ?? (slice.truncated ? null : slice.rows.length) : null;
    return {
      key, sourceId: SOURCE_IDS[key], sourceName: schema?.name ?? key, status,
      loaded: !error && slice ? slice.rows.length : null, requestTotal: count,
      scope: slice?.scope ?? null, acquiredAt: !error ? slice?.acquiredAt ?? null : null,
      metadataUpdatedAt: schema?.rows_updated_at ?? null,
      metadataCapturedAt: evidence.registry.generated_at ?? null,
      dateFields: fields ?? [], range,
      reason: error ?? (!slice ? 'Source evidence was not returned.' : slice.truncated
        ? 'Bounded query or parent window; not complete carrier history.'
        : !slice.rows.length ? 'No rows in this request scope; not proof of no historical activity.'
        : 'Complete for this request scope; not a standardized risk window.'),
    };
  });
}

export function coverageReport(evidence: CarrierEvidence, census?: DataRow) {
  census ??= evidence.census ?? evidence.slices.census?.rows[0];
  return {
    version: 1, dotNumber: evidence.dotNumber, mode: evidence.mode, assembledAt: evidence.loadedAt,
    scope: 'Loaded source requests only. Metadata dates are a saved catalog cut, not live publication or historical availability dates. Sparse event dates do not establish missing records.',
    riskScore: null, riskReason: 'No numeric Transport3r risk model released.',
    exposure: census ? {
      reportDate: readValue(census, ['MCS150_DATE']) ?? null,
      registration: readValue(census, ['STATUS_CODE']) ?? null,
      drivers: readValue(census, ['TOTAL_DRIVERS']) ?? null,
      powerUnits: readValue(census, ['POWER_UNITS']) ?? null,
      mileageYear: readValue(census, ['MCS150_MILEAGE_YEAR']) ?? null,
      reviewNotes: censusReviewNotes(readValue(census, ['MCS150_DATE']), readValue(census, ['STATUS_CODE']), new Date(evidence.loadedAt)),
    } : null,
    sources: coverageRows(evidence),
  };
}
