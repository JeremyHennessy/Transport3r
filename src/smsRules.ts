export const SMS_RULESET = {
  id: 'SMS_3_21_CURRENT',
  version: '3.21',
  published: '2026-06',
  status: 'ACTIVE',
} as const;

export type SmsBasicKey = 'unsafe' | 'hos' | 'driverFitness' | 'controlledSubstances' | 'vehicleMaintenance' | 'hazmat' | 'crash';
export type InspectionMeasureBasicKey = 'hos' | 'driverFitness' | 'controlledSubstances' | 'vehicleMaintenance' | 'hazmat';
export type CarrierSegment = 'COMBO' | 'STRAIGHT';

export type SmsBasicRule = {
  key: SmsBasicKey;
  label: string;
  violationBasicMatches: string[];
  relevantInspectionField?: string;
  officialMeasureField?: string;
  sufficientRelevantInspections?: number;
  sufficientViolationInspections?: number;
  interventionThresholds: { passenger: number; hazmat: number; general: number };
};

export const SMS_BASIC_RULES: Record<SmsBasicKey, SmsBasicRule> = {
  unsafe: {
    key: 'unsafe',
    label: 'Unsafe Driving',
    violationBasicMatches: ['unsafe driving'],
    relevantInspectionField: 'unsafe_insp',
    officialMeasureField: 'unsafe_driv_measure',
    sufficientViolationInspections: 3,
    interventionThresholds: { passenger: 50, hazmat: 60, general: 65 },
  },
  hos: {
    key: 'hos',
    label: 'Hours-of-Service Compliance',
    violationBasicMatches: ['hours-of-service', 'hours of service', 'hos compliance'],
    relevantInspectionField: 'fatigued_insp',
    officialMeasureField: 'hos_driv_measure',
    sufficientRelevantInspections: 3,
    sufficientViolationInspections: 1,
    interventionThresholds: { passenger: 50, hazmat: 60, general: 65 },
  },
  driverFitness: {
    key: 'driverFitness',
    label: 'Driver Fitness',
    violationBasicMatches: ['driver fitness'],
    relevantInspectionField: 'dr_fitness_insp',
    officialMeasureField: 'driv_fit_measure',
    sufficientRelevantInspections: 5,
    sufficientViolationInspections: 1,
    interventionThresholds: { passenger: 65, hazmat: 75, general: 80 },
  },
  controlledSubstances: {
    key: 'controlledSubstances',
    label: 'Controlled Substances/Alcohol',
    violationBasicMatches: ['controlled substances/alcohol', 'controlled substances and alcohol', 'drugs/alcohol'],
    relevantInspectionField: 'subt_alcohol_insp',
    officialMeasureField: 'contr_subst_measure',
    interventionThresholds: { passenger: 65, hazmat: 75, general: 80 },
  },
  vehicleMaintenance: {
    key: 'vehicleMaintenance',
    label: 'Vehicle Maintenance',
    violationBasicMatches: ['vehicle maintenance', 'vehicle maint'],
    relevantInspectionField: 'vh_maint_insp',
    officialMeasureField: 'veh_maint_measure',
    sufficientRelevantInspections: 5,
    sufficientViolationInspections: 1,
    interventionThresholds: { passenger: 65, hazmat: 75, general: 80 },
  },
  hazmat: {
    key: 'hazmat',
    label: 'Hazardous Materials Compliance',
    violationBasicMatches: ['hazardous materials compliance', 'hazmat compliance', 'hm compliance'],
    relevantInspectionField: 'hm_insp',
    sufficientRelevantInspections: 5,
    sufficientViolationInspections: 1,
    interventionThresholds: { passenger: 80, hazmat: 80, general: 80 },
  },
  crash: {
    key: 'crash',
    label: 'Crash Indicator',
    violationBasicMatches: [],
    interventionThresholds: { passenger: 50, hazmat: 60, general: 65 },
  },
};

export const INSPECTION_MEASURE_BASICS: InspectionMeasureBasicKey[] = [
  'hos',
  'driverFitness',
  'controlledSubstances',
  'vehicleMaintenance',
  'hazmat',
];

export const SAFETY_EVENT_GROUPS = {
  hos: [
    { group: 1, min: 3, max: 10 },
    { group: 2, min: 11, max: 20 },
    { group: 3, min: 21, max: 100 },
    { group: 4, min: 101, max: 500 },
    { group: 5, min: 501, max: Number.POSITIVE_INFINITY },
  ],
  driverFitness: [
    { group: 1, min: 5, max: 10 },
    { group: 2, min: 11, max: 20 },
    { group: 3, min: 21, max: 100 },
    { group: 4, min: 101, max: 500 },
    { group: 5, min: 501, max: Number.POSITIVE_INFINITY },
  ],
  vehicleMaintenance: [
    { group: 1, min: 5, max: 10 },
    { group: 2, min: 11, max: 20 },
    { group: 3, min: 21, max: 100 },
    { group: 4, min: 101, max: 500 },
    { group: 5, min: 501, max: Number.POSITIVE_INFINITY },
  ],
  hazmat: [
    { group: 1, min: 5, max: 10 },
    { group: 2, min: 11, max: 15 },
    { group: 3, min: 16, max: 40 },
    { group: 4, min: 41, max: 100 },
    { group: 5, min: 101, max: Number.POSITIVE_INFINITY },
  ],
  controlledSubstances: [
    { group: 1, min: 1, max: 1 },
    { group: 2, min: 2, max: 2 },
    { group: 3, min: 3, max: 3 },
    { group: 4, min: 4, max: Number.POSITIVE_INFINITY },
  ],
  unsafe: {
    COMBO: [
      { group: 1, min: 3, max: 8 },
      { group: 2, min: 9, max: 21 },
      { group: 3, min: 22, max: 57 },
      { group: 4, min: 58, max: 149 },
      { group: 5, min: 150, max: Number.POSITIVE_INFINITY },
    ],
    STRAIGHT: [
      { group: 1, min: 3, max: 4 },
      { group: 2, min: 5, max: 8 },
      { group: 3, min: 9, max: 18 },
      { group: 4, min: 19, max: 49 },
      { group: 5, min: 50, max: Number.POSITIVE_INFINITY },
    ],
  },
  crash: {
    COMBO: [
      { group: 1, min: 2, max: 3 },
      { group: 2, min: 4, max: 6 },
      { group: 3, min: 7, max: 16 },
      { group: 4, min: 17, max: 45 },
      { group: 5, min: 46, max: Number.POSITIVE_INFINITY },
    ],
    STRAIGHT: [
      { group: 1, min: 2, max: 2 },
      { group: 2, min: 3, max: 4 },
      { group: 3, min: 5, max: 8 },
      { group: 4, min: 9, max: 26 },
      { group: 5, min: 27, max: Number.POSITIVE_INFINITY },
    ],
  },
} as const;

export function safetyEventGroup(basic: InspectionMeasureBasicKey, eventCount: number): number | null {
  const groups = SAFETY_EVENT_GROUPS[basic];
  const match = groups.find((group) => eventCount >= group.min && eventCount <= group.max);
  return match?.group ?? null;
}

export function unsafeSafetyEventGroup(segment: CarrierSegment, inspectionsWithViolations: number): number | null {
  const match = SAFETY_EVENT_GROUPS.unsafe[segment].find((group) => inspectionsWithViolations >= group.min && inspectionsWithViolations <= group.max);
  return match?.group ?? null;
}

export function crashSafetyEventGroup(segment: CarrierSegment, crashes: number): number | null {
  const match = SAFETY_EVENT_GROUPS.crash[segment].find((group) => crashes >= group.min && crashes <= group.max);
  return match?.group ?? null;
}

export function utilizationFactor(segment: CarrierSegment, vmtPerAveragePu: number | null): number {
  if (vmtPerAveragePu === null || !Number.isFinite(vmtPerAveragePu)) return 1;
  if (segment === 'COMBO') {
    if (vmtPerAveragePu < 80_000) return 1;
    if (vmtPerAveragePu <= 160_000) return 1 + 0.6 * ((vmtPerAveragePu - 80_000) / 80_000);
    if (vmtPerAveragePu <= 200_000) return 1.6;
    return 1;
  }
  if (vmtPerAveragePu < 20_000) return 1;
  if (vmtPerAveragePu <= 60_000) return vmtPerAveragePu / 20_000;
  if (vmtPerAveragePu <= 200_000) return 3;
  return 1;
}

export function crashSeverityWeight({ towAway, injuryCount, fatalityCount, hazmatReleased }: { towAway: boolean; injuryCount: number; fatalityCount: number; hazmatReleased: boolean }): number {
  const base = injuryCount > 0 || fatalityCount > 0 ? 2 : towAway ? 1 : 0;
  return base + (hazmatReleased && base > 0 ? 1 : 0);
}
