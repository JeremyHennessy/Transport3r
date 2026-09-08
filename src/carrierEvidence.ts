import {
  DataRow,
  DataSlice,
  SchemaRegistry,
  inspectionId,
  loadSchemaRegistry,
  queryByDot,
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
  citations: 'qbt8-7vic',
  motusCarrier: 'inys-ebih',
  motusAuthHistory: 'yu5v-wbh6',
  motusInsurance: 'c5y8-a4uz',
  motusInsuranceHistory: '3uet-3z4i',
  motusRevokeSuspend: 'wb4f-neki',
  smsCensus: 'kjg3-diqy',
  smsInspection: 'rbkj-cgst',
  smsCrash: '4wxs-vbns',
  smsViolation: '8mt8-2mdr',
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

export type CarrierEvidence = {
  dotNumber: string;
  loadedAt: string;
  registry: SchemaRegistry;
  slices: Partial<Record<EvidenceKey, DataSlice>>;
  errors: Partial<Record<EvidenceKey, string>>;
};

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

export async function loadCarrierEvidence(dotNumber: string): Promise<CarrierEvidence> {
  const registry = await loadSchemaRegistry();
  const slices: Partial<Record<EvidenceKey, DataSlice>> = {};
  const errors: Partial<Record<EvidenceKey, string>> = {};

  const inspectionResult = await capture(
    'inspections',
    queryByDot(registry, SOURCE_IDS.inspections, dotNumber, {
      limit: 750,
      orderAliases: ['INSP_DATE', 'INSPECTION_DATE', 'REPORT_DATE'],
    }),
  );
  if (inspectionResult.slice) slices.inspections = inspectionResult.slice;
  if (inspectionResult.error) errors.inspections = inspectionResult.error;

  const inspectionIds = (slices.inspections?.rows ?? [])
    .map(inspectionId)
    .filter((id): id is string => Boolean(id));

  const tasks: Array<Promise<{ key: EvidenceKey; slice?: DataSlice; error?: string }>> = [
    capture(
      'crash',
      queryByDot(registry, SOURCE_IDS.crash, dotNumber, {
        limit: 500,
        orderAliases: ['CRASH_DATE', 'REPORT_DATE'],
      }),
    ),
    capture('units', queryByDotOrInspectionIds(registry, SOURCE_IDS.units, dotNumber, inspectionIds, { limit: 5000 })),
    capture('violations', queryByDotOrInspectionIds(registry, SOURCE_IDS.violations, dotNumber, inspectionIds, { limit: 5000 })),
    capture('citations', queryByDotOrInspectionIds(registry, SOURCE_IDS.citations, dotNumber, inspectionIds, { limit: 2500 })),
    capture('motusCarrier', queryByDot(registry, SOURCE_IDS.motusCarrier, dotNumber, { limit: 100 })),
    capture('motusAuthHistory', queryByDot(registry, SOURCE_IDS.motusAuthHistory, dotNumber, { limit: 250 })),
    capture('motusInsurance', queryByDot(registry, SOURCE_IDS.motusInsurance, dotNumber, { limit: 250 })),
    capture('motusInsuranceHistory', queryByDot(registry, SOURCE_IDS.motusInsuranceHistory, dotNumber, { limit: 500 })),
    capture('motusRevokeSuspend', queryByDot(registry, SOURCE_IDS.motusRevokeSuspend, dotNumber, { limit: 250 })),
    capture('smsCensus', queryByDot(registry, SOURCE_IDS.smsCensus, dotNumber, { limit: 5 })),
    capture('smsInspection', queryByDot(registry, SOURCE_IDS.smsInspection, dotNumber, { limit: 1000 })),
    capture('smsCrash', queryByDot(registry, SOURCE_IDS.smsCrash, dotNumber, { limit: 500 })),
    capture('smsViolation', queryByDot(registry, SOURCE_IDS.smsViolation, dotNumber, { limit: 2500 })),
    capture('smsABProperty', queryByDot(registry, SOURCE_IDS.smsABProperty, dotNumber, { limit: 5 })),
    capture('smsCProperty', queryByDot(registry, SOURCE_IDS.smsCProperty, dotNumber, { limit: 5 })),
    capture('newEntrantOos', queryByDot(registry, SOURCE_IDS.newEntrantOos, dotNumber, { limit: 100 })),
  ];

  for (const result of await Promise.all(tasks)) {
    if (result.slice) slices[result.key] = result.slice;
    if (result.error) errors[result.key] = result.error;
  }

  return {
    dotNumber,
    loadedAt: new Date().toISOString(),
    registry,
    slices,
    errors,
  };
}

export function rowCount(slice?: DataSlice): number {
  return slice?.total ?? slice?.rows.length ?? 0;
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
  const ab = evidence?.slices.smsABProperty?.rows ?? [];
  return ab.length ? ab : evidence?.slices.smsCProperty?.rows ?? [];
}
