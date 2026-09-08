import { CarrierEvidence } from './carrierEvidence';
import { DataRow, readNumber, readValue } from './datahub';
import {
  INSPECTION_MEASURE_BASICS,
  InspectionMeasureBasicKey,
  SMS_BASIC_RULES,
  SMS_RULESET,
  safetyEventGroup,
} from './smsRules';

export type SmsReplayStatus = 'MATCH' | 'CLOSE' | 'MISMATCH' | 'NO_OFFICIAL' | 'PARTIAL_DATA' | 'NO_DENOMINATOR';

export type SmsMeasureReplay = {
  ruleset: typeof SMS_RULESET.id;
  basic: InspectionMeasureBasicKey;
  label: string;
  numerator: number;
  denominator: number;
  calculatedMeasure: number | null;
  officialMeasure: number | null;
  delta: number | null;
  status: SmsReplayStatus;
  relevantInspections: number;
  violationInspections: number;
  safetyEventGroup: number | null;
  cappedInspections: number;
  truncatedInput: boolean;
};

function truthy(raw?: string): boolean {
  if (!raw) return false;
  return ['Y', 'YES', 'TRUE', 'T', '1'].includes(raw.trim().toUpperCase());
}

function numeric(raw: unknown): number {
  if (raw === null || raw === undefined || String(raw).trim() === '') return 0;
  const value = Number(String(raw).replaceAll(',', ''));
  return Number.isFinite(value) ? value : 0;
}

function inspectionKey(row: DataRow): string | undefined {
  return readValue(row, ['UNIQUE_ID', 'INSPECTION_ID', 'INSP_ID']);
}

function violationMatchesBasic(row: DataRow, basic: InspectionMeasureBasicKey): boolean {
  const description = (readValue(row, ['BASIC_DESC']) ?? '').toLowerCase();
  return SMS_BASIC_RULES[basic].violationBasicMatches.some((match) => description.includes(match));
}

function officialOutputRow(evidence: CarrierEvidence): DataRow | null {
  const candidates = [
    evidence.slices.smsABProperty?.rows ?? [],
    evidence.slices.smsCProperty?.rows ?? [],
    evidence.slices.smsABPass?.rows ?? [],
    evidence.slices.smsCPass?.rows ?? [],
  ];
  for (const rows of candidates) {
    if (rows.length) return rows[0];
  }
  return null;
}

function officialMeasure(evidence: CarrierEvidence, basic: InspectionMeasureBasicKey): number | null {
  const field = SMS_BASIC_RULES[basic].officialMeasureField;
  if (!field) return null;
  const row = officialOutputRow(evidence);
  if (!row) return null;
  const value = readNumber(row, [field]);
  return value === null ? null : value;
}

export function replayInspectionMeasure(
  inspections: DataRow[],
  violations: DataRow[],
  basic: InspectionMeasureBasicKey,
): Omit<SmsMeasureReplay, 'officialMeasure' | 'delta' | 'status' | 'truncatedInput'> {
  const rule = SMS_BASIC_RULES[basic];
  if (!rule.relevantInspectionField) throw new Error(`${basic} does not define a relevant-inspection field`);

  const relevant = inspections.filter((row) => truthy(readValue(row, [rule.relevantInspectionField!]))) ;
  const inspectionTimeWeights = new Map<string, number>();
  for (const row of relevant) {
    const key = inspectionKey(row);
    if (!key) continue;
    inspectionTimeWeights.set(key, numeric(readValue(row, ['TIME_WEIGHT'])));
  }

  const denominator = [...inspectionTimeWeights.values()].reduce((sum, weight) => sum + weight, 0);
  const violationSeverityByInspection = new Map<string, number>();
  const violationTimeWeightByInspection = new Map<string, number>();

  for (const row of violations) {
    if (!violationMatchesBasic(row, basic)) continue;
    const key = inspectionKey(row);
    if (!key) continue;

    const totalSeverity = readNumber(row, ['TOTAL_SEVERITY_WGHT']);
    const baseSeverity = numeric(readValue(row, ['SEVERITY_WEIGHT']));
    const oosWeight = basic === 'controlledSubstances' ? 0 : numeric(readValue(row, ['OOS_WEIGHT']));
    const severity = totalSeverity ?? (baseSeverity + oosWeight);
    violationSeverityByInspection.set(key, (violationSeverityByInspection.get(key) ?? 0) + severity);

    const rowTimeWeight = numeric(readValue(row, ['TIME_WEIGHT']));
    if (rowTimeWeight > 0) violationTimeWeightByInspection.set(key, rowTimeWeight);
  }

  let numerator = 0;
  let cappedInspections = 0;
  for (const [key, severitySum] of violationSeverityByInspection.entries()) {
    const cappedSeverity = Math.min(30, severitySum);
    if (severitySum > 30) cappedInspections += 1;
    const timeWeight = violationTimeWeightByInspection.get(key) ?? inspectionTimeWeights.get(key) ?? 0;
    numerator += cappedSeverity * timeWeight;
  }

  const calculatedMeasure = denominator > 0 ? numerator / denominator : null;
  return {
    ruleset: SMS_RULESET.id,
    basic,
    label: rule.label,
    numerator,
    denominator,
    calculatedMeasure,
    relevantInspections: inspectionTimeWeights.size,
    violationInspections: violationSeverityByInspection.size,
    safetyEventGroup: safetyEventGroup(basic, basic === 'controlledSubstances' ? violationSeverityByInspection.size : inspectionTimeWeights.size),
    cappedInspections,
  };
}

function compare(calculated: number | null, official: number | null, truncatedInput: boolean): Pick<SmsMeasureReplay, 'delta' | 'status'> {
  if (truncatedInput) return { delta: null, status: 'PARTIAL_DATA' };
  if (calculated === null) return { delta: null, status: 'NO_DENOMINATOR' };
  if (official === null) return { delta: null, status: 'NO_OFFICIAL' };
  const delta = calculated - official;
  const absolute = Math.abs(delta);
  if (absolute <= 0.011) return { delta, status: 'MATCH' };
  if (absolute <= 0.025) return { delta, status: 'CLOSE' };
  return { delta, status: 'MISMATCH' };
}

export function replayCarrierInspectionMeasures(evidence: CarrierEvidence): SmsMeasureReplay[] {
  const inspections = evidence.slices.smsInspection?.rows ?? [];
  const violations = evidence.slices.smsViolation?.rows ?? [];
  const truncatedInput = Boolean(evidence.slices.smsInspection?.truncated || evidence.slices.smsViolation?.truncated);

  return INSPECTION_MEASURE_BASICS.map((basic) => {
    const replay = replayInspectionMeasure(inspections, violations, basic);
    const official = officialMeasure(evidence, basic);
    return {
      ...replay,
      officialMeasure: official,
      truncatedInput,
      ...compare(replay.calculatedMeasure, official, truncatedInput),
    };
  });
}

export function replaySummary(replays: SmsMeasureReplay[]) {
  const validationCandidates = replays.filter((replay) => replay.officialMeasure !== null && !replay.truncatedInput);
  const matches = validationCandidates.filter((replay) => replay.status === 'MATCH' || replay.status === 'CLOSE');
  const mismatches = validationCandidates.filter((replay) => replay.status === 'MISMATCH');
  return {
    validationCandidates: validationCandidates.length,
    matches: matches.length,
    mismatches: mismatches.length,
    exactMatches: validationCandidates.filter((replay) => replay.status === 'MATCH').length,
  };
}
