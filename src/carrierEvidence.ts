import {
  DataRow,
  DataSlice,
  SchemaRegistry,
  inspectionId,
  loadSchemaRegistry,
  queryByDot,
  queryByDocketNumbers,
  queryByDotOrInspectionIds,
  readNumber,
  readValue,
} from './datahub';

export const SOURCE_IDS = {
  census: 'az4n-8mr2',
  crash: 'aayw-vxb3',
  inspections: 'fx4q-ay7w',
  units: 'wt8s-2hbx',
  violations: '876r-jsdb',
  specialStudies: '5qik-smay',
  citations: 'qbt8-7vic',
  motusCarrier: 'inys-ebih',
  motusAuthHistory: 'yu5v-wbh6',
  motusInsurance: 'c5y8-a4uz',
  motusInsuranceHistory: '3uet-3z4i',
  motusBoc3: '6snj-ed7q',
  motusRevokeSuspend: 'wb4f-neki',
  motusCarrierDelta: 'nakq-58th',
  motusAuthDelta: 'dm5j-zc6c',
  motusBoc3Delta: 'mhr5-hjyc',
  motusInsuranceDelta: 'x96h-evps',
  motusInsuranceHistoryDelta: 'xe5s-wca7',
  motusRevokeSuspendDelta: 'e67p-xyd5',
  legacyCarrier: '6eyk-hxee',
  legacyInsurance: 'ypjt-5ydn',
  legacyActivePendingInsurance: 'qh9u-swkp',
  legacyAuthHistory: '9mw4-x3tu',
  legacyBoc3: '2emp-mxtb',
  legacyInsuranceHistory: '6sqe-dvqs',
  legacyRejected: '96tg-4mhf',
  legacyRevocation: 'sa6p-acbp',
  smsCensus: 'kjg3-diqy',
  smsInspection: 'rbkj-cgst',
  smsCrash: '4wxs-vbns',
  smsViolation: '8mt8-2mdr',
  smsABPass: 'm3ry-qcip',
  smsCPass: 'h3zn-uid9',
  smsABProperty: '4y6x-dmck',
  smsCProperty: 'h9zy-gjn8',
  newEntrantOos: 'p2mt-9ige',
} as const;

export const UNIT_FIELD_ALIASES = {
  vin: ['INSP_UNIT_VEHICLE_ID_NUMBER', 'VEHICLE_IDENTIFICATION_NUMBER', 'VIN'],
  make: ['INSP_UNIT_MAKE', 'VEHICLE_MAKE', 'MAKE'],
  type: ['INSP_UNIT_TYPE_ID', 'UNIT_TYPE', 'VEHICLE_TYPE'],
  plate: ['INSP_UNIT_LICENSE', 'LICENSE', 'LICENSE_PLATE', 'PLATE'],
  plateState: ['INSP_UNIT_LICENSE_STATE', 'LICENSE_STATE', 'PLATE_STATE', 'STATE'],
  company: ['INSP_UNIT_COMPANY', 'COMPANY', 'UNIT_COMPANY'],
  unitNumber: ['INSP_UNIT_NUMBER', 'UNIT_NUMBER'],
} as const;

export const VIOLATION_FIELD_ALIASES = {
  oos: ['OUT_OF_SERVICE_INDICATOR', 'OOS', 'OOS_IND', 'OOS_FLAG', 'OUT_OF_SERVICE'],
  description: ['VIOL_DESC', 'VIOLATION_DESC', 'DESCRIPTION', 'BASIC_DESC'],
  unit: ['INSP_VIOL_UNIT', 'UNIT_NUMBER', 'INSP_UNIT_NUMBER'],
} as const;

export type EvidenceKey = keyof typeof SOURCE_IDS;
export type CarrierEvidenceMode = 'summary' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence' | 'inspection';

export type CarrierEvidence = {
  dotNumber: string;
  completeAll?: boolean;
  completeAttempted?: boolean;
  inspectionId?: string;
  mode: CarrierEvidenceMode;
  loadedAt: string;
  registry: SchemaRegistry;
  slices: Partial<Record<EvidenceKey, DataSlice>>;
  errors: Partial<Record<EvidenceKey, string>>;
  census?: DataRow;
};

const CHILD_KEYS = new Set<EvidenceKey>(['units', 'violations', 'specialStudies', 'citations']);
const sliceCache = new Map<string, Promise<DataSlice>>();

const MODE_KEYS: Record<CarrierEvidenceMode, EvidenceKey[]> = {
  summary: [
    'inspections', 'violations', 'crash',
    'motusCarrier', 'motusInsurance', 'motusRevokeSuspend',
    'motusCarrierDelta', 'motusAuthDelta', 'motusBoc3Delta',
    'motusInsuranceDelta', 'motusInsuranceHistoryDelta', 'motusRevokeSuspendDelta',
    'smsABProperty', 'smsCProperty', 'smsABPass', 'smsCPass',
    'newEntrantOos',
  ],
  safety: ['inspections', 'violations', 'citations', 'specialStudies', 'crash'],
  fleet: ['inspections', 'units'],
  authority: [
    'motusCarrier', 'motusAuthHistory', 'motusBoc3', 'motusRevokeSuspend',
    'motusCarrierDelta', 'motusAuthDelta', 'motusBoc3Delta', 'motusRevokeSuspendDelta', 'newEntrantOos',
  ],
  insurance: ['motusInsurance', 'motusInsuranceHistory', 'motusInsuranceDelta', 'motusInsuranceHistoryDelta'],
  sms: ['smsCensus', 'smsInspection', 'smsCrash', 'smsViolation', 'smsABPass', 'smsCPass', 'smsABProperty', 'smsCProperty'],
  inspection: ['inspections', 'units', 'violations', 'citations', 'specialStudies'],
  evidence: Object.keys(SOURCE_IDS) as EvidenceKey[],
};

export function evidenceKeys(mode: CarrierEvidenceMode): EvidenceKey[] {
  return [...MODE_KEYS[mode]];
}

function sourceTask(
  registry: SchemaRegistry,
  key: EvidenceKey,
  dotNumber: string,
  inspectionIds: string[],
): Promise<DataSlice> {
  const sourceId = SOURCE_IDS[key];
  if (key === 'inspections') {
    return queryByDot(registry, sourceId, dotNumber, {
      limit: 500,
      orderAliases: ['INSP_DATE', 'INSPECTION_DATE', 'REPORT_DATE'],
      includeTotal: true,
    });
  }
  if (key === 'crash') {
    return queryByDot(registry, sourceId, dotNumber, {
      limit: 350,
      orderAliases: ['CRASH_DATE', 'REPORT_DATE'],
    });
  }
  if (CHILD_KEYS.has(key)) {
    const limit = key === 'violations' ? 5000 : key === 'units' ? 3500 : 2000;
    return queryByDotOrInspectionIds(registry, sourceId, dotNumber, inspectionIds, {
      limit,
      maxInspectionIds: 500,
    });
  }

  const limits: Partial<Record<EvidenceKey, number>> = {
    census: 2,
    motusCarrier: 100,
    motusAuthHistory: 300,
    motusInsurance: 250,
    motusInsuranceHistory: 500,
    motusBoc3: 100,
    motusRevokeSuspend: 300,
    motusCarrierDelta: 50,
    motusAuthDelta: 50,
    motusBoc3Delta: 50,
    motusInsuranceDelta: 50,
    motusInsuranceHistoryDelta: 50,
    motusRevokeSuspendDelta: 50,
    smsCensus: 5,
    smsInspection: 1000,
    smsCrash: 500,
    smsViolation: 2500,
    smsABPass: 5,
    smsCPass: 5,
    smsABProperty: 5,
    smsCProperty: 5,
    newEntrantOos: 100,
  };
  return queryByDot(registry, sourceId, dotNumber, { limit: limits[key] ?? 250 });
}

function cachedSourceTask(
  registry: SchemaRegistry,
  key: EvidenceKey,
  dotNumber: string,
  inspectionIds: string[],
): Promise<DataSlice> {
  const cacheKey = `${dotNumber}:${key}:${CHILD_KEYS.has(key) ? inspectionIds.join(',') : ''}`;
  const existing = sliceCache.get(cacheKey);
  if (existing) return existing;
  const task = sourceTask(registry, key, dotNumber, inspectionIds).catch((cause) => {
    sliceCache.delete(cacheKey);
    throw cause;
  });
  sliceCache.set(cacheKey, task);
  return task;
}

async function capture(
  key: EvidenceKey,
  task: Promise<DataSlice>,
): Promise<{ key: EvidenceKey; slice?: DataSlice; error?: string }> {
  try {
    return { key, slice: await task };
  } catch (cause) {
    return { key, error: cause instanceof Error ? cause.message : String(cause) };
  }
}

export async function loadCarrierEvidence(
  dotNumber: string,
  mode: CarrierEvidenceMode = 'summary',
): Promise<CarrierEvidence> {
  const registry = await loadSchemaRegistry();
  const slices: Partial<Record<EvidenceKey, DataSlice>> = {};
  const errors: Partial<Record<EvidenceKey, string>> = {};
  const requested = [...new Set(MODE_KEYS[mode])];

  let inspectionIds: string[] = [];
  if (requested.includes('inspections') || requested.some((key) => CHILD_KEYS.has(key))) {
    const inspectionResult = await capture('inspections', cachedSourceTask(registry, 'inspections', dotNumber, []));
    if (inspectionResult.slice) {
      slices.inspections = inspectionResult.slice;
      inspectionIds = inspectionResult.slice.rows.map(inspectionId).filter((id): id is string => Boolean(id));
    }
    if (inspectionResult.error) errors.inspections = inspectionResult.error;
  }

  let legacyDockets: string[] = [];
  if (requested.includes('legacyInsurance')) {
    const legacyCarrierResult = await capture('legacyCarrier', cachedSourceTask(registry, 'legacyCarrier', dotNumber, []));
    if (legacyCarrierResult.slice) {
      slices.legacyCarrier = legacyCarrierResult.slice;
      legacyDockets = legacyCarrierResult.slice.rows
        .map((row) => readValue(row, ['DOCKET_NUMBER', 'DOCKET_NO']))
        .filter((value): value is string => Boolean(value));
      legacyDockets = [...new Set(legacyDockets)];
    }
    if (legacyCarrierResult.error) errors.legacyCarrier = legacyCarrierResult.error;
  }

  const remaining = requested.filter((key) =>
    key !== 'inspections' && key !== 'legacyCarrier' && key !== 'legacyInsurance'
  );
  const results = await Promise.all(
    remaining.map((key) => {
      if (CHILD_KEYS.has(key) && errors.inspections) {
        return Promise.resolve({ key, error: 'Parent inspections unavailable; child evidence was not queried.' });
      }
      return capture(key, cachedSourceTask(registry, key, dotNumber, inspectionIds));
    }),
  );
  for (const result of results) {
    if ('slice' in result && result.slice) {
      const incompleteParents = CHILD_KEYS.has(result.key) && (slices.inspections?.truncated || inspectionIds.length < (slices.inspections?.rows.length ?? 0));
      slices[result.key] = incompleteParents ? { ...result.slice, truncated: true, total: null } : result.slice;
    }
    if (result.error) errors[result.key] = result.error;
  }

  if (requested.includes('legacyInsurance') && errors.legacyCarrier) {
    errors.legacyInsurance = 'Legacy carrier/docket bridge unavailable; historical filings were not queried.';
  } else if (requested.includes('legacyInsurance')) {
    const legacyInsuranceResult = await capture(
      'legacyInsurance',
      queryByDocketNumbers(registry, SOURCE_IDS.legacyInsurance, legacyDockets, {
        limitPerChunk: 2000,
        maxDocketNumbers: 100,
      }),
    );
    if (legacyInsuranceResult.slice) slices.legacyInsurance = slices.legacyCarrier?.truncated
      ? { ...legacyInsuranceResult.slice, truncated: true, total: null } : legacyInsuranceResult.slice;
    if (legacyInsuranceResult.error) errors.legacyInsurance = legacyInsuranceResult.error;
  }

  return {
    dotNumber,
    mode,
    loadedAt: new Date().toISOString(),
    registry,
    slices,
    errors,
  };
}

export function clearCarrierEvidenceCache(dotNumber?: string): void {
  for (const key of [...sliceCache.keys()]) {
    if (!dotNumber || key.startsWith(`${dotNumber}:`)) sliceCache.delete(key);
  }
}

export function rowCount(slice?: DataSlice): number {
  return slice?.total ?? slice?.rows.length ?? 0;
}

export function rowCountLabel(slice?: DataSlice): string {
  if (!slice) return '—';
  const count = slice.total ?? slice.rows.length;
  return `${count.toLocaleString()}${slice.truncated && slice.total === null ? '+' : ''}`;
}

export function loadedRowCountLabel(slice?: DataSlice): string {
  return slice ? slice.rows.length.toLocaleString() : '—';
}

export function inspectionCountDetail(slice?: DataSlice): string {
  if (!slice) return 'Inspection source unavailable';
  if (slice.rows.length === 0 && !slice.truncated) return 'No rows returned for this USDOT; not proof of no inspections';
  const loaded = loadedRowCountLabel(slice);
  return `Published daily file · ${loaded} recent rows loaded${slice.truncated && slice.total === null ? ' · total unavailable' : ''}; not a SAFER 24-month count`;
}

export function inspectionAvailability(evidence: CarrierEvidence): string | null {
  const slice = evidence.slices.inspections;
  if (evidence.errors.inspections || !slice) return 'Inspection source unavailable. The app cannot determine how many inspection records exist.';
  if (slice.rows.length === 0) return slice.truncated
    ? 'No inspection rows in the loaded window; source coverage is incomplete.'
    : 'No inspection rows returned for this USDOT from the published daily file. This does not prove no inspections ever occurred or that the carrier is low risk.';
  return null;
}

export function evidenceIssues(evidence: CarrierEvidence): Array<{ key: EvidenceKey; message: string }> {
  return MODE_KEYS[evidence.mode].flatMap((key) => {
    if (evidence.errors[key]) return [{ key, message: evidence.errors[key]! }];
    const slice = evidence.slices[key];
    if (!slice) return [{ key, message: 'Source evidence was not returned.' }];
    return slice.truncated ? [{ key, message: 'Loaded evidence is partial; the returned rows are not a complete total.' }] : [];
  });
}

export function sourceEmptyMessage(evidence: CarrierEvidence, key: EvidenceKey, empty = 'No rows returned.'): string {
  if (evidence.errors[key] || !evidence.slices[key]) return 'Source unavailable; record absence cannot be determined.';
  if (evidence.slices[key]?.truncated) return 'No rows in the loaded window; source coverage is partial.';
  return empty;
}

export function authorityStatusLabel(evidence: CarrierEvidence): string {
  if (evidence.errors.motusCarrier || !evidence.slices.motusCarrier) return 'Current MOTUS authority unavailable';
  const statuses = authorityStatuses(evidence);
  if (statuses.length) return statuses.join(', ');
  return evidence.slices.motusCarrier.truncated ? 'No authority status in the loaded window' : 'No current MOTUS authority status row returned';
}

export function aggregateRows(evidence: CarrierEvidence | null, keys: EvidenceKey[]): { loaded: number; complete: boolean; label: string } {
  const loaded = keys.reduce((sum, key) => sum + (evidence?.slices[key]?.rows.length ?? 0), 0);
  const complete = keys.length > 0 && keys.every((key) => Boolean(evidence?.slices[key] && !evidence.errors[key] && !evidence.slices[key]?.truncated));
  return { loaded, complete, label: complete ? loaded.toLocaleString() : loaded > 0 ? `${loaded.toLocaleString()}+` : '—' };
}

export function observedVinCountLabel(evidence: CarrierEvidence | null): string {
  if (!evidence?.slices.units || evidence.errors.units) return '—';
  return `${observedVins(evidence).length.toLocaleString()}${evidence.slices.units.truncated ? '+' : ''}`;
}

export function truthyFlag(value?: string): boolean {
  if (!value) return false;
  return ['Y', 'YES', '1', 'TRUE', 'T', 'OOS'].includes(value.trim().toUpperCase());
}

export function observedVins(evidence: CarrierEvidence | null): string[] {
  const values = (evidence?.slices.units?.rows ?? [])
    .map((row) => readValue(row, [...UNIT_FIELD_ALIASES.vin]))
    .filter((value): value is string => Boolean(value && value.length >= 6));
  return [...new Set(values)];
}

export function oosViolationCount(evidence: CarrierEvidence | null): number | null {
  const slice = evidence?.slices.violations;
  if (!slice || evidence?.errors.violations) return null;
  const flags = slice.rows.map((row) => readValue(row, [...VIOLATION_FIELD_ALIASES.oos]));
  if (flags.some((flag) => !flag || !['Y','YES','1','TRUE','T','OOS','N','NO','0','FALSE','F'].includes(flag.trim().toUpperCase()))) return null;
  return flags.filter(truthyFlag).length;
}

export function severeCrashCounts(evidence: CarrierEvidence | null): { fatal: number | null; injury: number | null; tow: number | null; incomplete: boolean } {
  const slice = evidence?.slices.crash;
  if (!slice || evidence?.errors.crash) return { fatal: null, injury: null, tow: null, incomplete: true };
  const fatalities = slice.rows.map((row) => readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT', 'FATAL_CNT']));
  const injuries = slice.rows.map((row) => readNumber(row, ['INJURIES', 'INJURY_CNT', 'INJURY_COUNT', 'INJ_CNT']));
  const tows = slice.rows.map((row) => readValue(row, ['TOW_AWAY', 'TOWAWAY', 'TOW_AWAY_FLAG']));
  const count = (values: Array<boolean | null>) => {
    const positives = values.filter((value) => value === true).length;
    return positives || !values.includes(null) ? positives : null;
  };
  const numberFlag = (value: number | null) => value === null || value < 0 || !Number.isInteger(value) ? null : value > 0;
  const towFlags = tows.map((value) => value && ['Y','YES','1','TRUE','T','N','NO','0','FALSE','F'].includes(value.trim().toUpperCase()) ? truthyFlag(value) : null);
  return { fatal: count(fatalities.map(numberFlag)), injury: count(injuries.map(numberFlag)), tow: count(towFlags),
    incomplete: slice.truncated || [...fatalities.map(numberFlag), ...injuries.map(numberFlag), ...towFlags].includes(null) };
}

export function authorityStatuses(evidence: CarrierEvidence | null): string[] {
  const statuses = (evidence?.slices.motusCarrier?.rows ?? [])
    .map((row) => readValue(row, ['OP_AUTH_STATUS', 'AUTH_STATUS', 'OPERATING_AUTHORITY_STATUS']))
    .filter((value): value is string => Boolean(value));
  return [...new Set(statuses)];
}

export function activeInsuranceRows(evidence: CarrierEvidence | null): DataRow[] {
  return evidence?.slices.motusInsurance?.rows ?? [];
}

export const SMS_OUTPUT_KEYS = ['smsABProperty', 'smsCProperty', 'smsABPass', 'smsCPass'] as const;

// The general AB/C files include property AND passenger carriers. Passenger files
// are overlapping, more specific outputs, not a mutually exclusive fifth class.
export function selectOfficialSmsOutput(evidence: CarrierEvidence | null): {
  row: DataRow | null; sourceId: string | null; issues: string[];
} {
  const issues: string[] = [];
  for (const key of SMS_OUTPUT_KEYS) {
    const slice = evidence?.slices[key];
    if (!slice || evidence?.errors[key] || slice.truncated) issues.push(`INCOMPLETE_SMS_OUTPUT:${key}`);
    if ((slice?.rows.length ?? 0) > 1) issues.push(`DUPLICATE_SMS_OUTPUT:${key}`);
    if (slice?.rows.some(row => !evidence?.dotNumber || readValue(row, ['DOT_NUMBER'])?.trim() !== evidence.dotNumber)) issues.push(`SMS_OUTPUT_IDENTITY_MISMATCH:${key}`);
  }
  const rowFor = (key: typeof SMS_OUTPUT_KEYS[number]) => evidence?.slices[key]?.rows[0];
  const ab = rowFor('smsABPass') ?? rowFor('smsABProperty');
  const c = rowFor('smsCPass') ?? rowFor('smsCProperty');
  if (ab && c) issues.push('CONFLICTING_SMS_OPERATION_POPULATIONS');
  for (const [general, passenger] of [['smsABProperty','smsABPass'], ['smsCProperty','smsCPass']] as const) {
    const generalRow = rowFor(general), passengerRow = rowFor(passenger);
    if (!generalRow || !passengerRow) continue;
    for (const field of ['unsafe_driv_measure','hos_driv_measure','driv_fit_measure','contr_subst_measure','veh_maint_measure','hm_measure']) {
      const left = readValue(generalRow, [field]), right = readValue(passengerRow, [field]);
      if (left !== undefined && right !== undefined && (readNumber(generalRow, [field]) === null || readNumber(passengerRow, [field]) === null || readNumber(generalRow, [field]) !== readNumber(passengerRow, [field]))) issues.push(`CONFLICTING_SMS_MEASURE:${field}`);
    }
  }
  if (issues.length) return { row: null, sourceId: null, issues };
  const key = SMS_OUTPUT_KEYS.find(key => key.endsWith('Pass') && rowFor(key)) ?? SMS_OUTPUT_KEYS.find(key => rowFor(key));
  return { row: key ? rowFor(key)! : null, sourceId: key ? SOURCE_IDS[key] : null, issues };
}

export function officialSmsRows(evidence: CarrierEvidence | null): DataRow[] {
  const { row } = selectOfficialSmsOutput(evidence);
  return row ? [row] : [];
}

export function officialSmsSourceId(evidence: CarrierEvidence | null): string | null {
  return selectOfficialSmsOutput(evidence).sourceId;
}

export const MOTUS_DELTA_KEYS: EvidenceKey[] = ['motusCarrierDelta', 'motusAuthDelta', 'motusBoc3Delta', 'motusInsuranceDelta', 'motusInsuranceHistoryDelta', 'motusRevokeSuspendDelta'];
