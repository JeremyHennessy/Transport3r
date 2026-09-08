import { FormEvent, useEffect, useMemo, useState } from 'react';
import { DataRow, readValue } from './datahub';

type SortMode = 'fleet_desc' | 'dot_desc' | 'name_asc';

type DirectoryFilters = {
  q: string;
  state: string;
  operation: string;
  hazmat: string;
  minFleetCode: string;
  sort: SortMode;
};

type Carrier = {
  dotNumber: string;
  legalName: string;
  dbaName?: string;
  city?: string;
  state?: string;
  operation?: string;
  powerUnits?: string;
  drivers?: string;
  mileage?: string;
  mileageYear?: string;
  hazmat?: string;
  fleetSizeCode?: string;
};

const DATAHUB = 'https://data.transportation.gov/resource';
const PAGE_SIZE = 100;
const DEFAULT_FILTERS: DirectoryFilters = {
  q: '',
  state: '',
  operation: '',
  hazmat: '',
  minFleetCode: '',
  sort: 'fleet_desc',
};

const STATE_OPTIONS = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA',
  'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA',
  'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY', 'PR', 'GU', 'VI', 'AS', 'MP',
];

const OPERATION_LABELS: Record<string, string> = {
  A: 'Interstate',
  B: 'Intrastate hazmat',
  C: 'Intrastate non-hazmat',
};

const FLEET_THRESHOLDS = [
  { code: '', label: 'Any fleet size' },
  { code: 'A', label: '1+ power units' },
  { code: 'D', label: '7+ power units' },
  { code: 'G', label: '15+ power units' },
  { code: 'J', label: '24+ power units' },
  { code: 'N', label: '45+ power units' },
  { code: 'P', label: '76+ power units' },
  { code: 'Q', label: '101+ power units' },
  { code: 'R', label: '201+ power units' },
  { code: 'U', label: '551+ power units' },
  { code: 'V', label: '1,000+ power units' },
  { code: 'W', label: '2,001+ power units' },
  { code: 'Z', label: 'Over 5,000 power units' },
];

function parseFilters(): DirectoryFilters {
  const queryIndex = window.location.hash.indexOf('?');
  if (queryIndex < 0) return { ...DEFAULT_FILTERS };
  const params = new URLSearchParams(window.location.hash.slice(queryIndex + 1));
  const sort = params.get('sort') as SortMode | null;
  const minFleetCode = (params.get('minFleet') ?? '').toUpperCase();
  return {
    q: params.get('q') ?? '',
    state: (params.get('state') ?? '').toUpperCase(),
    operation: (params.get('operation') ?? '').toUpperCase(),
    hazmat: (params.get('hazmat') ?? '').toUpperCase(),
    minFleetCode: FLEET_THRESHOLDS.some((option) => option.code === minFleetCode) ? minFleetCode : '',
    sort: sort && ['fleet_desc', 'dot_desc', 'name_asc'].includes(sort) ? sort : DEFAULT_FILTERS.sort,
  };
}

function filtersHash(filters: DirectoryFilters): string {
  const params = new URLSearchParams();
  const q = filters.q.trim();
  if (q) params.set('q', q);
  if (filters.state) params.set('state', filters.state);
  if (filters.operation) params.set('operation', filters.operation);
  if (filters.hazmat) params.set('hazmat', filters.hazmat);
  if (filters.minFleetCode) params.set('minFleet', filters.minFleetCode);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set('sort', filters.sort);
  const query = params.toString();
  return `#/carriers${query ? `?${query}` : ''}`;
}

function escapeSoqlText(value: string): string {
  return value.replaceAll("'", "''");
}

function carrierFromRow(row: DataRow): Carrier {
  return {
    dotNumber: readValue(row, ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM', 'DOT_NO']) ?? 'Unknown',
    legalName: readValue(row, ['LEGAL_NAME', 'CARRIER_NAME', 'NAME']) ?? 'Unnamed carrier',
    dbaName: readValue(row, ['DBA_NAME', 'DBA']),
    city: readValue(row, ['PHY_CITY', 'PHYSICAL_CITY', 'CITY']),
    state: readValue(row, ['PHY_STATE', 'PHYSICAL_STATE', 'STATE']),
    operation: readValue(row, ['CARRIER_OPERATION', 'CARRIER_OPERATION_DESC', 'OPERATION']),
    powerUnits: readValue(row, ['POWER_UNITS', 'NBR_POWER_UNIT', 'TOTAL_POWER_UNITS']),
    drivers: readValue(row, ['TOTAL_DRIVERS', 'DRIVER_TOTAL', 'DRIVERS']),
    mileage: readValue(row, ['MCS150_MILEAGE', 'MILEAGE', 'VMT']),
    mileageYear: readValue(row, ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR', 'VMT_YEAR']),
    hazmat: readValue(row, ['HM_IND', 'HAZMAT_IND', 'HAZMAT_FLAG']),
    fleetSizeCode: readValue(row, ['FLEETSIZE', 'FLEET_SIZE_CODE']),
  };
}

function formatNumber(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''));
  return Number.isFinite(numeric) ? numeric.toLocaleString() : String(value);
}

function operationLabel(value?: string): string {
  if (!value) return '—';
  return OPERATION_LABELS[value.toUpperCase()] ?? value;
}

function sortExpression(sort: SortMode): string {
  if (sort === 'dot_desc') return 'dot_number DESC';
  if (sort === 'name_asc') return 'legal_name ASC, dot_number DESC';
  return 'fleetsize DESC, dot_number DESC';
}

async function loadCarriers(filters: DirectoryFilters, signal: AbortSignal): Promise<Carrier[]> {
  const params = new URLSearchParams({ '$limit': String(PAGE_SIZE), '$order': sortExpression(filters.sort) });
  const where: string[] = [];
  const q = filters.q.trim();

  if (/^\d+$/.test(q)) where.push(`dot_number=${Number(q)}`);
  else if (q) params.set('$q', q);

  if (filters.state) where.push(`phy_state='${escapeSoqlText(filters.state)}'`);
  if (filters.operation) where.push(`carrier_operation='${escapeSoqlText(filters.operation)}'`);
  if (filters.hazmat === 'Y' || filters.hazmat === 'N') where.push(`hm_ind='${filters.hazmat}'`);
  if (filters.minFleetCode) where.push(`fleetsize>='${filters.minFleetCode}'`);

  if (where.length) params.set('$where', where.join(' AND '));

  const response = await fetch(`${DATAHUB}/az4n-8mr2.json?${params.toString()}`, { signal });
  if (!response.ok) throw new Error(`Company Census returned HTTP ${response.status}`);
  const payload = await response.json();
  if (!Array.isArray(payload)) throw new Error('Company Census returned an unexpected payload');
  return (payload as DataRow[]).map(carrierFromRow);
}

function Wordmark() {
  return (
    <a className="wordmark" href="#/overview" aria-label="Transport3r home">
      <span className="wordmark-mark" aria-hidden="true">
        <svg viewBox="0 0 42 42" role="img">
          <path d="M8 10.5h26v6H23.8V34h-6V16.5H8z" />
          <path d="M27 21h7v13h-7z" className="mark-accent" />
        </svg>
      </span>
      <span>Transport<span className="wordmark-three">3r</span></span>
    </a>
  );
}

function ResultStat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="directory-stat"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

export default function CarrierDirectoryApp() {
  const [applied, setApplied] = useState<DirectoryFilters>(() => parseFilters());
  const [draft, setDraft] = useState<DirectoryFilters>(() => parseFilters());
  const [rows, setRows] = useState<Carrier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'failed'>('idle');

  const appliedKey = useMemo(() => JSON.stringify(applied), [applied]);

  useEffect(() => {
    const onHash = () => {
      if (!window.location.hash.startsWith('#/carriers') && !window.location.hash.startsWith('#/prospect')) return;
      const next = parseFilters();
      setApplied(next);
      setDraft(next);
      setCopyState('idle');
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    loadCarriers(applied, controller.signal)
      .then((loaded) => setRows(loaded))
      .catch((cause) => {
        if (cause instanceof DOMException && cause.name === 'AbortError') return;
        setRows([]);
        setError(cause instanceof Error ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [appliedKey]);

  const statesInSlice = useMemo(() => new Set(rows.map((carrier) => carrier.state).filter(Boolean)).size, [rows]);
  const powerUnitsInSlice = useMemo(() => rows.reduce((sum, carrier) => sum + (Number(carrier.powerUnits) || 0), 0), [rows]);
  const activeFilterCount = [applied.q, applied.state, applied.operation, applied.hazmat, applied.minFleetCode].filter(Boolean).length;

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    const nextHash = filtersHash(draft);
    if (window.location.hash === nextHash) {
      setApplied({ ...draft });
      return;
    }
    window.location.hash = nextHash;
  }

  function resetFilters() {
    setDraft({ ...DEFAULT_FILTERS });
    if (window.location.hash === '#/carriers') setApplied({ ...DEFAULT_FILTERS });
    else window.location.hash = '#/carriers';
  }

  async function copyViewLink() {
    const base = `${window.location.origin}${window.location.pathname}${window.location.search}`;
    const url = `${base}${filtersHash(applied)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopyState('copied');
    } catch {
      setCopyState('failed');
    }
  }

  return (
    <div className="app-shell carrier-directory-shell">
      <header className="top-nav directory-top-nav">
        <Wordmark />
        <nav aria-label="Primary navigation">
          <a href="#/overview">Overview</a>
          <a href="#/carriers" className="active">Carriers</a>
          <a href="#/portfolio">Portfolio</a>
          <a href="#/alerts">Alerts</a>
          <a href="#/methodology">Methodology</a>
          <a href="#/sources">Source Health</a>
        </nav>
        <div className="nav-meta"><span className="nav-dot" /><span>FMCSA workspace</span></div>
      </header>

      <main className="page-shell wide-shell directory-page-shell">
        <section className="page-heading directory-heading">
          <div>
            <div className="eyebrow">Nationwide carrier intelligence</div>
            <h1>Carriers</h1>
            <p>Filter the current FMCSA Company Census as a carrier summary table. Every filter state and every carrier evidence section has a URL you can share directly.</p>
          </div>
          <button className="directory-share-button" type="button" onClick={copyViewLink}>
            {copyState === 'copied' ? 'Link copied' : copyState === 'failed' ? 'Copy failed' : 'Copy view link'}
          </button>
        </section>

        <section className="panel carrier-filter-panel">
          <form onSubmit={applyFilters}>
            <div className="carrier-filter-grid">
              <label className="directory-filter directory-filter-query">
                <span>Carrier / USDOT</span>
                <input value={draft.q} onChange={(event) => setDraft({ ...draft, q: event.target.value })} placeholder="Name or USDOT number" autoComplete="off" />
              </label>
              <label className="directory-filter">
                <span>State</span>
                <select value={draft.state} onChange={(event) => setDraft({ ...draft, state: event.target.value })}>
                  <option value="">All states</option>
                  {STATE_OPTIONS.map((state) => <option key={state} value={state}>{state}</option>)}
                </select>
              </label>
              <label className="directory-filter">
                <span>Operation</span>
                <select value={draft.operation} onChange={(event) => setDraft({ ...draft, operation: event.target.value })}>
                  <option value="">All operations</option>
                  <option value="A">Interstate</option>
                  <option value="B">Intrastate hazmat</option>
                  <option value="C">Intrastate non-hazmat</option>
                </select>
              </label>
              <label className="directory-filter">
                <span>Hazmat</span>
                <select value={draft.hazmat} onChange={(event) => setDraft({ ...draft, hazmat: event.target.value })}>
                  <option value="">All</option>
                  <option value="Y">Hazmat flagged</option>
                  <option value="N">Not flagged</option>
                </select>
              </label>
              <label className="directory-filter">
                <span>Minimum fleet</span>
                <select value={draft.minFleetCode} onChange={(event) => setDraft({ ...draft, minFleetCode: event.target.value })}>
                  {FLEET_THRESHOLDS.map((option) => <option key={option.code || 'all'} value={option.code}>{option.label}</option>)}
                </select>
              </label>
              <label className="directory-filter">
                <span>Sort</span>
                <select value={draft.sort} onChange={(event) => setDraft({ ...draft, sort: event.target.value as SortMode })}>
                  <option value="fleet_desc">Fleet size · largest</option>
                  <option value="dot_desc">USDOT · newest/highest</option>
                  <option value="name_asc">Carrier name · A–Z</option>
                </select>
              </label>
            </div>
            <div className="directory-filter-actions">
              <div className="directory-filter-note"><span className="live-dot" /> Live Company Census <code>az4n-8mr2</code> · up to {PAGE_SIZE} matches per view</div>
              <div className="directory-filter-buttons">
                <button className="directory-reset-button" type="button" onClick={resetFilters}>Reset</button>
                <button className="primary-button" type="submit">Apply filters</button>
              </div>
            </div>
          </form>
        </section>

        <section className="directory-stats" aria-label="Loaded result summary">
          <ResultStat label="Matched rows" value={loading ? '…' : formatNumber(rows.length)} detail={rows.length === PAGE_SIZE ? `First ${PAGE_SIZE} in this filtered view` : 'Current filtered view'} />
          <ResultStat label="Active filters" value={String(activeFilterCount)} detail="Encoded in the shareable URL" />
          <ResultStat label="States represented" value={loading ? '…' : formatNumber(statesInSlice)} detail="Within the loaded result slice" />
          <ResultStat label="Power units" value={loading ? '…' : formatNumber(powerUnitsInSlice)} detail="Sum within the loaded result slice" />
        </section>

        <section className="panel carrier-summary-panel">
          <div className="panel-heading compact directory-table-heading">
            <div><div className="eyebrow">Carrier summary</div><h2>FMCSA carrier table</h2></div>
            <span className="directory-view-status">{loading ? 'Loading current census…' : error ? 'Source error' : `${rows.length} carrier${rows.length === 1 ? '' : 's'} shown`}</span>
          </div>

          {error && <div className="inline-error"><strong>Carrier table could not load.</strong> {error}</div>}
          {!error && !loading && !rows.length && <div className="directory-empty"><strong>No carriers matched these filters.</strong><span>Widen the filters or reset the view.</span></div>}

          {!error && rows.length > 0 && (
            <div className="carrier-summary-scroll">
              <div className="carrier-summary-table" role="table" aria-label="Carrier summary table">
                <div className="carrier-summary-row carrier-summary-header" role="row">
                  <span>Carrier</span><span>USDOT</span><span>Location</span><span>Operation</span><span>Power units</span><span>Drivers</span><span>Reported VMT</span><span>Evidence links</span>
                </div>
                {rows.map((carrier) => (
                  <div className="carrier-summary-row" role="row" key={carrier.dotNumber}>
                    <span className="carrier-name-cell">
                      <a href={`#/carrier/${carrier.dotNumber}/summary`}><strong>{carrier.legalName}</strong></a>
                      {carrier.dbaName && <small>DBA {carrier.dbaName}</small>}
                    </span>
                    <span className="carrier-dot-cell"><a href={`#/carrier/${carrier.dotNumber}/summary`}>{carrier.dotNumber}</a></span>
                    <span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || '—'}</span>
                    <span>{operationLabel(carrier.operation)}</span>
                    <span className="number-cell">{formatNumber(carrier.powerUnits)}</span>
                    <span className="number-cell">{formatNumber(carrier.drivers)}</span>
                    <span className="number-cell">{formatNumber(carrier.mileage)}{carrier.mileageYear ? <small>{carrier.mileageYear}</small> : null}</span>
                    <span className="carrier-evidence-links">
                      <a href={`#/carrier/${carrier.dotNumber}/summary`}>Summary</a>
                      <a href={`#/carrier/${carrier.dotNumber}/safety`}>Safety</a>
                      <a href={`#/carrier/${carrier.dotNumber}/fleet`}>Fleet</a>
                      <a href={`#/carrier/${carrier.dotNumber}/authority`}>Authority</a>
                      <a href={`#/carrier/${carrier.dotNumber}/insurance`}>Insurance</a>
                      <a href={`#/carrier/${carrier.dotNumber}/sms`}>SMS</a>
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      </main>

      <footer className="app-footer"><span>Transport3r</span><span>Shareable FMCSA carrier directory</span><span>Evidence before score</span></footer>
    </div>
  );
}
