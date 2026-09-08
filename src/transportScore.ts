import {
  CarrierEvidence,
  activeInsuranceRows,
  authorityStatuses,
  officialSmsRows,
  rowCount,
  truthyFlag,
} from './carrierEvidence';
import { readNumber, readValue } from './datahub';
import { assessFleetBand } from './fleetIntegrity';

export const TRI_RULESET = {
  id: 'TRI_0_1_RESEARCH',
  version: '0.1',
  published: '2026-09-08',
  status: 'RESEARCH_NOT_ACTUARIALLY_VALIDATED',
} as const;

export type TransportScoreInput = {
  powerUnits?: string;
  drivers?: string;
  mileage?: string;
  mileageYear?: string;
  mcs150Date?: string;
  fleetSizeCode?: string;
};

export type OfficialBasicPercentile = {
  key: 'unsafe' | 'hos' | 'vehicleMaintenance' | 'driverFitness' | 'controlledSubstances';
  label: string;
  percentile: number | null;
  weight: number;
};

export type ScoreComponent = {
  id: 'sms' | 'events' | 'enforcement' | 'coverage';
  label: string;
  score: number | null;
  weight: number;
  evidence: string[];
};

export type TransportRiskScore = {
  ruleset: typeof TRI_RULESET;
  score: number | null;
  band: string;
  confidence: number;
  officialBasics: OfficialBasicPercentile[];
  components: ScoreComponent[];
  hardFlags: string[];
  fleetIntegrity: ReturnType<typeof assessFleetBand>;
};

const BASIC_FIELDS: Array<Omit<OfficialBasicPercentile, 'percentile'>> = [
  { key: 'unsafe', label: 'Unsafe Driving', weight: 0.30 },
  { key: 'hos', label: 'HOS Compliance', weight: 0.25 },
  { key: 'vehicleMaintenance', label: 'Vehicle Maintenance', weight: 0.20 },
  { key: 'driverFitness', label: 'Driver Fitness', weight: 0.15 },
  { key: 'controlledSubstances', label: 'Controlled Substances / Alcohol', weight: 0.10 },
];

const BASIC_ALIASES: Record<OfficialBasicPercentile['key'], string[]> = {
  unsafe: ['UNSAFE_DRIV_PCT'],
  hos: ['HOS_DRIV_PCT'],
  vehicleMaintenance: ['VEH_MAINT_PCT'],
  driverFitness: ['DRIV_FIT_PCT'],
  controlledSubstances: ['CONTR_SUBST_PCT'],
};

function clamp(value: number, min = 0, max = 100): number {
  return Math.max(min, Math.min(max, value));
}

function weightedAverage(items: Array<{ score: number | null; weight: number }>): number | null {
  const available = items.filter((item): item is { score: number; weight: number } => item.score !== null && Number.isFinite(item.score));
  const denominator = available.reduce((sum, item) => sum + item.weight, 0);
  if (!denominator) return null;
  return available.reduce((sum, item) => sum + item.score * item.weight, 0) / denominator;
}

function currentOfficialPercentiles(evidence: CarrierEvidence): OfficialBasicPercentile[] {
  const row = officialSmsRows(evidence)[0];
  return BASIC_FIELDS.map((field) => ({
    ...field,
    percentile: row ? readNumber(row, BASIC_ALIASES[field.key]) : null,
  })).map((entry) => ({ ...entry, percentile: entry.percentile === null ? null : clamp(entry.percentile) }));
}

function eventPressure(evidence: CarrierEvidence, powerUnits?: string): ScoreComponent {
  const inspections = evidence.slices.inspections?.rows ?? [];
  const violations = evidence.slices.violations?.rows ?? [];
  const crashes = evidence.slices.crash?.rows ?? [];

  const oosInspectionIds = new Set(
    violations
      .filter((row) => truthyFlag(readValue(row, ['OOS', 'OOS_IND', 'OOS_FLAG', 'OUT_OF_SERVICE'])))
      .map((row) => readValue(row, ['INSPECTION_ID', 'UNIQUE_ID', 'INSP_ID']))
      .filter((value): value is string => Boolean(value)),
  );
  const oosRate = inspections.length ? oosInspectionIds.size / inspections.length : null;

  let severityUnits = 0;
  let fatal = 0;
  let injury = 0;
  let tow = 0;
  for (const row of crashes) {
    const fatalities = readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT', 'FATAL_CNT']) ?? 0;
    const injuries = readNumber(row, ['INJURIES', 'INJURY_CNT', 'INJURY_COUNT', 'INJ_CNT']) ?? 0;
    const towAway = truthyFlag(readValue(row, ['TOW_AWAY', 'TOWAWAY', 'TOW_AWAY_FLAG']));
    if (fatalities > 0) { severityUnits += 4; fatal += 1; }
    else if (injuries > 0) { severityUnits += 2; injury += 1; }
    else if (towAway) { severityUnits += 1; tow += 1; }
    else severityUnits += 0.5;
  }

  const pu = Number(String(powerUnits ?? '').replaceAll(',', ''));
  const crashPressure = evidence.slices.crash
    ? crashes.length === 0 ? 0 : Number.isFinite(pu) && pu > 0 ? clamp((severityUnits / pu) * 25) : clamp(severityUnits * 8)
    : null;
  const oosPressure = evidence.slices.inspections && evidence.slices.violations && oosRate !== null ? clamp(oosRate * 100) : null;
  const score = weightedAverage([
    { score: crashPressure, weight: 0.55 },
    { score: oosPressure, weight: 0.45 },
  ]);

  const evidenceNotes: string[] = [];
  if (evidence.slices.crash) evidenceNotes.push(`${crashes.length} loaded crash rows · ${fatal} fatality-involved · ${injury} injury-involved · ${tow} tow-away-only`);
  if (oosRate !== null) evidenceNotes.push(`${oosInspectionIds.size}/${inspections.length} loaded inspections have one or more OOS violation rows`);
  if (crashes.length && (!Number.isFinite(pu) || pu <= 0)) evidenceNotes.push('Crash pressure could not normalize to reported power units; conservative event weighting used.');

  return { id: 'events', label: 'Safety event pressure', score, weight: 0.20, evidence: evidenceNotes };
}

function enforcementPressure(evidence: CarrierEvidence): ScoreComponent {
  const statuses = authorityStatuses(evidence);
  const recentRevokes = rowCount(evidence.slices.motusRevokeSuspendDelta);
  const newEntrantOos = rowCount(evidence.slices.newEntrantOos);
  const revokeHistory = rowCount(evidence.slices.motusRevokeSuspend);
  const hasAuthorityEvidence = Boolean(evidence.slices.motusCarrier || evidence.slices.motusRevokeSuspend || evidence.slices.newEntrantOos);
  if (!hasAuthorityEvidence) return { id: 'enforcement', label: 'Authority / enforcement', score: null, weight: 0.15, evidence: [] };

  let score = 0;
  const notes: string[] = [];
  for (const status of statuses) {
    const normalized = status.toUpperCase();
    if (/(REVOK|SUSPEND|INACTIVE|NOT AUTH|OUT OF SERVICE)/.test(normalized)) score = Math.max(score, 100);
    else if (/PENDING/.test(normalized)) score = Math.max(score, 35);
  }
  if (statuses.length) notes.push(`Current MOTUS authority status: ${statuses.join(', ')}`);
  if (recentRevokes > 0) { score = 100; notes.push(`${recentRevokes} revoke/suspend rows in the loaded 24-hour delta`); }
  if (newEntrantOos > 0) { score = Math.max(score, 95); notes.push(`${newEntrantOos} New Entrant OOS order rows returned`); }
  if (revokeHistory > 0) { score = Math.max(score, Math.min(70, 35 + revokeHistory * 5)); notes.push(`${revokeHistory} historical revoke/suspend rows returned`); }
  if (!notes.length) notes.push('No adverse authority/enforcement row was derived from the loaded sources.');
  return { id: 'enforcement', label: 'Authority / enforcement', score: clamp(score), weight: 0.15, evidence: notes };
}

function coveragePressure(evidence: CarrierEvidence): ScoreComponent {
  const active = activeInsuranceRows(evidence).length;
  const activeDelta = rowCount(evidence.slices.motusInsuranceDelta);
  const historyDelta = rowCount(evidence.slices.motusInsuranceHistoryDelta);
  const hasEvidence = Boolean(evidence.slices.motusInsurance || evidence.slices.motusInsuranceDelta || evidence.slices.motusInsuranceHistoryDelta);
  if (!hasEvidence) return { id: 'coverage', label: 'Coverage change pressure', score: null, weight: 0.05, evidence: [] };
  if (!active && !activeDelta && !historyDelta) {
    return {
      id: 'coverage',
      label: 'Coverage change pressure',
      score: null,
      weight: 0.05,
      evidence: ['No active/pending MOTUS filing rows were returned; Transport3r does not infer that coverage is required or missing from this fact alone.'],
    };
  }
  let score = 0;
  if (activeDelta > 0) score = Math.max(score, 35);
  if (historyDelta > 0) score = Math.max(score, 25);
  if (!active && (activeDelta > 0 || historyDelta > 0)) score = Math.max(score, 45);
  return {
    id: 'coverage',
    label: 'Coverage change pressure',
    score,
    weight: 0.05,
    evidence: [`${active} active/pending filing rows · ${activeDelta} active-file 24h changes · ${historyDelta} history 24h changes`],
  };
}

function monthAge(raw?: string): number | null {
  if (!raw) return null;
  const date = new Date(raw);
  if (Number.isNaN(date.valueOf())) return null;
  const now = new Date();
  return Math.max(0, (now.getUTCFullYear() - date.getUTCFullYear()) * 12 + (now.getUTCMonth() - date.getUTCMonth()));
}

export function scoreBandLabel(score: number | null): string {
  if (score === null) return 'Insufficient data';
  if (score >= 80) return 'Severe signal';
  if (score >= 65) return 'High signal';
  if (score >= 45) return 'Elevated signal';
  if (score >= 25) return 'Moderate signal';
  return 'Lower signal';
}

export function buildTransportScore(input: TransportScoreInput, evidence: CarrierEvidence): TransportRiskScore {
  const officialBasics = currentOfficialPercentiles(evidence);
  const availableBasics = officialBasics.filter((basic) => basic.percentile !== null);
  const smsScore = weightedAverage(officialBasics.map((basic) => ({ score: basic.percentile, weight: basic.weight })));
  const smsComponent: ScoreComponent = {
    id: 'sms',
    label: 'Official SMS percentile index',
    score: smsScore,
    weight: 0.60,
    evidence: availableBasics.map((basic) => `${basic.label}: ${basic.percentile?.toFixed(1)} percentile`),
  };

  const events = eventPressure(evidence, input.powerUnits);
  const enforcement = enforcementPressure(evidence);
  const coverage = coveragePressure(evidence);
  const components = [smsComponent, events, enforcement, coverage];
  const score = weightedAverage(components.map((component) => ({ score: component.score, weight: component.weight })));

  const fleetIntegrity = assessFleetBand(input.powerUnits, input.fleetSizeCode);
  const hardFlags: string[] = [];
  if (fleetIntegrity.status === 'MISMATCH') hardFlags.push(`Company Census fleet band ${fleetIntegrity.actual ?? '—'} does not match ${input.powerUnits ?? '—'} reported power units (expected ${fleetIntegrity.expected ?? '—'}).`);
  const mcsAge = monthAge(input.mcs150Date);
  if (mcsAge !== null && mcsAge > 24) hardFlags.push(`MCS-150 carrier report is approximately ${mcsAge} months old; exposure values may be stale.`);
  const eventCrashes = evidence.slices.crash?.rows ?? [];
  const fatalRows = eventCrashes.filter((row) => (readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT', 'FATAL_CNT']) ?? 0) > 0).length;
  if (fatalRows > 0) hardFlags.push(`${fatalRows} loaded crash record${fatalRows === 1 ? '' : 's'} reports one or more fatalities.`);
  if (rowCount(evidence.slices.motusRevokeSuspendDelta) > 0) hardFlags.push('Recent MOTUS revoke/suspend activity is present in the loaded 24-hour difference feed.');
  if (rowCount(evidence.slices.newEntrantOos) > 0) hardFlags.push('New Entrant OOS order history is present and requires current-effect review.');

  let confidence = 0;
  confidence += (availableBasics.length / BASIC_FIELDS.length) * 45;
  if (events.score !== null) confidence += 15;
  if (enforcement.score !== null) confidence += 15;
  if (coverage.score !== null || coverage.evidence.length) confidence += 10;
  confidence += [input.powerUnits, input.drivers, input.mileage, input.mcs150Date].filter((value) => Boolean(String(value ?? '').trim())).length * 2.5;
  if (fleetIntegrity.status === 'MATCH') confidence += 5;
  else if (fleetIntegrity.status === 'UNKNOWN') confidence += 2;
  confidence -= Math.min(20, Object.keys(evidence.errors).length * 5);
  confidence = Math.round(clamp(confidence));

  const usableScore = smsScore === null && enforcement.score === null && events.score === null ? null : score === null ? null : Math.round(clamp(score) * 10) / 10;
  return {
    ruleset: TRI_RULESET,
    score: usableScore,
    band: scoreBandLabel(usableScore),
    confidence,
    officialBasics,
    components,
    hardFlags,
    fleetIntegrity,
  };
}
