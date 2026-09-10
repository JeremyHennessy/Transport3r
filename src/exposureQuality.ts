import { parseDateValue } from './datahub';

type Exposure = { powerUnits?: string; drivers?: string; mcs150Date?: string; statusCode?: string; mileage?: string; mileageYear?: string };
const count = (raw?: string) => {
  if (!raw?.trim()) return null;
  const value = Number(raw.replaceAll(',', ''));
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
};

/** Review heuristics, not corrected exposure or a proprietary risk score. */
export function exposureQualityFlags(row: Exposure, today = new Date()): string[] {
  const flags: string[] = [], units = count(row.powerUnits), drivers = count(row.drivers);
  if (units === null) flags.push('Power units missing or invalid.');
  if (drivers === null) flags.push('Driver count missing or invalid.');
  if (row.statusCode !== 'A') flags.push('Registration is not confirmed active; counts may not reflect current operations.');
  const report = parseDateValue(row.mcs150Date), cutoff = new Date(today);
  cutoff.setUTCFullYear(cutoff.getUTCFullYear() - 2);
  if (!report) flags.push('MCS-150 report date missing or invalid.');
  else if (report > today) flags.push('MCS-150 report date is in the future.');
  else if (report < cutoff) flags.push('MCS-150 report is more than two years old.');
  if (units !== null && drivers !== null && units >= 20 && (drivers === 0 || units > drivers * 10)) flags.push('At least 20 power units and over 10 units per driver, or zero drivers: reconcile reported exposure.');
  if (units !== null && units > 0 && drivers !== null && drivers >= 20 && drivers > units * 10) flags.push('At least 20 drivers and over 10 drivers per power unit: reconcile reported exposure.');
  if (units === 0 && drivers !== null && drivers > 0) flags.push('Drivers reported with zero power units; verify operation and reporting scope.');
  const year = Number(row.mileageYear);
  if (!row.mileageYear || !/^\d{4}$/.test(row.mileageYear) || year < 1900 || year > today.getUTCFullYear()) flags.push('Mileage year missing or invalid.');
  else if (year < today.getUTCFullYear() - 2) flags.push('Mileage year is more than two years old.');
  if (count(row.mileage) === null) flags.push('Mileage missing or invalid.');
  return flags;
}
