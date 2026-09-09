import { FormEvent, useEffect, useMemo, useState } from 'react';
import sourceCatalogJson from '../data/fmcsa_sources.json';
import { DataRow, SchemaRegistry, loadSchemaRegistry, readValue, censusStatusLabel, driverReportDetail } from './datahub';

type Page = 'overview' | 'carriers' | 'portfolio' | 'alerts' | 'methodology' | 'sources';
type SortMode = 'fleet_desc' | 'dot_desc' | 'name_asc' | 'drivers_desc' | 'drivers_asc';
type RiskFilter = '' | 'available' | 'unavailable';

type SourceCatalogEntry = {
  id: string;
  name: string;
  family: string;
  cadence: string;
  scope: string;
  role: string;
  tier: string;
  history: string;
};

type SourceHealthEntry = {
  id: string;
  name: string;
  family: string;
  cadence: string;
  status: 'healthy' | 'degraded' | 'failed' | 'pending';
  checked_at?: string | null;
  rows_updated_at?: string | null;
  schema_fields?: number | null;
  sample_rows?: number | null;
  error?: string | null;
};

type SourceHealthPayload = {
  generated_at: string | null;
  source_count?: number;
  healthy_count?: number;
  degraded_count?: number;
  failed_count?: number;
  sources: SourceHealthEntry[];
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
  mcs150Date?: string;
  statusCode?: string;
  mileage?: string;
  mileageYear?: string;
  hazmat?: string;
  fleetSizeCode?: string;
};

type CarrierFilters = {
  q: string;
  state: string;
  operation: string;
  hazmat: string;
  minFleetCode: string;
  minDrivers: string;
  maxDrivers: string;
  risk: RiskFilter;
  sort: SortMode;
};

const sourceCatalog = sourceCatalogJson as SourceCatalogEntry[];
const DATAHUB = 'https://data.transportation.gov/resource';
const PAGE_SIZE = 100;

const NAV: Array<{ id: Page; label: string; short: string }> = [
  { id: 'overview', label: 'Overview', short: 'Overview' },
  { id: 'carriers', label: 'Carriers', short: 'Carriers' },
  { id: 'portfolio', label: 'Portfolio', short: 'Portfolio' },
  { id: 'alerts', label: 'Alerts', short: 'Alerts' },
  { id: 'methodology', label: 'Methodology', short: 'Method' },
  { id: 'sources', label: 'Data Sources', short: 'Data' },
];

const DEFAULT_FILTERS: CarrierFilters = {
  q: '',
  state: '',
  operation: '',
  hazmat: '',
  minFleetCode: '',
  minDrivers: '',
  maxDrivers: '',
  risk: '',
  sort: 'fleet_desc',
};

const STATES = [
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

const DATA_FAMILIES = [
  {
    title: 'Identity & exposure',
    eyebrow: 'Daily census',
    description: 'Resolve the correct carrier, operation type, reported equipment, drivers and mileage before judging loss potential.',
    sources: ['az4n-8mr2'],
    action: 'Carrier triage',
  },
  {
    title: 'Safety evidence',
    eyebrow: 'Daily inspections & crashes',
    description: 'Inspect crash involvement, inspection history, violations, OOS events, citations and the actual vehicles observed roadside.',
    sources: ['aayw-vxb3', 'fx4q-ay7w', 'wt8s-2hbx', '876r-jsdb', '5qik-smay', 'qbt8-7vic'],
    action: 'Loss-control evidence',
  },
  {
    title: 'Authority & coverage',
    eyebrow: 'MOTUS baseline + history',
    description: 'Verify operating authority, policy filings, cancellations, BOC-3 administration and revoke/suspend history.',
    sources: ['inys-ebih', 'yu5v-wbh6', 'c5y8-a4uz', '3uet-3z4i', '6snj-ed7q', 'wb4f-neki'],
    action: 'Eligibility & continuity',
  },
  {
    title: 'Legacy authority archive',
    eyebrow: 'Frozen pre-MOTUS baseline',
    description: 'Eight official legacy authority files retained for historical continuity. They never override modern MOTUS current state.',
    sources: ['6eyk-hxee', 'ypjt-5ydn', 'qh9u-swkp', '9mw4-x3tu', '2emp-mxtb', '6sqe-dvqs', '96tg-4mhf', 'sa6p-acbp'],
    action: 'Historical lineage only',
  },
  {
    title: 'Change detection',
    eyebrow: '24-hour MOTUS deltas',
    description: 'Separate material changes from static history: new authority events, insurance changes and suspension/revocation activity.',
    sources: ['nakq-58th', 'dm5j-zc6c', 'mhr5-hjyc', 'x96h-evps', 'xe5s-wca7', 'e67p-xyd5'],
    action: 'Portfolio monitoring',
  },
  {
    title: 'SMS methodology',
    eyebrow: 'Monthly input + official output',
    description: 'Replay FMCSA measures from the exact monthly inputs, then validate against official published outputs before any insurance model uses them.',
    sources: ['kjg3-diqy', 'rbkj-cgst', '4wxs-vbns', '8mt8-2mdr', 'm3ry-qcip', 'h3zn-uid9', '4y6x-dmck', 'h9zy-gjn8'],
    action: 'Deterministic scoring layer',
  },
  {
    title: 'Operational enforcement',
    eyebrow: 'New Entrant OOS',
    description: 'Surface federal operational out-of-service orders as a hard-review fact independent of any composite score.',
    sources: ['p2mt-9ige'],
    action: 'Material alert',
  },
];

function pageFromHash(): Page {
  const segment = window.location.hash.replace(/^#\//, '').split(/[/?]/)[0];
  if (segment === 'prospect') return 'carriers';
  return NAV.some((item) => item.id === segment) ? segment as Page : 'overview';
}

export function parseCarrierFilters(hash = window.location.hash): CarrierFilters {
  const queryIndex = hash.indexOf('?');
  if (queryIndex < 0) return { ...DEFAULT_FILTERS };
  const params = new URLSearchParams(hash.slice(queryIndex + 1));
  const sort = params.get('sort') as SortMode | null;
  const minFleetCode = (params.get('minFleet') ?? '').toUpperCase();
  return {
    q: params.get('q') ?? '',
    state: (params.get('state') ?? '').toUpperCase(),
    operation: (params.get('operation') ?? '').toUpperCase(),
    hazmat: (params.get('hazmat') ?? '').toUpperCase(),
    minFleetCode: FLEET_THRESHOLDS.some((option) => option.code === minFleetCode) ? minFleetCode : '',
    minDrivers: (params.get('minDrivers') ?? '').trim(),
    maxDrivers: (params.get('maxDrivers') ?? '').trim(),
    risk: ['available', 'unavailable'].includes(params.get('risk') ?? '') ? params.get('risk') as RiskFilter : '',
    sort: sort && ['fleet_desc', 'dot_desc', 'name_asc', 'drivers_desc', 'drivers_asc'].includes(sort) ? sort : DEFAULT_FILTERS.sort,
  };
}

export function carrierHash(filters: CarrierFilters): string {
  const params = new URLSearchParams();
  const q = filters.q.trim();
  if (q) params.set('q', q);
  if (filters.state) params.set('state', filters.state);
  if (filters.operation) params.set('operation', filters.operation);
  if (filters.hazmat) params.set('hazmat', filters.hazmat);
  if (filters.minFleetCode) params.set('minFleet', filters.minFleetCode);
  if (filters.minDrivers.trim()) params.set('minDrivers', filters.minDrivers.trim());
  if (filters.maxDrivers.trim()) params.set('maxDrivers', filters.maxDrivers.trim());
  if (filters.risk) params.set('risk', filters.risk);
  if (filters.sort !== DEFAULT_FILTERS.sort) params.set('sort', filters.sort);
  const query = params.toString();
  return `#/carriers${query ? `?${query}` : ''}`;
}

function escapeSoql(value: string): string {
  return value.replaceAll("'", "''");
}

function formatNumber(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''));
  return Number.isFinite(numeric) ? numeric.toLocaleString() : String(value);
}

function formatDateTime(raw?: string | null): string {
  if (!raw) return 'Unavailable';
  const date = new Date(raw);
  if (Number.isNaN(date.valueOf())) return raw;
  return date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
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
    mcs150Date: readValue(row, ['MCS150_DATE']),
    statusCode: readValue(row, ['STATUS_CODE']),
    mileage: readValue(row, ['MCS150_MILEAGE', 'MILEAGE', 'VMT']),
    mileageYear: readValue(row, ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR', 'VMT_YEAR']),
    hazmat: readValue(row, ['HM_IND', 'HAZMAT_IND', 'HAZMAT_FLAG']),
    fleetSizeCode: readValue(row, ['FLEETSIZE', 'FLEET_SIZE_CODE']),
  };
}

function sortExpression(sort: SortMode): string {
  if (sort === 'drivers_desc') return 'total_drivers::number DESC NULLS LAST, dot_number DESC';
  if (sort === 'drivers_asc') return 'total_drivers::number ASC NULLS LAST, dot_number DESC';
  if (sort === 'dot_desc') return 'dot_number DESC';
  if (sort === 'name_asc') return 'legal_name ASC, dot_number DESC';
  return 'fleetsize DESC, dot_number DESC';
}

export async function fetchDirectoryRows(url: string, signal?: AbortSignal, timeoutMs = 9000): Promise<unknown> {
  if (signal?.aborted) throw new DOMException('Request cancelled', 'AbortError');
  const controller = new AbortController();
  const cancel = () => controller.abort();
  signal?.addEventListener('abort', cancel, { once: true });
  const timeout = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(url, { signal: controller.signal, headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error(`Company Census returned HTTP ${response.status}`);
    return await response.json();
  } catch (cause) {
    if (!signal?.aborted && cause instanceof DOMException && cause.name === 'AbortError') throw new Error('FMCSA request timed out');
    throw cause;
  } finally {
    window.clearTimeout(timeout);
    signal?.removeEventListener('abort', cancel);
  }
}

export function carrierFilterError(filters: CarrierFilters): string | null {
  for (const raw of [filters.minDrivers, filters.maxDrivers]) {
    const value = raw.trim();
    if (value && (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)))) return 'Driver limits must be whole numbers of zero or more.';
  }
  if (filters.minDrivers.trim() && filters.maxDrivers.trim() && Number(filters.minDrivers) > Number(filters.maxDrivers)) return 'Minimum drivers must not exceed maximum drivers.';
  return null;
}

export function buildCarrierQuery(filters: CarrierFilters): URLSearchParams {
  const error = carrierFilterError(filters);
  if (error) throw new Error(error);
  const params = new URLSearchParams({ '$limit': String(PAGE_SIZE), '$order': sortExpression(filters.sort) });
  const where: string[] = [];
  const q = filters.q.trim();
  if (/^\d+$/.test(q)) where.push(`dot_number=${Number(q)}`);
  else if (q) params.set('$q', q);
  if (filters.state) where.push(`phy_state='${escapeSoql(filters.state)}'`);
  if (filters.operation) where.push(`carrier_operation='${escapeSoql(filters.operation)}'`);
  if (filters.hazmat === 'Y' || filters.hazmat === 'N') where.push(`hm_ind='${filters.hazmat}'`);
  if (filters.minFleetCode) where.push(`fleetsize>='${filters.minFleetCode}'`);
  if (filters.minDrivers.trim()) where.push(`total_drivers::number>=${Number(filters.minDrivers)}`);
  if (filters.maxDrivers.trim()) where.push(`total_drivers::number<=${Number(filters.maxDrivers)}`);
  if (where.length) params.set('$where', where.join(' AND '));
  return params;
}

export async function loadCarriers(filters: CarrierFilters, signal?: AbortSignal): Promise<Carrier[]> {
  const params = buildCarrierQuery(filters);
  // No production score artifact/model is released. Availability is not a Census field.
  if (filters.risk === 'available') return [];
  const payload = await fetchDirectoryRows(`${DATAHUB}/az4n-8mr2.json?${params.toString()}`, signal);
  if (!Array.isArray(payload)) throw new Error('Company Census returned an unexpected payload');
  return (payload as DataRow[]).map(carrierFromRow);
}

function Brand() {
  return (
    <a className="t3-brand" href="#/overview" aria-label="Transport3r overview">
      <span className="t3-mark" aria-hidden="true">
        <svg viewBox="0 0 42 42"><path d="M8 10.5h26v6H23.8V34h-6V16.5H8z"/><path d="M27 21h7v13h-7z" className="accent"/></svg>
      </span>
      <span className="t3-brand-text">Transport<span>3r</span></span>
    </a>
  );
}

function HealthPill({ health }: { health: SourceHealthPayload | null }) {
  if (!health) return <span className="t3-health neutral"><i/>Source snapshot loading</span>;
  const healthy = health.healthy_count ?? health.sources.filter((source) => source.status === 'healthy').length;
  const total = health.source_count ?? sourceCatalog.length;
  const allHealthy = healthy === total;
  return <span className={`t3-health ${allHealthy ? 'good' : 'warn'}`}><i/>{healthy}/{total} source probes healthy</span>;
}

function Shell({ page, health, children }: { page: Page; health: SourceHealthPayload | null; children: React.ReactNode }) {
  return (
    <div className="t3-app">
      <header className="t3-topbar">
        <Brand />
        <nav className="t3-primary-nav" aria-label="Primary navigation">
          {NAV.map((item) => <a key={item.id} href={`#/${item.id}`} className={page === item.id ? 'active' : ''}><span className="wide-label">{item.label}</span><span className="short-label">{item.short}</span></a>)}
        </nav>
        <HealthPill health={health} />
      </header>
      {children}
      <footer className="t3-footer"><span>Transport3r</span><span>FMCSA-first transportation insurance intelligence</span><span>Evidence before score</span></footer>
    </div>
  );
}

function PageHeading({ eyebrow, title, copy, action }: { eyebrow: string; title: string; copy: string; action?: React.ReactNode }) {
  return <section className="t3-page-heading"><div><div className="t3-eyebrow">{eyebrow}</div><h1>{title}</h1><p>{copy}</p></div>{action}</section>;
}

function OverviewPage({ health, schema }: { health: SourceHealthPayload | null; schema: SchemaRegistry | null }) {
  const healthy = health?.healthy_count ?? health?.sources.filter((source) => source.status === 'healthy').length ?? 0;
  const latestDaily = useMemo(() => {
    const values = (health?.sources ?? []).map((source) => source.rows_updated_at).filter((value): value is string => Boolean(value));
    if (!values.length) return null;
    return values.sort().at(-1) ?? null;
  }, [health]);

  return <main className="t3-main">
    <section className="t3-hero">
      <div className="t3-hero-copy">
        <div className="t3-eyebrow light">Transportation underwriting workspace</div>
        <h1>Know the carrier before you price the risk.</h1>
        <p>Resolve identity and exposure, trace three years of safety evidence, verify authority and insurance continuity, monitor daily changes, and keep every calculated or modelled value visibly separate from official FMCSA facts.</p>
        <div className="t3-actions"><a className="t3-button primary" href="#/carriers">Browse carriers</a><a className="t3-button ghost" href="#/sources">Review the data</a></div>
      </div>
      <aside className="t3-hero-status">
        <div className="t3-status-head"><span>Evidence system</span><strong>{healthy || '—'} / {sourceCatalog.length}</strong></div>
        <div className="t3-status-row"><span>Official source registry</span><strong>{schema?.source_count ?? sourceCatalog.length} datasets</strong></div>
        <div className="t3-status-row"><span>Registered fields</span><strong>{schema?.field_count?.toLocaleString() ?? '—'}</strong></div>
        <div className="t3-status-row"><span>Latest daily source update</span><strong>{latestDaily ? formatDateTime(latestDaily) : 'Loading'}</strong></div>
        <div className="t3-status-note">Overview uses repository snapshots only. Live FMCSA requests begin when you open Carriers or a Carrier 360 tab.</div>
      </aside>
    </section>

    <section className="t3-kpi-grid">
      <article><span>Daily safety / census</span><strong>7</strong><p>Carrier identity, crashes, inspections, units, violations, citations and studies.</p></article>
      <article><span>Authority / insurance</span><strong>11</strong><p>Six full-history MOTUS sources plus five daily change feeds.</p></article>
      <article><span>Monthly SMS</span><strong>8</strong><p>Exact inputs and official outputs for replay and validation.</p></article>
      <article><span>Enforcement</span><strong>1</strong><p>New Entrant operational OOS orders surfaced as a hard-review fact.</p></article>
    </section>

    <section className="t3-section-head"><div><div className="t3-eyebrow">Data → decision</div><h2>Every dataset has an underwriting job.</h2></div><a href="#/sources">See all 27 sources →</a></section>
    <section className="t3-family-grid">
      {DATA_FAMILIES.map((family) => <article className="t3-family-card" key={family.title}><div className="t3-eyebrow">{family.eyebrow}</div><h3>{family.title}</h3><p>{family.description}</p><div className="t3-card-foot"><span>{family.sources.length} source{family.sources.length === 1 ? '' : 's'}</span><strong>{family.action}</strong></div></article>)}
    </section>

    <section className="t3-two-col">
      <article className="t3-panel">
        <div className="t3-panel-head"><div><div className="t3-eyebrow">Underwriting sequence</div><h2>One carrier, six questions.</h2></div></div>
        <div className="t3-step-list">
          {[
            ['01', 'Who is the risk?', 'USDOT identity, operation, geography, fleet, drivers and reported VMT.'],
            ['02', 'What has happened?', 'Crashes, inspections, violations, OOS findings and roadside vehicle observations.'],
            ['03', 'Can it legally operate?', 'Authority status, revocation/suspension and New Entrant OOS evidence.'],
            ['04', 'Is coverage continuous?', 'Active/pending insurance filings plus cancellation and replacement history.'],
            ['05', 'What changed recently?', 'Daily MOTUS deltas isolate new authority and insurance events.'],
            ['06', 'What can be calculated?', 'Replay FMCSA SMS measures first; only then introduce a proprietary insurance model.'],
          ].map(([number, title, text]) => <div className="t3-step" key={number}><span>{number}</span><div><strong>{title}</strong><p>{text}</p></div></div>)}
        </div>
      </article>
      <article className="t3-panel t3-model-panel">
        <div className="t3-eyebrow">Calculation governance</div><h2>Score last, not first.</h2>
        <div className="t3-model-stage official"><span>1</span><div><strong>Official FMCSA</strong><p>Published records and values. Never relabelled as Transport output.</p></div></div>
        <div className="t3-model-stage calculated"><span>2</span><div><strong>Transport calculated</strong><p>Deterministic replay from versioned public inputs. SMS measure replay is regression-tested in CI.</p></div></div>
        <div className="t3-model-stage modelled"><span>3</span><div><strong>Transport modelled</strong><p>Insurance-oriented TRI remains gated until peer-percentile reconstruction and actuarial validation are complete.</p></div></div>
      </article>
    </section>
  </main>;
}

function CarriersPage() {
  const [applied, setApplied] = useState<CarrierFilters>(() => parseCarrierFilters());
  const [draft, setDraft] = useState<CarrierFilters>(() => parseCarrierFilters());
  const [rows, setRows] = useState<Carrier[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'manual'>('idle');
  const [reloadVersion, setReloadVersion] = useState(0);

  const appliedKey = useMemo(() => JSON.stringify(applied), [applied]);

  useEffect(() => {
    const onHash = () => {
      if (pageFromHash() !== 'carriers') return;
      const next = parseCarrierFilters();
      setApplied(next);
      setDraft(next);
      setCopyState('idle');
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    let current = true;
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    setRows([]);
    loadCarriers(applied, controller.signal)
      .then((loaded) => { if (current) setRows(loaded); })
      .catch((cause) => { if (current) { setRows([]); setError(cause instanceof Error ? cause.message : String(cause)); } })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; controller.abort(); };
  }, [appliedKey, reloadVersion]);

  const loadedStates = useMemo(() => new Set(rows.map((row) => row.state).filter(Boolean)).size, [rows]);
  const loadedUnits = useMemo(() => rows.reduce((sum, row) => sum + (Number(row.powerUnits) || 0), 0), [rows]);
  const activeFilters = [applied.q, applied.state, applied.operation, applied.hazmat, applied.minFleetCode, applied.minDrivers, applied.maxDrivers, applied.risk].filter(Boolean).length;
  const filterError = carrierFilterError(draft);

  function apply(event: FormEvent) {
    event.preventDefault();
    if (filterError) return;
    const next = carrierHash(draft);
    if (carrierHash(applied) === next) setReloadVersion(version => version + 1);
    if (window.location.hash !== next) window.location.hash = next;
  }

  function reset() {
    setDraft({ ...DEFAULT_FILTERS });
    if (carrierHash(applied) === '#/carriers') setReloadVersion(version => version + 1);
    if (window.location.hash !== '#/carriers') window.location.hash = '#/carriers';
  }

  function sortDrivers() {
    const next: CarrierFilters = { ...applied, sort: applied.sort === 'drivers_desc' ? 'drivers_asc' : 'drivers_desc' };
    setDraft(next);
    window.location.hash = carrierHash(next);
  }

  async function copyView() {
    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setCopyState('copied');
    } catch {
      window.prompt('Copy this shareable carrier view URL:', url);
      setCopyState('manual');
    }
  }

  return <main className="t3-main">
    <PageHeading eyebrow="Nationwide carrier intelligence" title="Carriers" copy="A live Company Census summary table for triage. Filters are encoded in the URL so an underwriting view can be shared exactly as screened." action={<button className="t3-button secondary" onClick={copyView}>{copyState === 'copied' ? 'View link copied' : 'Copy view link'}</button>} />

    <section className="t3-panel t3-filter-panel">
      <form className="t3-filter-grid t3-carrier-filters" onSubmit={apply}>
        <label className="span-2"><span>Carrier / USDOT</span><input value={draft.q} onChange={(event) => setDraft({ ...draft, q: event.target.value })} placeholder="Legal name, DBA or USDOT number" /></label>
        <label><span>State</span><select value={draft.state} onChange={(event) => setDraft({ ...draft, state: event.target.value })}><option value="">All states</option>{STATES.map((state) => <option key={state}>{state}</option>)}</select></label>
        <label><span>Operation</span><select value={draft.operation} onChange={(event) => setDraft({ ...draft, operation: event.target.value })}><option value="">All operations</option><option value="A">Interstate</option><option value="B">Intrastate hazmat</option><option value="C">Intrastate non-hazmat</option></select></label>
        <label><span>Hazmat</span><select value={draft.hazmat} onChange={(event) => setDraft({ ...draft, hazmat: event.target.value })}><option value="">Any</option><option value="Y">Hazmat</option><option value="N">Non-hazmat</option></select></label>
        <label><span>Minimum fleet</span><select value={draft.minFleetCode} onChange={(event) => setDraft({ ...draft, minFleetCode: event.target.value })}>{FLEET_THRESHOLDS.map((option) => <option key={option.code} value={option.code}>{option.label}</option>)}</select></label>
        <label><span>Minimum drivers</span><input type="number" min="0" step="1" value={draft.minDrivers} onChange={(event) => setDraft({ ...draft, minDrivers: event.target.value })} placeholder="No minimum" /></label>
        <label><span>Maximum drivers</span><input type="number" min="0" step="1" value={draft.maxDrivers} onChange={(event) => setDraft({ ...draft, maxDrivers: event.target.value })} placeholder="No maximum" /></label>
        <label><span>Risk score</span><select value={draft.risk} onChange={(event) => setDraft({ ...draft, risk: event.target.value as RiskFilter })}><option value="">Any availability</option><option value="available">Available</option><option value="unavailable">Unavailable</option></select></label>
        <label><span>Sort</span><select value={draft.sort} onChange={(event) => setDraft({ ...draft, sort: event.target.value as SortMode })}><option value="fleet_desc">Largest fleet band</option><option value="drivers_desc">Drivers · most first</option><option value="drivers_asc">Drivers · fewest first</option><option value="dot_desc">Newest USDOT number</option><option value="name_asc">Carrier name</option></select></label>
        <div className="t3-filter-actions"><button className="t3-button primary" disabled={loading}>{loading ? 'Loading…' : 'Apply filters'}</button><button className="t3-button text" type="button" onClick={reset}>Reset</button></div>
      </form>
      {filterError && <div className="t3-error" role="alert">{filterError}</div>}
      <div className="t3-query-note"><span className="t3-live-dot"/>Live FMCSA Company Census · filters and sorting apply before the {PAGE_SIZE}-row limit · detailed evidence loads after opening a carrier tab.</div>
      <div className="t3-query-note">Risk scores are unavailable: no scoring model has been released. Driver limits use reported counts; unknown counts do not match a numeric range.</div>
    </section>

    <section className="t3-mini-stats">
      <div><span>Rows loaded</span><strong>{loading ? '—' : rows.length.toLocaleString()}</strong><small>Current screened slice</small></div>
      <div><span>States represented</span><strong>{loading ? '—' : loadedStates.toLocaleString()}</strong><small>Within loaded slice</small></div>
      <div><span>Reported power units</span><strong>{loading ? '—' : loadedUnits.toLocaleString()}</strong><small>Sum of loaded rows</small></div>
      <div><span>Active filters</span><strong>{activeFilters}</strong><small>Encoded in shareable URL</small></div>
    </section>

    {error && <div className="t3-error"><strong>FMCSA carrier table unavailable.</strong><span>{error}</span><button onClick={() => setReloadVersion(version => version + 1)}>Retry</button></div>}

    <section className="t3-panel t3-table-panel">
      <div className="t3-table-headline"><div><div className="t3-eyebrow">Company Census</div><h2>Carrier summary</h2></div><span>{loading ? 'Loading matching rows…' : error ? 'Source unavailable' : rows.length === PAGE_SIZE ? `First ${PAGE_SIZE} matching rows` : `${rows.length} matching rows loaded`}</span></div>
      <div className="t3-carrier-table-wrap">
        <div className="t3-carrier-table">
          <div className="t3-carrier-row header"><span>Carrier</span><span>USDOT</span><span>Location</span><span>Operation</span><span>Fleet</span><span><button className="t3-column-sort" type="button" onClick={sortDrivers} aria-label={`Sort drivers ${applied.sort === 'drivers_desc' ? 'fewest' : 'most'} first`}>Drivers {applied.sort === 'drivers_desc' ? '↓' : applied.sort === 'drivers_asc' ? '↑' : '↕'}</button></span><span>Risk score</span><span>VMT</span><span>HM</span><span>Evidence</span></div>
          {!loading && !error && rows.map((carrier) => <div className="t3-carrier-row" key={carrier.dotNumber}>
            <span className="carrier-name"><a href={`#/carrier/${carrier.dotNumber}/summary`}>{carrier.legalName}</a>{carrier.dbaName && <small>DBA {carrier.dbaName}</small>}</span>
            <span className="mono">{carrier.dotNumber}</span>
            <span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || '—'}</span>
            <span>{OPERATION_LABELS[(carrier.operation ?? '').toUpperCase()] ?? carrier.operation ?? '—'}</span>
            <span><strong>{formatNumber(carrier.powerUnits)}</strong><small>PU · band {carrier.fleetSizeCode ?? '—'}</small></span>
            <span title={driverReportDetail(carrier.mcs150Date,carrier.statusCode)}>{formatNumber(carrier.drivers)}<small>{censusStatusLabel(carrier.statusCode)} registration</small></span>
            <span title="No released scoring model is available for this carrier.">Unavailable</span>
            <span>{formatNumber(carrier.mileage)}{carrier.mileageYear && <small>{carrier.mileageYear}</small>}</span>
            <span>{carrier.hazmat || '—'}</span>
            <span className="evidence-links"><a href={`#/carrier/${carrier.dotNumber}/summary`}>360</a><a href={`#/carrier/${carrier.dotNumber}/safety`}>Safety</a><a href={`#/carrier/${carrier.dotNumber}/fleet`}>Fleet</a><a href={`#/carrier/${carrier.dotNumber}/authority`}>Authority</a><a href={`#/carrier/${carrier.dotNumber}/insurance`}>Insurance</a><a href={`#/carrier/${carrier.dotNumber}/sms`}>SMS</a></span>
          </div>)}
          {!loading && !error && rows.length === 0 && <div className="t3-table-empty"><strong>{applied.risk === 'available' ? 'No released risk scores are available.' : 'No carriers returned for this screen.'}</strong><span>{applied.risk === 'available' ? 'Choose Any availability or Unavailable to browse carriers.' : 'Broaden the filters or search by USDOT for exact entity resolution.'}</span></div>}
          {loading && <div className="t3-table-empty"><span className="t3-spinner"/><strong>Loading current Company Census rows</strong></div>}
        </div>
      </div>
    </section>
  </main>;
}

function PortfolioPage() {
  return <main className="t3-main"><PageHeading eyebrow="Book-of-business workflow" title="Portfolio" copy="The monitoring layer is designed for insured, quoted and watched carriers. No policy or premium values are fabricated until an insurer account spine is supplied or a carrier is explicitly saved." />
    <section className="t3-two-col">
      <article className="t3-panel t3-empty-workspace"><div className="t3-empty-icon">P</div><h2>No portfolio records yet.</h2><p>The public FMCSA layer can resolve and evaluate carriers now. Portfolio persistence is the boundary between public intelligence and insurer-owned exposure data.</p><a className="t3-button primary" href="#/carriers">Find carriers</a></article>
      <article className="t3-panel"><div className="t3-eyebrow">Planned account spine</div><h2>What belongs here</h2><div className="t3-definition-list"><div><strong>Exposure</strong><span>Policy, limits, premium, class, territory, scheduled power units and VMT.</span></div><div><strong>Public intelligence</strong><span>Current census, inspections, crashes, authority, insurance filings and SMS.</span></div><div><strong>Monitoring</strong><span>Daily authority/insurance/OOS changes and monthly safety movement.</span></div><div><strong>Validation</strong><span>Actual claims frequency and severity to evaluate future TRI deciles.</span></div></div></article>
    </section>
  </main>;
}

function AlertsPage({ health }: { health: SourceHealthPayload | null }) {
  const healthById = useMemo(() => new Map((health?.sources ?? []).map((source) => [source.id, source])), [health]);
  const events = [
    ['Critical', 'Operational OOS order', 'p2mt-9ige', 'New Entrant federal OOS history; current effect must be verified from the record.'],
    ['Critical', 'Authority suspension / revocation', 'e67p-xyd5', '24-hour RevokeSuspend differences plus baseline authority state.'],
    ['Critical', 'Insurance filing change', 'x96h-evps', 'Active/pending policy changes, backed by insurance-history differences.'],
    ['High', 'New serious crash', 'aayw-vxb3', 'Daily crash involvement; fault is not inferred from the public record.'],
    ['High', 'OOS / violation deterioration', '876r-jsdb', 'Requires persisted daily snapshots to detect worsening rates rather than one-time counts.'],
    ['Watch', 'Fleet / mileage change', 'az4n-8mr2', 'Requires historical census snapshots to distinguish real exposure movement from stale MCS-150 data.'],
    ['Watch', 'Monthly SMS deterioration', '4y6x-dmck', 'Official output plus deterministic replay; portfolio-level deltas require monthly persistence.'],
  ];
  return <main className="t3-main"><PageHeading eyebrow="Material change detection" title="Alerts" copy="Alerts are facts or deterministic changes, not score decorations. Daily MOTUS difference feeds are the near-current event layer; portfolio persistence is still required to evaluate insured-carrier changes continuously." />
    <section className="t3-panel"><div className="t3-alert-table"><div className="t3-alert-row header"><span>Priority</span><span>Event</span><span>Source</span><span>Underwriting treatment</span><span>Health</span></div>{events.map(([level, event, sourceId, treatment]) => { const source = healthById.get(sourceId); return <div className="t3-alert-row" key={event}><span><b className={`t3-priority ${level.toLowerCase()}`}>{level}</b></span><span><strong>{event}</strong></span><span className="mono">{sourceId}</span><span>{treatment}</span><span><i className={`t3-source-dot ${source?.status ?? 'pending'}`}/>{source?.status ?? 'pending'}</span></div>; })}</div></section>
    <section className="t3-note-panel"><strong>Current constraint</strong><p>The source feeds are live and healthy, but Transport3r does not yet persist a durable insured-carrier snapshot history. Until that layer exists, the app will not invent “new since yesterday” events from a single current lookup.</p></section>
  </main>;
}

function MethodologyPage() {
  return <main className="t3-main"><PageHeading eyebrow="Versioned calculation contract" title="Methodology" copy="Official FMCSA outputs, deterministic Transport calculations and proprietary insurance models are separate evidence classes with separate validation gates." />
    <section className="t3-evidence-class-grid"><article className="official"><span>01</span><div className="t3-eyebrow">Official FMCSA</div><h2>Published evidence</h2><p>Census, inspections, violations, crashes, authority, insurance, OOS orders and official SMS outputs. These values are never presented as proprietary scores.</p></article><article className="calculated"><span>02</span><div className="t3-eyebrow">Transport calculated</div><h2>Deterministic replay</h2><p>SMS v3.21 inspection-based measures are reproduced from the current monthly input files and regression-tested against FMCSA outputs. Every formula stays versioned and replayable.</p></article><article className="modelled"><span>03</span><div className="t3-eyebrow">Transport modelled</div><h2>Insurance inference</h2><p>TRI is intentionally not released until full-population percentile reconstruction, exposure treatment and actuarial validation are defensible.</p></article></section>
    <section className="t3-panel"><div className="t3-panel-head"><div><div className="t3-eyebrow">SMS v3.21</div><h2>Calculation pipeline</h2></div><span className="t3-chip good">Current ruleset</span></div><div className="t3-method-pipeline"><div><span>1</span><strong>Monthly census</strong><p>Carrier class, power units, VMT and SMS eligibility inputs.</p></div><div><span>2</span><strong>Inspection / crash / violation inputs</strong><p>Exact events and FMCSA-provided methodology fields for the current SMS month.</p></div><div><span>3</span><strong>Measure replay</strong><p>Severity, OOS and recency weighting plus relevant-inspection denominators.</p></div><div><span>4</span><strong>Official output validation</strong><p>Compare Transport replay to the public AB/C passenger/property outputs.</p></div><div><span>5</span><strong>Percentile gate</strong><p>Blocked until the peer-population calculation is reconstructed and validated exactly.</p></div><div><span>6</span><strong>TRI gate</strong><p>Only after actuarial testing against insurer claims and exposure.</p></div></div></section>
    <section className="t3-note-panel"><strong>Historical integrity rule</strong><p>A future FMCSA methodology activation must create a new ruleset. It must never rewrite a result that was calculated under an older ruleset or source as-of state.</p></section>
  </main>;
}

function SourcesPage({ health, schema }: { health: SourceHealthPayload | null; schema: SchemaRegistry | null }) {
  const healthById = useMemo(() => new Map((health?.sources ?? []).map((source) => [source.id, source])), [health]);
  const groups = useMemo(() => {
    const map = new Map<string, SourceCatalogEntry[]>();
    for (const source of sourceCatalog) {
      const current = map.get(source.family) ?? [];
      current.push(source);
      map.set(source.family, current);
    }
    return [...map.entries()];
  }, []);
  return <main className="t3-main"><PageHeading eyebrow="Data lineage & operating contract" title="Data Sources" copy={`All ${schema?.source_count ?? sourceCatalog.length} configured FMCSA/DOT datasets, why they exist in Transport3r, their update cadence, and the job each performs in underwriting or validation.`} action={<div className="t3-asof"><span>Health snapshot</span><strong>{formatDateTime(health?.generated_at)}</strong></div>} />
    <section className="t3-mini-stats"><div><span>Registered datasets</span><strong>{schema?.source_count ?? sourceCatalog.length}</strong><small>Version-controlled registry</small></div><div><span>Registered fields</span><strong>{schema?.field_count?.toLocaleString() ?? '—'}</strong><small>Persisted schema snapshot</small></div><div><span>Healthy probes</span><strong>{health?.healthy_count ?? health?.sources.filter((source) => source.status === 'healthy').length ?? '—'}</strong><small>Latest automated probe</small></div><div><span>Failed probes</span><strong>{health?.failed_count ?? health?.sources.filter((source) => source.status === 'failed').length ?? '—'}</strong><small>Not hidden from the UI</small></div></section>
    <div className="t3-source-groups">{groups.map(([family, sources]) => <section className="t3-panel t3-source-group" key={family}><div className="t3-source-group-head"><div><div className="t3-eyebrow">{sources[0]?.cadence}</div><h2>{family}</h2></div><span>{sources.length} source{sources.length === 1 ? '' : 's'}</span></div><div className="t3-source-list"><div className="t3-source-row header"><span>Status</span><span>Dataset</span><span>Purpose in Transport3r</span><span>Scope / history</span><span>Updated</span></div>{sources.map((source) => { const status = healthById.get(source.id); return <div className="t3-source-row" key={source.id}><span><i className={`t3-source-dot ${status?.status ?? 'pending'}`}/>{status?.status ?? 'pending'}</span><span><strong>{source.name}</strong><code>{source.id}</code><small>{source.tier}</small></span><span>{source.role}</span><span>{source.scope}<small>{source.history}</small></span><span>{formatDateTime(status?.rows_updated_at)}<small>{status?.schema_fields ?? '—'} fields</small></span></div>; })}</div></section>)}</div>
  </main>;
}

export default function WorkspaceApp() {
  const [page, setPage] = useState<Page>(() => pageFromHash());
  const [health, setHealth] = useState<SourceHealthPayload | null>(null);
  const [schema, setSchema] = useState<SchemaRegistry | null>(null);

  useEffect(() => {
    const onHash = () => setPage(pageFromHash());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    const title = NAV.find((item) => item.id === page)?.label ?? 'Overview';
    document.title = `${title} · Transport3r`;
  }, [page]);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/source-health.json`, { cache: 'no-store' })
      .then((response) => response.ok ? response.json() as Promise<SourceHealthPayload> : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then(setHealth)
      .catch(() => setHealth({ generated_at: null, sources: [] }));
    loadSchemaRegistry().then(setSchema).catch(() => setSchema(null));
  }, []);

  return <Shell page={page} health={health}>
    {page === 'overview' && <OverviewPage health={health} schema={schema} />}
    {page === 'carriers' && <CarriersPage />}
    {page === 'portfolio' && <PortfolioPage />}
    {page === 'alerts' && <AlertsPage health={health} />}
    {page === 'methodology' && <MethodologyPage />}
    {page === 'sources' && <SourcesPage health={health} schema={schema} />}
  </Shell>;
}

