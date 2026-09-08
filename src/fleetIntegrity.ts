export type FleetBandCode =
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
