from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: expected exactly one match, found {count}: {old[:100]!r}')
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


fleet_integrity = r'''export type FleetBandCode =
  | 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J' | 'K' | 'L' | 'M'
  | 'N' | 'O' | 'P' | 'Q' | 'R' | 'S' | 'T' | 'U' | 'V' | 'W' | 'X' | 'Y' | 'Z';

export type FleetBandAssessment = {
  status: 'MATCH' | 'MISMATCH' | 'UNKNOWN';
  actual: FleetBandCode | null;
  expected: FleetBandCode | null;
  powerUnits: number | null;
  actualLabel: string;
  expectedLabel: string;
};

// FMCSA Company Census FLEETSIZE code ranges reviewed against the current data dictionary in September 2026.
const FLEET_BANDS: Array<{ code: FleetBandCode; min: number; max: number }> = [
  { code: 'A', min: 1, max: 1 },
  { code: 'B', min: 2, max: 3 },
  { code: 'C', min: 4, max: 6 },
  { code: 'D', min: 7, max: 8 },
  { code: 'E', min: 9, max: 11 },
  { code: 'F', min: 12, max: 14 },
  { code: 'G', min: 15, max: 17 },
  { code: 'H', min: 18, max: 19 },
  { code: 'I', min: 20, max: 23 },
  { code: 'J', min: 24, max: 28 },
  { code: 'K', min: 29, max: 32 },
  { code: 'L', min: 33, max: 38 },
  { code: 'M', min: 39, max: 44 },
  { code: 'N', min: 45, max: 55 },
  { code: 'O', min: 56, max: 75 },
  { code: 'P', min: 76, max: 100 },
  { code: 'Q', min: 101, max: 200 },
  { code: 'R', min: 201, max: 300 },
  { code: 'S', min: 301, max: 400 },
  { code: 'T', min: 401, max: 550 },
  { code: 'U', min: 551, max: 999 },
  { code: 'V', min: 1000, max: 2000 },
  { code: 'W', min: 2001, max: 3000 },
  { code: 'X', min: 3001, max: 4000 },
  { code: 'Y', min: 4001, max: 5000 },
  { code: 'Z', min: 5001, max: Number.POSITIVE_INFINITY },
];

function countValue(raw?: string | number | null): number | null {
  if (raw === null || raw === undefined || String(raw).trim() === '') return null;
  const value = Number(String(raw).replaceAll(',', ''));
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.round(value);
}

function normalizeCode(raw?: string | null): FleetBandCode | null {
  const value = String(raw ?? '').trim().toUpperCase();
  return FLEET_BANDS.some((band) => band.code === value) ? value as FleetBandCode : null;
}

export function expectedFleetBand(powerUnits?: string | number | null): FleetBandCode | null {
  const count = countValue(powerUnits);
  if (count === null || count < 1) return null;
  return FLEET_BANDS.find((band) => count >= band.min && count <= band.max)?.code ?? null;
}

export function fleetBandLabel(raw?: string | null): string {
  const code = normalizeCode(raw);
  if (!code) return 'Band unavailable';
  const band = FLEET_BANDS.find((candidate) => candidate.code === code)!;
  if (!Number.isFinite(band.max)) return `${code} · 5,001+`;
  if (band.min === band.max) return `${code} · ${band.min.toLocaleString()}`;
  return `${code} · ${band.min.toLocaleString()}–${band.max.toLocaleString()}`;
}

export function assessFleetBand(powerUnits?: string | number | null, fleetSizeCode?: string | null): FleetBandAssessment {
  const count = countValue(powerUnits);
  const actual = normalizeCode(fleetSizeCode);
  const expected = expectedFleetBand(powerUnits);
  return {
    status: actual && expected ? (actual === expected ? 'MATCH' : 'MISMATCH') : 'UNKNOWN',
    actual,
    expected,
    powerUnits: count,
    actualLabel: fleetBandLabel(actual),
    expectedLabel: fleetBandLabel(expected),
  };
}
'''
(ROOT / 'src/fleetIntegrity.ts').write_text(fleet_integrity, encoding='utf-8')

transport_score = r'''import {
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
'''
(ROOT / 'src/transportScore.ts').write_text(transport_score, encoding='utf-8')

carrier = ROOT / 'src/CarrierRouteApp.tsx'
replace_once(
    carrier,
    "import { DataRow, readNumber, readValue, schemaLabel } from './datahub';\nimport { replayCarrierInspectionMeasures, replaySummary } from './smsReplay';",
    "import { DataRow, readNumber, readValue, schemaLabel } from './datahub';\nimport { assessFleetBand, fleetBandLabel } from './fleetIntegrity';\nimport { replayCarrierInspectionMeasures, replaySummary } from './smsReplay';\nimport { buildTransportScore, TRI_RULESET } from './transportScore';",
)
replace_once(
    carrier,
    "type CarrierSection = 'summary' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence';",
    "type CarrierSection = 'summary' | 'score' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence';",
)
replace_once(
    carrier,
    "  powerUnits?: string;\n  drivers?: string;\n  mileage?: string;\n  mileageYear?: string;\n  hazmat?: string;",
    "  powerUnits?: string;\n  truckUnits?: string;\n  busUnits?: string;\n  fleetSizeCode?: string;\n  drivers?: string;\n  mileage?: string;\n  mileageYear?: string;\n  mcs150Date?: string;\n  hazmat?: string;",
)
replace_once(
    carrier,
    "  { id: 'summary', label: 'Summary', description: 'Decision view' },\n  { id: 'safety', label: 'Safety', description: 'Inspections & crashes' },",
    "  { id: 'summary', label: 'Summary', description: 'Decision view' },\n  { id: 'score', label: 'Score', description: 'TRI v0.1 research' },\n  { id: 'safety', label: 'Safety', description: 'Inspections & crashes' },",
)
replace_once(
    carrier,
    "function routeMode(route: ParsedRoute): CarrierEvidenceMode {\n  return route.kind === 'inspection' ? 'inspection' : route.section;\n}",
    "function routeMode(route: ParsedRoute): CarrierEvidenceMode {\n  if (route.kind === 'inspection') return 'inspection';\n  if (route.section === 'score') return 'summary';\n  return route.section;\n}",
)
replace_once(
    carrier,
    "    powerUnits: readValue(row, ['POWER_UNITS', 'NBR_POWER_UNIT', 'TOTAL_POWER_UNITS']),\n    drivers: readValue(row, ['TOTAL_DRIVERS', 'DRIVER_TOTAL', 'DRIVERS']),\n    mileage: readValue(row, ['MCS150_MILEAGE', 'MILEAGE', 'VMT']),\n    mileageYear: readValue(row, ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR', 'VMT_YEAR']),",
    "    powerUnits: readValue(row, ['POWER_UNITS', 'NBR_POWER_UNIT', 'TOTAL_POWER_UNITS']),\n    truckUnits: readValue(row, ['TRUCK_UNITS']),\n    busUnits: readValue(row, ['BUS_UNITS']),\n    fleetSizeCode: readValue(row, ['FLEETSIZE', 'FLEET_SIZE_CODE']),\n    drivers: readValue(row, ['TOTAL_DRIVERS', 'DRIVER_TOTAL', 'DRIVERS']),\n    mileage: readValue(row, ['MCS150_MILEAGE', 'MILEAGE', 'VMT']),\n    mileageYear: readValue(row, ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR', 'VMT_YEAR']),\n    mcs150Date: readValue(row, ['MCS150_DATE']),",
)
replace_once(
    carrier,
    "function Badge({ children, tone = 'official' }: { children: ReactNode; tone?: 'official' | 'calculated' | 'warning' | 'good' | 'neutral' }) {",
    "function Badge({ children, tone = 'official' }: { children: ReactNode; tone?: 'official' | 'calculated' | 'modelled' | 'warning' | 'good' | 'neutral' }) {",
)
replace_once(
    carrier,
    "    <section className=\"c360-exposure-strip\"><Metric label=\"Reported power units\" value={formatNumber(carrier.powerUnits)} /><Metric label=\"Drivers\" value={formatNumber(carrier.drivers)} /><Metric label=\"Reported VMT\" value={formatNumber(carrier.mileage)} detail={carrier.mileageYear ? `MCS-150 mileage year ${carrier.mileageYear}` : 'Mileage year unavailable'} /><Metric label=\"Operating class\" value={formatOperation(carrier.operation)} /></section>",
    "    <section className=\"c360-exposure-strip\"><Metric label=\"Reported power units\" value={formatNumber(carrier.powerUnits)} /><Metric label=\"Fleet band\" value={fleetBandLabel(carrier.fleetSizeCode)} detail=\"Company Census FLEETSIZE\" /><Metric label=\"Drivers\" value={formatNumber(carrier.drivers)} /><Metric label=\"Reported VMT\" value={formatNumber(carrier.mileage)} detail={carrier.mileageYear ? `MCS-150 mileage year ${carrier.mileageYear}` : 'Mileage year unavailable'} /><Metric label=\"Operating class\" value={formatOperation(carrier.operation)} /></section>",
)

score_components = r'''
function ScoreSummary({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const score = buildTransportScore({
    powerUnits: carrier.powerUnits,
    drivers: carrier.drivers,
    mileage: carrier.mileage,
    mileageYear: carrier.mileageYear,
    mcs150Date: carrier.mcs150Date,
    fleetSizeCode: carrier.fleetSizeCode,
  }, evidence);
  const tone = score.score === null ? 'neutral' : score.score >= 65 ? 'warning' : score.score < 25 ? 'good' : 'calculated';
  return <div className="c360-score-summary">
    <div className="c360-score-number"><span>TRI v{TRI_RULESET.version}</span><strong>{score.score === null ? '—' : score.score.toFixed(1)}</strong><small>{score.band}</small></div>
    <div className="c360-score-summary-copy"><div><Badge tone="modelled">Transport modelled</Badge><Badge tone={tone}>{score.confidence}% confidence</Badge></div><p>Research underwriting index. Official public SMS percentiles are the largest input; event, authority and coverage signals are separately modelled. Not an FMCSA safety rating or an actuarially validated pricing score.</p></div>
    <a href={`#/carrier/${carrier.dotNumber}/score`}>Open score methodology →</a>
  </div>;
}

function Score({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const score = buildTransportScore({
    powerUnits: carrier.powerUnits,
    drivers: carrier.drivers,
    mileage: carrier.mileage,
    mileageYear: carrier.mileageYear,
    mcs150Date: carrier.mcs150Date,
    fleetSizeCode: carrier.fleetSizeCode,
  }, evidence);
  return <section className="c360-card">
    <SectionHeading eyebrow={`Transport modelled · ${TRI_RULESET.id}`} title="Transport Risk Index" badges={<div className="c360-badge-stack"><Badge tone="modelled">Research v{TRI_RULESET.version}</Badge><Badge>Official SMS backbone</Badge></div>} />
    <div className="c360-score-hero">
      <div className="c360-score-dial"><span>0</span><strong>{score.score === null ? '—' : score.score.toFixed(1)}</strong><span>100</span><small>Higher = more underwriting concern</small></div>
      <div><div className="t3-eyebrow">Signal band</div><h3>{score.band}</h3><p>Confidence {score.confidence}%. The score is suppressed when there is not enough safety/enforcement evidence to support a meaningful composite.</p></div>
      <div><div className="t3-eyebrow">Fleet data integrity</div><h3>{score.fleetIntegrity.status}</h3><p>Reported {formatNumber(carrier.powerUnits)} power units · {score.fleetIntegrity.actualLabel}{score.fleetIntegrity.status === 'MISMATCH' ? ` · expected ${score.fleetIntegrity.expectedLabel}` : ''}.</p></div>
    </div>
    {score.hardFlags.length > 0 && <div className="c360-review warning"><strong>Hard-review flags are not averaged away by the score</strong><ul>{score.hardFlags.map((flag) => <li key={flag}>{flag}</li>)}</ul></div>}
    <h3 className="c360-subhead">Score components</h3>
    <div className="c360-score-components">{score.components.map((component) => <article key={component.id}><div className="c360-score-component-head"><span>{component.label}</span><strong>{component.score === null ? 'N/A' : component.score.toFixed(1)}</strong></div><div className="c360-score-bar"><i style={{ width: `${component.score ?? 0}%` }}/></div><small>{Math.round(component.weight * 100)}% configured composite weight · unavailable components are reweighted out</small>{component.evidence.length > 0 && <ul>{component.evidence.map((item) => <li key={item}>{item}</li>)}</ul>}</article>)}</div>
    <h3 className="c360-subhead">Official public SMS percentiles used</h3>
    <div className="c360-official-grid">{score.officialBasics.map((basic) => <div key={basic.key}><span>{basic.label}</span><strong>{basic.percentile === null ? 'N/A' : basic.percentile.toFixed(1)}</strong><small>{Math.round(basic.weight * 100)}% inside SMS component</small></div>)}</div>
    <div className="c360-note"><strong>TRI v0.1 calculation contract</strong><p>Configured composite weights: 60% official SMS percentile index, 20% modelled safety-event pressure, 15% authority/enforcement pressure and 5% coverage-change pressure. Missing components are not scored as zero; available components are reweighted. Company Census freshness and fleet-band consistency affect confidence and hard-review flags, not the numeric risk score.</p></div>
    <div className="c360-review clear"><strong>Research use only</strong><p>TRI v0.1 is designed for triage and evidence prioritization. It is not an FMCSA safety rating, does not determine legal operating status, and has not been calibrated against insurer loss outcomes. Do not use it as an automated bind/decline, eligibility, pricing or premium decision.</p></div>
    <SourceErrors evidence={evidence}/>
  </section>;
}
'''
replace_once(carrier, "function Summary({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {", score_components + "\nfunction Summary({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {")
replace_once(
    carrier,
    "  const changes = recentChangeCount(evidence);\n  const concerns: string[] = [];",
    "  const changes = recentChangeCount(evidence);\n  const fleetIntegrity = assessFleetBand(carrier.powerUnits, carrier.fleetSizeCode);\n  const concerns: string[] = [];",
)
replace_once(
    carrier,
    "  if (oos) concerns.push(`${oos} loaded violation row${oos === 1 ? '' : 's'} is flagged out of service.`);",
    "  if (oos) concerns.push(`${oos} loaded violation row${oos === 1 ? '' : 's'} is flagged out of service.`);\n  if (fleetIntegrity.status === 'MISMATCH') concerns.push(`Company Census fleet band ${fleetIntegrity.actual ?? '—'} conflicts with ${carrier.powerUnits ?? '—'} reported power units; expected band ${fleetIntegrity.expected ?? '—'}.`);",
)
replace_once(
    carrier,
    "    <div className=\"c360-metric-grid four\"><Metric label=\"Loaded inspections\" value={rowCountLabel(evidence.slices.inspections)} detail=\"Recent inspection window\"/><Metric label=\"Loaded crashes\" value={rowCountLabel(evidence.slices.crash)} detail={`${crashes.fatal} fatality-involved · ${crashes.injury} injury-involved`}/><Metric label=\"Active/pending filings\" value={formatNumber(activeInsurance)} detail=\"MOTUS insurance\"/><Metric label=\"24h MOTUS changes\" value={formatNumber(changes)} detail=\"Loaded carrier/insurance/revoke deltas\"/></div>",
    "    <ScoreSummary carrier={carrier} evidence={evidence}/><div className=\"c360-metric-grid four\"><Metric label=\"Loaded inspections\" value={rowCountLabel(evidence.slices.inspections)} detail=\"Recent inspection window\"/><Metric label=\"Loaded crashes\" value={rowCountLabel(evidence.slices.crash)} detail={`${crashes.fatal} fatality-involved · ${crashes.injury} injury-involved`}/><Metric label=\"Active/pending filings\" value={formatNumber(activeInsurance)} detail=\"MOTUS insurance\"/><Metric label=\"24h MOTUS changes\" value={formatNumber(changes)} detail=\"Loaded carrier/insurance/revoke deltas\"/></div>",
)
replace_once(
    carrier,
    "function Fleet({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {\n  const units = evidence.slices.units?.rows ?? [];\n  const vins = observedVins(evidence);\n  const reported = Number(carrier.powerUnits);\n  const ratio = Number.isFinite(reported) && reported > 0 ? Math.round((vins.length / reported) * 100) : null;",
    "function Fleet({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {\n  const units = evidence.slices.units?.rows ?? [];\n  const vins = observedVins(evidence);\n  const reported = Number(carrier.powerUnits);\n  const ratio = Number.isFinite(reported) && reported > 0 ? Math.round((vins.length / reported) * 100) : null;\n  const fleetIntegrity = assessFleetBand(carrier.powerUnits, carrier.fleetSizeCode);",
)
replace_once(
    carrier,
    "return <section className=\"c360-card\"><SectionHeading eyebrow=\"Roadside vehicle observations\" title=\"Fleet evidence\" badges={<Badge>Official FMCSA</Badge>} /><div className=\"c360-metric-grid four\"><Metric label=\"Reported power units\" value={formatNumber(carrier.powerUnits)} detail=\"Company Census report\"/><Metric label=\"Unique observed VINs\" value={formatNumber(vins.length)} detail=\"Loaded inspection-unit evidence\"/><Metric label=\"Inspection-unit rows\" value={rowCountLabel(evidence.slices.units)} detail=\"Most recent inspection-ID window\"/><Metric label=\"Observed / reported\" value={ratio === null ? '—' : `${ratio}%`} detail=\"Context only — not ownership coverage\"/></div>",
    "return <section className=\"c360-card\"><SectionHeading eyebrow=\"Reported exposure + roadside observations\" title=\"Fleet evidence\" badges={<div className=\"c360-badge-stack\"><Badge>Official FMCSA</Badge><Badge tone={fleetIntegrity.status === 'MISMATCH' ? 'warning' : fleetIntegrity.status === 'MATCH' ? 'good' : 'neutral'}>{fleetIntegrity.status === 'MATCH' ? 'Census band consistent' : fleetIntegrity.status === 'MISMATCH' ? 'Census band mismatch' : 'Band not comparable'}</Badge></div>} /><div className=\"c360-metric-grid six\"><Metric label=\"Reported power units\" value={formatNumber(carrier.powerUnits)} detail=\"Company Census POWER_UNITS\"/><Metric label=\"Fleet band\" value={fleetIntegrity.actualLabel} detail={fleetIntegrity.status === 'MISMATCH' ? `Expected ${fleetIntegrity.expectedLabel}` : 'Company Census FLEETSIZE'}/><Metric label=\"Truck units\" value={formatNumber(carrier.truckUnits)} detail=\"Company Census\"/><Metric label=\"Bus units\" value={formatNumber(carrier.busUnits)} detail=\"Company Census\"/><Metric label=\"Unique observed VINs\" value={formatNumber(vins.length)} detail=\"Loaded inspection-unit evidence\"/><Metric label=\"Observed / reported\" value={ratio === null ? '—' : `${ratio}%`} detail=\"Context only — not ownership coverage\"/></div>{fleetIntegrity.status === 'MISMATCH' && <div className=\"c360-review warning\"><strong>FMCSA Census fields disagree on fleet size</strong><p>POWER_UNITS reports {formatNumber(carrier.powerUnits)}, which maps to {fleetIntegrity.expectedLabel}, while FLEETSIZE reports {fleetIntegrity.actualLabel}. Transport3r is preserving both source values and flagging the inconsistency instead of silently choosing one.</p></div>}",
)
replace_once(
    carrier,
    "    if (route.section === 'summary') return <Summary carrier={carrier} evidence={evidence}/>;\n    if (route.section === 'safety') return <Safety carrier={carrier} evidence={evidence}/>;",
    "    if (route.section === 'summary') return <Summary carrier={carrier} evidence={evidence}/>;\n    if (route.section === 'score') return <Score carrier={carrier} evidence={evidence}/>;\n    if (route.section === 'safety') return <Safety carrier={carrier} evidence={evidence}/>;",
)

css = ROOT / 'src/carrierRoutes.css'
css_text = css.read_text(encoding='utf-8')
marker = '/* TRI v0.1 */'
if marker not in css_text:
    css_text += r'''

/* TRI v0.1 */
.c360-badge.modelled{background:#f3e8ff;color:#6b21a8;border-color:#d8b4fe}
.c360-score-summary{display:grid;grid-template-columns:120px 1fr auto;gap:18px;align-items:center;padding:18px 20px;margin:0 0 22px;border:1px solid #dfe7ef;border-radius:16px;background:linear-gradient(135deg,#f8fbff 0%,#fff 58%,#faf5ff 100%)}
.c360-score-number{display:flex;flex-direction:column;align-items:flex-start}.c360-score-number>span{font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:#667085}.c360-score-number strong{font-size:38px;line-height:1;color:#172033}.c360-score-number small{margin-top:5px;color:#667085;font-weight:700}
.c360-score-summary-copy>div{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px}.c360-score-summary-copy p{margin:0;color:#52606d;line-height:1.45}.c360-score-summary>a{font-size:13px;font-weight:800;text-decoration:none;color:#165d96;white-space:nowrap}
.c360-score-hero{display:grid;grid-template-columns:210px 1fr 1fr;gap:18px;margin-bottom:24px}.c360-score-hero>div{border:1px solid #e1e7ee;border-radius:16px;padding:18px;background:#fff}.c360-score-hero h3{margin:5px 0 8px;font-size:22px}.c360-score-hero p{margin:0;color:#596676;line-height:1.5}
.c360-score-dial{display:grid!important;grid-template-columns:auto 1fr auto!important;align-items:end!important;text-align:center;background:linear-gradient(180deg,#f8fbff,#fff)!important}.c360-score-dial strong{font-size:48px;line-height:1;color:#172033}.c360-score-dial>span{font-size:11px;color:#98a2b3}.c360-score-dial small{grid-column:1/-1;margin-top:9px;color:#667085}
.c360-score-components{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-bottom:24px}.c360-score-components article{border:1px solid #e1e7ee;border-radius:14px;padding:16px;background:#fff}.c360-score-component-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.c360-score-component-head span{font-weight:800}.c360-score-component-head strong{font-size:22px}.c360-score-bar{height:7px;background:#edf1f5;border-radius:99px;overflow:hidden;margin:10px 0}.c360-score-bar i{display:block;height:100%;background:linear-gradient(90deg,#2b78b8,#a855f7);border-radius:99px}.c360-score-components small{color:#667085}.c360-score-components ul{margin:10px 0 0;padding-left:18px;color:#52606d;font-size:12px;line-height:1.45}
@media(max-width:900px){.c360-score-summary{grid-template-columns:100px 1fr}.c360-score-summary>a{grid-column:1/-1}.c360-score-hero{grid-template-columns:1fr}.c360-score-components{grid-template-columns:1fr}}
@media(max-width:620px){.c360-score-summary{grid-template-columns:1fr}.c360-score-number{align-items:flex-start}.c360-score-number strong{font-size:34px}}
'''
    css.write_text(css_text, encoding='utf-8')

workspace = ROOT / 'src/WorkspaceApp.tsx'
replace_once(
    workspace,
    "<p>TRI is intentionally not released until full-population percentile reconstruction, exposure treatment and actuarial validation are defensible.</p>",
    "<p>TRI v0.1 is a research underwriting index that uses official public SMS percentiles where available, plus separately labelled Transport-modelled event, enforcement and coverage signals. It is not actuarially validated for pricing or eligibility.</p>",
)
replace_once(
    workspace,
    "<div><span>5</span><strong>Percentile gate</strong><p>Blocked until the peer-population calculation is reconstructed and validated exactly.</p></div><div><span>6</span><strong>TRI gate</strong><p>Only after actuarial testing against insurer claims and exposure.</p></div>",
    "<div><span>5</span><strong>Percentile layer</strong><p>Use FMCSA's official public percentile outputs where published. Peer reconstruction remains gated for unavailable categories and what-if calculations.</p></div><div><span>6</span><strong>TRI v0.1 research</strong><p>Composite triage score is visible with confidence and formula lineage; actuarial calibration against insurer claims remains required before pricing or eligibility use.</p></div>",
)

audit = r'''#!/usr/bin/env python3
import json
import urllib.parse
import urllib.request

BANDS = [
    ('A',1,1),('B',2,3),('C',4,6),('D',7,8),('E',9,11),('F',12,14),('G',15,17),('H',18,19),
    ('I',20,23),('J',24,28),('K',29,32),('L',33,38),('M',39,44),('N',45,55),('O',56,75),
    ('P',76,100),('Q',101,200),('R',201,300),('S',301,400),('T',401,550),('U',551,999),
    ('V',1000,2000),('W',2001,3000),('X',3001,4000),('Y',4001,5000),('Z',5001,10**12),
]

def expected(n):
    for code, low, high in BANDS:
        if low <= n <= high:
            return code
    return None

params = {
    '$select': 'dot_number,legal_name,power_units,fleetsize,mcs150_date,status_code',
    '$where': "power_units is not null AND power_units!='0' AND fleetsize is not null",
    '$limit': '1500',
    '$order': 'dot_number DESC',
}
url = 'https://data.transportation.gov/resource/az4n-8mr2.json?' + urllib.parse.urlencode(params)
request = urllib.request.Request(url, headers={'User-Agent': 'Transport3r fleet audit', 'Accept': 'application/json'})
with urllib.request.urlopen(request, timeout=45) as response:
    rows = json.load(response)

matches = 0
mismatches = []
unknown = []
for row in rows:
    try:
        pu = int(float(str(row.get('power_units','')).replace(',','')))
    except ValueError:
        continue
    actual = str(row.get('fleetsize','')).strip().upper()
    exp = expected(pu)
    if not exp or actual not in {b[0] for b in BANDS}:
        unknown.append({'dot': row.get('dot_number'), 'power_units': pu, 'actual': actual, 'expected': exp})
    elif actual == exp:
        matches += 1
    else:
        mismatches.append({'dot': row.get('dot_number'), 'name': row.get('legal_name'), 'power_units': pu, 'actual': actual, 'expected': exp, 'mcs150_date': row.get('mcs150_date')})

comparable = matches + len(mismatches)
print(json.dumps({
    'sample_rows': len(rows),
    'comparable': comparable,
    'matches': matches,
    'mismatches': len(mismatches),
    'match_rate': round(matches / comparable, 4) if comparable else None,
    'unknown': len(unknown),
    'mismatch_examples': mismatches[:20],
}, indent=2))
if comparable < 100:
    raise SystemExit('Fleet audit returned too few comparable rows')
'''
(ROOT / 'scripts/audit_fleet_consistency.py').write_text(audit, encoding='utf-8')
print('TRI v0.1 patch applied')
