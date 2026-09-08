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

export type EvidenceKey = keyof typeof SOURCE_IDS;
export type CarrierEvidenceMode = 'summary' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence' | 'inspection';

export type CarrierEvidence = {
  dotNumber: string;
  mode: CarrierEvidenceMode;
  loadedAt: string;
  registry: SchemaRegistry;
  slices: Partial<Record<EvidenceKey, DataSlice>>;
  errors: Partial<Record<EvidenceKey, string>>;
};

const CHILD_KEYS = new Set<EvidenceKey>(['units', 'violations', 'specialStudies', 'citations']);
const sliceCache = new Map<string, Promise<DataSlice>>();

const MODE_KEYS: Record<CarrierEvidenceMode, EvidenceKey[]> = {
  summary: [
    'inspections', 'violations', 'crash',
    'motusCarrier', 'motusInsurance', 'motusRevokeSuspend',
    'motusInsuranceDelta', 'motusRevokeSuspendDelta',
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
  inspection: ['inspections', 'units', 'violations', 'citations'],
  evidence: Object.keys(SOURCE_IDS) as EvidenceKey[],
};

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
      maxInspectionIds: 250,
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
  const cacheKey = `${dotNumber}:${key}`;
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
    remaining.map((key) => capture(key, cachedSourceTask(registry, key, dotNumber, inspectionIds))),
  );
  for (const result of results) {
    if (result.slice) slices[result.key] = result.slice;
    if (result.error) errors[result.key] = result.error;
  }

  if (requested.includes('legacyInsurance')) {
    const legacyInsuranceResult = await capture(
      'legacyInsurance',
      queryByDocketNumbers(registry, SOURCE_IDS.legacyInsurance, legacyDockets, {
        limitPerChunk: 2000,
        maxDocketNumbers: 100,
      }),
    );
    if (legacyInsuranceResult.slice) slices.legacyInsurance = legacyInsuranceResult.slice;
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
  if (!slice) return '0';
  const count = slice.total ?? slice.rows.length;
  return `${count.toLocaleString()}${slice.truncated && slice.total === null ? '+' : ''}`;
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

export function oosViolationCount(evidence: CarrierEvidence | null): number {
  return (evidence?.slices.violations?.rows ?? []).filter((row) =>
    truthyFlag(readValue(row, ['OOS', 'OOS_IND', 'OOS_FLAG', 'OUT_OF_SERVICE'])),
  ).length;
}

export function severeCrashCounts(evidence: CarrierEvidence | null): { fatal: number; injury: number; tow: number } {
  let fatal = 0;
  let injury = 0;
  let tow = 0;
  for (const row of evidence?.slices.crash?.rows ?? []) {
    const fatalities = readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT', 'FATAL_CNT']) ?? 0;
    const injuries = readNumber(row, ['INJURIES', 'INJURY_CNT', 'INJURY_COUNT', 'INJ_CNT']) ?? 0;
    if (fatalities > 0) fatal += 1;
    if (injuries > 0) injury += 1;
    if (truthyFlag(readValue(row, ['TOW_AWAY', 'TOWAWAY', 'TOW_AWAY_FLAG']))) tow += 1;
  }
  return { fatal, injury, tow };
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

export function officialSmsRows(evidence: CarrierEvidence | null): DataRow[] {
  const candidates: EvidenceKey[] = ['smsABProperty', 'smsCProperty', 'smsABPass', 'smsCPass'];
  for (const key of candidates) {
    const rows = evidence?.slices[key]?.rows ?? [];
    if (rows.length) return rows;
  }
  return [];
}

export function officialSmsSourceId(evidence: CarrierEvidence | null): string | null {
  const candidates: EvidenceKey[] = ['smsABProperty', 'smsCProperty', 'smsABPass', 'smsCPass'];
  for (const key of candidates) {
    if ((evidence?.slices[key]?.rows.length ?? 0) > 0) return SOURCE_IDS[key];
  }
  return null;
}

export function recentChangeCount(evidence: CarrierEvidence | null): number {
  return [
    evidence?.slices.motusCarrierDelta,
    evidence?.slices.motusAuthDelta,
    evidence?.slices.motusBoc3Delta,
    evidence?.slices.motusInsuranceDelta,
    evidence?.slices.motusInsuranceHistoryDelta,
    evidence?.slices.motusRevokeSuspendDelta,
  ].reduce((sum, slice) => sum + rowCount(slice), 0);
}
