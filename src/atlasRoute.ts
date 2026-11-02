/** Stable, shareable public USDOT atlas routes. Never interpret invalid IDs as safe. */
export function atlasDotFromHash(hash: string): string {
  if (!/^#\/atlas(?:\?|$)/.test(hash)) return '';
  const query = hash.split('?')[1] ?? '';
  const raw = new URLSearchParams(query).get('dot') ?? '';
  return /^[1-9][0-9]{0,9}$/.test(raw) ? raw : '';
}
export function atlasHash(dot: string): string {
  if (!/^[1-9][0-9]{0,9}$/.test(dot)) throw new Error('A valid USDOT is required');
  return '#/atlas?dot=' + encodeURIComponent(dot);
}
