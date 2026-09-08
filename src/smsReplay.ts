import { CarrierEvidence, selectOfficialSmsOutput } from './carrierEvidence';
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
  numerator: number | null;
  denominator: number | null;
  calculatedMeasure: number | null;
  officialMeasure: number | null;
  delta: number | null;
  status: SmsReplayStatus;
  relevantInspections: number;
  violationInspections: number;
  safetyEventGroup: number | null;
  cappedInspections: number;
  truncatedInput: boolean;
  inputIssues: string[];
  officialOutputIssues: string[];
};

function truthy(raw?: string): boolean {
  if (!raw) return false;
  return ['Y', 'YES', 'TRUE', 'T', '1'].includes(raw.trim().toUpperCase());
}

function numeric(raw: unknown): number | null {
  if (raw === null || raw === undefined || String(raw).trim() === '') return null;
  const text = String(raw).trim();
  if (!/^\d+(?:\.\d+)?$/.test(text)) return null;
  const value = Number(text);
  return Number.isFinite(value) && value >= 0 ? value : null;
}

function inspectionKey(row: DataRow): string | undefined {
  return readValue(row, ['UNIQUE_ID', 'INSPECTION_ID', 'INSP_ID']);
}

function violationMatchesBasic(row: DataRow, basic: InspectionMeasureBasicKey): boolean {
  const description = (readValue(row, ['BASIC_DESC']) ?? '').toLowerCase();
  return SMS_BASIC_RULES[basic].violationBasicMatches.some((match) => description.includes(match));
}

function officialMeasure(row: DataRow | null, basic: InspectionMeasureBasicKey): number | null {
  const field = SMS_BASIC_RULES[basic].officialMeasureField;
  if (!field) return null;
  if (!row) return null;
  const raw = readValue(row, [field]);
  return raw && /^(?:\d+(?:\.\d+)?|\.\d+)$/.test(raw.trim()) ? readNumber(row, [field]) : null;
}

export function replayInspectionMeasure(
  inspections: DataRow[],
  violations: DataRow[],
  basic: InspectionMeasureBasicKey,
): Omit<SmsMeasureReplay, 'officialMeasure' | 'delta' | 'status' | 'truncatedInput' | 'officialOutputIssues'> {
  const rule = SMS_BASIC_RULES[basic];
  if (!rule.relevantInspectionField) throw new Error(`${basic} does not define a relevant-inspection field`);

  const relevant = inspections.filter((row) => truthy(readValue(row, [rule.relevantInspectionField!]))) ;
  const issues = new Set<string>();
  const seen = new Set<string>();
  for (const row of inspections) {
    const key = inspectionKey(row);
    if (!key) issues.add('MISSING_INSPECTION_ID');
    else if (seen.has(key)) issues.add(`DUPLICATE_INSPECTION_ID:${key}`);
    else seen.add(key);
    const flag = readValue(row, [rule.relevantInspectionField!]);
    // Published SMS inputs use affirmative flags and can omit non-affirmative fields.
    if (flag && !['Y','YES','TRUE','T','1','N','NO','FALSE','F','0'].includes(flag.trim().toUpperCase())) issues.add(`INVALID_RELEVANCE_FLAG:${key}`);
  }
  const inspectionTimeWeights = new Map<string, number>();
  for (const row of relevant) {
    const key = inspectionKey(row);
    if (!key) continue;
    const weight = numeric(readValue(row, ['TIME_WEIGHT']));
    if (weight === null || ![1,2,3].includes(weight)) issues.add(`INVALID_INSPECTION_TIME_WEIGHT:${key}`);
    else inspectionTimeWeights.set(key, weight);
  }

  const denominator = [...inspectionTimeWeights.values()].reduce((sum, weight) => sum + weight, 0);
  const violationSeverityByInspection = new Map<string, number>();
  const violationTimeWeightByInspection = new Map<string, number>();

  for (const row of violations) {
    if (!readValue(row, ['BASIC_DESC'])) issues.add('MISSING_VIOLATION_BASIC');
    if (!violationMatchesBasic(row, basic)) continue;
    const key = inspectionKey(row);
    if (!key || !inspectionTimeWeights.has(key)) {
      issues.add(`UNMATCHED_RELEVANT_INSPECTION:${key ?? 'missing'}`);
      continue;
    }

    const rawTotalSeverity = readValue(row, ['TOTAL_SEVERITY_WGHT']);
    const totalSeverity = numeric(rawTotalSeverity);
    const baseSeverity = numeric(readValue(row, ['SEVERITY_WEIGHT']));
    const oosWeight = basic === 'controlledSubstances' ? 0 : numeric(readValue(row, ['OOS_WEIGHT']));
    const severity = rawTotalSeverity !== undefined ? totalSeverity : baseSeverity !== null && oosWeight !== null ? baseSeverity + oosWeight : null;
    if (severity === null) {
      issues.add(`INVALID_VIOLATION_SEVERITY:${key}`);
      continue;
    }
    violationSeverityByInspection.set(key, (violationSeverityByInspection.get(key) ?? 0) + severity);

    const rowTimeWeight = numeric(readValue(row, ['TIME_WEIGHT']));
    if (rowTimeWeight === null || rowTimeWeight !== inspectionTimeWeights.get(key)) issues.add(`INCONSISTENT_VIOLATION_TIME_WEIGHT:${key}`);
    else violationTimeWeightByInspection.set(key, rowTimeWeight);
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
    numerator: issues.size ? null : numerator,
    denominator: issues.size ? null : denominator,
    calculatedMeasure: issues.size ? null : calculatedMeasure,
    relevantInspections: inspectionTimeWeights.size,
    violationInspections: violationSeverityByInspection.size,
    safetyEventGroup: issues.size ? null : safetyEventGroup(basic, basic === 'controlledSubstances' ? violationSeverityByInspection.size : inspectionTimeWeights.size),
    cappedInspections,
    inputIssues: [...issues],
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
  const officialOutput = selectOfficialSmsOutput(evidence);
  const inspections = evidence.slices.smsInspection?.rows ?? [];
  const violations = evidence.slices.smsViolation?.rows ?? [];
  const truncatedInput = Boolean(!evidence.slices.smsInspection || !evidence.slices.smsViolation ||
    evidence.errors.smsInspection || evidence.errors.smsViolation ||
    evidence.slices.smsInspection?.truncated || evidence.slices.smsViolation?.truncated);

  return INSPECTION_MEASURE_BASICS.map((basic) => {
    const replay = replayInspectionMeasure(inspections, violations, basic);
    const inputIssues = [...replay.inputIssues];
    if (evidence.dotNumber && [...inspections,...violations].some((row) => readValue(row, ['DOT_NUMBER'])?.trim() !== evidence.dotNumber)) inputIssues.push('CARRIER_IDENTITY_MISMATCH');
    const incomplete = truncatedInput || inputIssues.length > 0;
    const official = officialMeasure(officialOutput.row, basic);
    return {
      ...replay,
      numerator: incomplete ? null : replay.numerator,
      denominator: incomplete ? null : replay.denominator,
      calculatedMeasure: incomplete ? null : replay.calculatedMeasure,
      safetyEventGroup: incomplete ? null : replay.safetyEventGroup,
      inputIssues,
      officialOutputIssues: officialOutput.issues,
      officialMeasure: official,
      truncatedInput,
      ...compare(replay.calculatedMeasure, official, incomplete || officialOutput.issues.length > 0),
    };
  });
}

export function replaySummary(replays: SmsMeasureReplay[]) {
  const validationCandidates = replays.filter((replay) => ['MATCH', 'CLOSE', 'MISMATCH'].includes(replay.status));
  const matches = validationCandidates.filter((replay) => replay.status === 'MATCH' || replay.status === 'CLOSE');
  const mismatches = validationCandidates.filter((replay) => replay.status === 'MISMATCH');
  return {
    validationCandidates: validationCandidates.length,
    matches: matches.length,
    mismatches: mismatches.length,
    exactMatches: validationCandidates.filter((replay) => replay.status === 'MATCH').length,
  };
}
