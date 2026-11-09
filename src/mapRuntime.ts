/** Register the lazy browser renderer at the entrypoint; model/SSR tests do not bundle WebGL. */
type Module = typeof import('maplibre-gl');
let loader: (() => Promise<Module>) | undefined;
let pending: Promise<Module> | undefined;
export function configureMapLoader(value: () => Promise<Module>): void { loader = value; pending = undefined; }
export function loadMapRenderer(): Promise<Module> {
  if (!loader) return Promise.reject(new Error('Interactive map renderer is not configured'));
  if (!pending) pending = loader().catch(error => {pending = undefined; throw error;});
  return pending;
}
