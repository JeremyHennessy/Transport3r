import { SOURCE_IDS, UNIT_FIELD_ALIASES, type CarrierEvidence, type EvidenceKey } from './carrierEvidence';
import { inspectionId, loadSchemaRegistry, queryByInspectionIds, readValue, type DataRow } from './datahub';

const CHILD_KEYS = ['units', 'violations', 'citations', 'specialStudies'] as const;

export async function loadInspectionEvidence(dotNumber: string, id: string): Promise<CarrierEvidence> {
  if (!/^[1-9]\d*$/.test(dotNumber) || !/^[1-9]\d*$/.test(id)) throw new Error('Positive USDOT and inspection identifiers are required.');
  const registry = await loadSchemaRegistry();
  const result: CarrierEvidence = { dotNumber, inspectionId: id, mode: 'inspection', registry, slices: {}, errors: {}, loadedAt: '' };
  try {
    const parent = await queryByInspectionIds(registry, SOURCE_IDS.inspections, [id], { maxInspectionIds: 1, limitPerChunk: 2 });
    if (parent.truncated || parent.rows.length > 1) throw new Error('Inspection identity is ambiguous in the source.');
    if (parent.rows.some(row => inspectionId(row) !== id || readValue(row, ['DOT_NUMBER']) !== dotNumber)) {
      throw new Error('This inspection does not belong to the requested USDOT.');
    }
    result.slices.inspections = { ...parent, scope: 'inspection' };
    if (!parent.rows.length) {
      for (const key of CHILD_KEYS) result.errors[key] = 'Parent inspection was not returned; child evidence was not queried.';
    } else {
      await Promise.all(CHILD_KEYS.map(async key => {
        try {
          const slice = await queryByInspectionIds(registry, SOURCE_IDS[key], [id], { maxInspectionIds: 1, limitPerChunk: 5000 });
          if (slice.rows.some(row => inspectionId(row) !== id || (readValue(row,['DOT_NUMBER']) !== undefined && readValue(row,['DOT_NUMBER']) !== dotNumber))) {
            throw new Error('Child source returned an unrelated inspection or carrier.');
          }
          result.slices[key] = { ...slice, scope: 'inspection' };
        } catch (error) {
          result.errors[key] = error instanceof Error ? error.message : String(error);
        }
      }));
    }
  } catch (error) {
    result.errors.inspections = error instanceof Error ? error.message : String(error);
    for (const key of CHILD_KEYS) result.errors[key] = 'Parent inspection could not be verified; child evidence was not queried.';
  }
  result.loadedAt = new Date().toISOString();
  return result;
}

export function observedVinRows(evidence: CarrierEvidence, vin: string) {
  const parents = new Map<string, DataRow>();
  const ambiguous = new Set<string>();
  for (const row of evidence.errors.inspections ? [] : evidence.slices.inspections?.rows ?? []) {
    const id = inspectionId(row);
    if (!id || readValue(row,['DOT_NUMBER']) !== evidence.dotNumber) continue;
    if (parents.has(id)) ambiguous.add(id);
    parents.set(id,row);
  }
  const requested = vin.trim().toUpperCase();
  const candidates = (evidence.errors.units ? [] : evidence.slices.units?.rows ?? []).filter(row =>
    readValue(row,[...UNIT_FIELD_ALIASES.vin])?.trim().toUpperCase() === requested);
  const rows = candidates.flatMap(unit => {
    const id = inspectionId(unit), parent = id && !ambiguous.has(id) ? parents.get(id) : undefined;
    const childDot = readValue(unit,['DOT_NUMBER']);
    return parent && (childDot === undefined || childDot === evidence.dotNumber) ? [{ unit, parent, inspectionId: id! }] : [];
  });
  return { rows, rejected: candidates.length - rows.length,
    incomplete: (['units','inspections'] as EvidenceKey[]).some(key => evidence.errors[key] || !evidence.slices[key] || evidence.slices[key]?.truncated) };
}
