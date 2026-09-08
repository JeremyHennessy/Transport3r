import { FormEvent, useEffect, useMemo, useState } from 'react';
import sourceCatalog from '../data/fmcsa_sources.json';

type Page = 'overview' | 'prospect' | 'portfolio' | 'alerts' | 'methodology' | 'sources';
type EvidenceClass = 'OFFICIAL_FMCSA' | 'TRANSPORT_CALCULATED' | 'TRANSPORT_MODELLED';

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
  sources: SourceHealthEntry[];
};

type DataRow = Record<string, unknown>;

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
  raw: DataRow;
};

const DATAHUB = 'https://data.transportation.gov/resource';

const nav: Array<{ id: Page; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'prospect', label: 'Carrier Search' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'methodology', label: 'Methodology' },
  { id: 'sources', label: 'Source Health' },
];

function value(row: DataRow, keys: string[]): string | undefined {
  for (const key of keys) {
    const v = row[key];
    if (v !== undefined && v !== null && String(v).trim() !== '') return String(v);
  }
  return undefined;
}

function carrierFromRow(row: DataRow): Carrier {
  return {
    dotNumber: value(row, ['dot_number', 'usdot_number', 'usdot_num', 'dot_no']) ?? 'Unknown',
    legalName: value(row, ['legal_name', 'carrier_name', 'name']) ?? 'Unnamed carrier',
    dbaName: value(row, ['dba_name', 'dba']),
    city: value(row, ['phy_city', 'physical_city', 'city']),
    state: value(row, ['phy_state', 'physical_state', 'state']),
    operation: value(row, ['carrier_operation', 'carrier_operation_desc', 'operation']),
    powerUnits: value(row, ['nbr_power_unit', 'power_units', 'total_power_units']),
    drivers: value(row, ['driver_total', 'total_drivers', 'drivers']),
    mileage: value(row, ['mcs150_mileage', 'mileage', 'vmt']),
    mileageYear: value(row, ['mcs150_mileage_year', 'mileage_year', 'vmt_year']),
    raw: row,
  };
}

function formatNumber(value?: string): string {
  if (!value) return '—';
  const numeric = Number(value.replaceAll(',', ''));
  return Number.isFinite(numeric) ? numeric.toLocaleString() : value;
}

function EvidenceBadge({ kind }: { kind: EvidenceClass }) {
  const labels: Record<EvidenceClass, string> = {
    OFFICIAL_FMCSA: 'Official FMCSA',
    TRANSPORT_CALCULATED: 'Transport calculated',
    TRANSPORT_MODELLED: 'Transport modelled',
  };
  return <span className={`evidence-badge evidence-${kind.toLowerCase()}`}>{labels[kind]}</span>;
}

function Wordmark() {
  return (
    <button className="wordmark" onClick={() => window.location.hash = '#/overview'} aria-label="Transport3r home">
      <span className="wordmark-mark" aria-hidden="true">
        <svg viewBox="0 0 42 42" role="img">
          <path d="M8 10.5h26v6H23.8V34h-6V16.5H8z" />
          <path d="M27 21h7v13h-7z" className="mark-accent" />
        </svg>
      </span>
      <span>Transport<span className="wordmark-three">3r</span></span>
    </button>
  );
}

function StatCard({ label, value, detail, tone = 'default' }: { label: string; value: string; detail: string; tone?: 'default' | 'orange' | 'green' }) {
  return (
    <article className={`stat-card stat-${tone}`}>
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}</div>
      <div className="stat-detail">{detail}</div>
    </article>
  );
}

function Overview({ sourceHealth }: { sourceHealth: SourceHealthPayload }) {
  const healthy = sourceHealth.sources.filter((source) => source.status === 'healthy').length;
  const checked = sourceHealth.sources.filter((source) => source.status !== 'pending').length;
  const core = sourceCatalog.filter((source) => source.tier === 'core').length;

  return (
    <main className="page-shell">
      <section className="hero-panel">
        <div className="hero-copy">
          <div className="eyebrow">Transportation insurance intelligence</div>
          <h1>Underwrite the carrier behind the submission.</h1>
          <p>
            Transport3r brings FMCSA census, inspections, violations, crashes, SMS, authority and insurance evidence into one auditable carrier view—then keeps official facts separate from calculated and modelled risk.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href="#/prospect">Search a carrier</a>
            <a className="secondary-button" href="#/sources">Inspect source health</a>
          </div>
        </div>
        <div className="hero-proof">
          <div className="proof-header">Evidence contract</div>
          <div className="proof-row"><EvidenceBadge kind="OFFICIAL_FMCSA" /><span>Published government value or record</span></div>
          <div className="proof-row"><EvidenceBadge kind="TRANSPORT_CALCULATED" /><span>Deterministic reproduction from source inputs</span></div>
          <div className="proof-row"><EvidenceBadge kind="TRANSPORT_MODELLED" /><span>Insurance-oriented inference, never presented as FMCSA</span></div>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard label="FMCSA connectors" value={String(sourceCatalog.length)} detail="Configured official DataHub datasets" />
        <StatCard label="Core underwriting sources" value={String(core)} detail="Census, safety, SMS, authority and insurance" tone="orange" />
        <StatCard label="Sources probed" value={`${checked}/${sourceCatalog.length}`} detail={checked ? `${healthy} healthy on latest probe` : 'Initial automated probe has not run yet'} />
        <StatCard label="SMS engines" value="2" detail="v3.21 active + approved preview kept separate" tone="green" />
      </section>

      <section className="content-grid two-thirds">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <div className="eyebrow">Underwriting workflow</div>
              <h2>Decision-first carrier review</h2>
            </div>
            <span className="status-pill status-build">Foundation build</span>
          </div>
          <div className="workflow-list">
            <div className="workflow-item"><span className="step-number">01</span><div><strong>Resolve the carrier</strong><p>USDOT-first identity, operation, fleet scale, mileage and authority.</p></div></div>
            <div className="workflow-item"><span className="step-number">02</span><div><strong>Trace safety evidence</strong><p>Inspections → units/VINs → violations/OOS → crashes → monthly SMS inputs.</p></div></div>
            <div className="workflow-item"><span className="step-number">03</span><div><strong>Verify legal/coverage continuity</strong><p>MOTUS authority, revocation/suspension, insurance and filing history.</p></div></div>
            <div className="workflow-item"><span className="step-number">04</span><div><strong>Calculate, then model</strong><p>Reproduce FMCSA methodology before introducing proprietary underwriting risk.</p></div></div>
          </div>
        </article>

        <aside className="panel decision-panel">
          <div className="eyebrow">Material alerts</div>
          <h2>Hard facts stay above the score.</h2>
          <p>Active OOS orders, authority revocations and coverage interruptions will be surfaced independently of any future composite TRI score.</p>
          <div className="alert-rule critical"><span>Critical</span><strong>Federal OOS / authority revoked</strong></div>
          <div className="alert-rule high"><span>High</span><strong>Recent severe crash / OOS deterioration</strong></div>
          <div className="alert-rule watch"><span>Watch</span><strong>Stale census / abrupt fleet change</strong></div>
        </aside>
      </section>

      <section className="panel source-clock-panel">
        <div className="panel-heading">
          <div>
            <div className="eyebrow">Source clocks</div>
            <h2>Freshness is dataset-specific.</h2>
          </div>
        </div>
        <div className="clock-grid">
          <div><strong>Daily safety</strong><span>Company Census, crash and inspection families</span><small>FMCSA describes these as based on roughly 24-hour-old source data.</small></div>
          <div><strong>Daily authority</strong><span>Modern MOTUS baseline + difference files</span><small>Authority and insurance changes are tracked independently of SMS.</small></div>
          <div><strong>Monthly SMS</strong><span>Four inputs + four official output files</span><small>Monthly calculation snapshots are preserved as their own as-of state.</small></div>
        </div>
      </section>
    </main>
  );
}

function CarrierSearch() {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<Carrier[]>([]);
  const [selected, setSelected] = useState<Carrier | null>(null);

  async function search(event: FormEvent) {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    setLoading(true);
    setError(null);
    setSelected(null);
    try {
      const params = new URLSearchParams({ '$limit': '25' });
      if (/^\d+$/.test(q)) params.set('$where', `dot_number=${Number(q)}`);
      else params.set('$q', q);
      const response = await fetch(`${DATAHUB}/az4n-8mr2.json?${params.toString()}`);
      if (!response.ok) throw new Error(`DOT DataHub returned HTTP ${response.status}`);
      const rows = await response.json() as DataRow[];
      setResults(rows.map(carrierFromRow));
      if (rows.length === 1) setSelected(carrierFromRow(rows[0]));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Carrier search failed');
      setResults([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="page-shell">
      <section className="page-heading">
        <div>
          <div className="eyebrow">Nationwide carrier intelligence</div>
          <h1>Carrier Search</h1>
          <p>Search the current FMCSA Company Census directly from DOT DataHub. The prototype uses USDOT as the primary carrier identity.</p>
        </div>
        <EvidenceBadge kind="OFFICIAL_FMCSA" />
      </section>

      <section className="search-panel panel">
        <form onSubmit={search} className="carrier-search-form">
          <div className="search-field">
            <label htmlFor="carrier-query">USDOT number or carrier name</label>
            <div className="search-control">
              <input id="carrier-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. 178538 or carrier legal name" autoComplete="off" />
              <button className="primary-button" disabled={loading}>{loading ? 'Searching…' : 'Search FMCSA'}</button>
            </div>
          </div>
        </form>
        <div className="source-note"><span className="live-dot" /> Live public query: Company Census dataset <code>az4n-8mr2</code></div>
        {error && <div className="inline-error">{error}. The source-health page can confirm whether DataHub is currently reachable.</div>}
      </section>

      <section className="carrier-layout">
        <div className="panel results-panel">
          <div className="panel-heading compact"><h2>Results</h2><span className="muted">{results.length ? `${results.length} returned` : 'No search run'}</span></div>
          {!results.length && !loading && <div className="empty-state"><strong>Start with a USDOT number when possible.</strong><p>Name search is broader; USDOT gives the cleanest entity resolution and downstream joins.</p></div>}
          <div className="result-list">
            {results.map((carrier, index) => (
              <button key={`${carrier.dotNumber}-${index}`} className={`carrier-result ${selected?.dotNumber === carrier.dotNumber ? 'selected' : ''}`} onClick={() => setSelected(carrier)}>
                <div><strong>{carrier.legalName}</strong>{carrier.dbaName && <span className="dba">DBA {carrier.dbaName}</span>}</div>
                <div className="carrier-result-meta"><span>USDOT {carrier.dotNumber}</span><span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || 'Location unavailable'}</span></div>
              </button>
            ))}
          </div>
        </div>

        <div className="panel carrier-detail-panel">
          {!selected ? (
            <div className="empty-state large"><strong>Carrier 360</strong><p>Select a result to inspect the official census snapshot. Inspection, crash, MOTUS and SMS drill-throughs are being wired to this USDOT spine next.</p></div>
          ) : (
            <>
              <div className="carrier-title-row">
                <div><div className="eyebrow">Carrier 360 · census snapshot</div><h2>{selected.legalName}</h2>{selected.dbaName && <p>DBA {selected.dbaName}</p>}</div>
                <EvidenceBadge kind="OFFICIAL_FMCSA" />
              </div>
              <div className="identity-strip">
                <div><span>USDOT</span><strong>{selected.dotNumber}</strong></div>
                <div><span>Location</span><strong>{[selected.city, selected.state].filter(Boolean).join(', ') || '—'}</strong></div>
                <div><span>Operation</span><strong>{selected.operation || '—'}</strong></div>
              </div>
              <div className="carrier-metrics">
                <div><span>Power units</span><strong>{formatNumber(selected.powerUnits)}</strong></div>
                <div><span>Drivers</span><strong>{formatNumber(selected.drivers)}</strong></div>
                <div><span>Reported VMT</span><strong>{formatNumber(selected.mileage)}</strong><small>{selected.mileageYear ? `Mileage year ${selected.mileageYear}` : 'Mileage year unavailable'}</small></div>
              </div>
              <div className="next-evidence">
                <h3>Next evidence joins</h3>
                <div className="evidence-roadmap">
                  <span>Inspections</span><span>Violations</span><span>Observed VINs</span><span>Crashes</span><span>SMS</span><span>MOTUS authority</span><span>Insurance</span><span>Related carriers</span>
                </div>
              </div>
              <details className="raw-evidence"><summary>Raw census evidence</summary><pre>{JSON.stringify(selected.raw, null, 2)}</pre></details>
            </>
          )}
        </div>
      </section>
    </main>
  );
}

function Portfolio() {
  return (
    <main className="page-shell">
      <section className="page-heading"><div><div className="eyebrow">Insurance workflow</div><h1>Portfolio</h1><p>Continuous carrier monitoring will live here once insured, quoted or watched accounts are persisted.</p></div></section>
      <section className="panel empty-workspace">
        <div className="empty-icon">P</div>
        <h2>No portfolio has been loaded.</h2>
        <p>This is intentional. Transport3r will not invent exposure, policy or loss data. Portfolio records require an insurer-supplied account/policy spine or an explicitly saved watchlist.</p>
        <div className="empty-columns">
          <div><strong>Planned exposure</strong><span>Written premium, power units, VMT, limits, class and territory</span></div>
          <div><strong>Monitoring</strong><span>New crash, OOS, authority, insurance and monthly SMS deltas</span></div>
          <div><strong>Validation</strong><span>Score deciles against actual claims, frequency and severity</span></div>
        </div>
      </section>
    </main>
  );
}

function Alerts() {
  const rules = [
    ['Critical', 'Federal / New Entrant operational OOS order', 'FMCSA OOS source'],
    ['Critical', 'Operating authority suspended or revoked', 'MOTUS RevokeSuspend'],
    ['Critical', 'Required insurance no longer on file', 'MOTUS insurance + history'],
    ['High', 'Recent fatal or injury crash', 'FMCSA crash records'],
    ['High', 'Material OOS-rate deterioration', 'Inspection + violation trend'],
    ['Watch', 'Stale MCS-150 / reported mileage', 'Company Census history'],
    ['Watch', 'Abrupt fleet-size or observed-VIN change', 'Census + inspection-unit history'],
  ];
  return (
    <main className="page-shell">
      <section className="page-heading"><div><div className="eyebrow">Event monitoring</div><h1>Alerts</h1><p>Material facts remain independent from future composite model scores.</p></div></section>
      <section className="panel">
        <div className="panel-heading"><div><h2>Alert rule registry</h2><p>Rules are defined; carrier-level evaluation begins once persistent carrier snapshots are present.</p></div><span className="status-pill status-build">No fabricated events</span></div>
        <div className="rule-table">
          {rules.map(([level, rule, source]) => <div className="rule-row" key={rule}><span className={`rule-level level-${level.toLowerCase()}`}>{level}</span><strong>{rule}</strong><span>{source}</span></div>)}
        </div>
      </section>
    </main>
  );
}

function Methodology() {
  return (
    <main className="page-shell">
      <section className="page-heading"><div><div className="eyebrow">Versioned calculation contract</div><h1>Methodology</h1><p>Official outputs, reproduced calculations and proprietary underwriting models are separate products of separate rulesets.</p></div></section>
      <section className="methodology-grid">
        <article className="panel method-card active-method">
          <div className="method-top"><span className="status-pill status-live">Active</span><EvidenceBadge kind="TRANSPORT_CALCULATED" /></div>
          <div className="eyebrow">FMCSA SMS</div><h2>v3.21 · June 2026</h2>
          <p>Current live methodology. The reproduction harness will be validated against FMCSA monthly output files before any internal risk model is trusted.</p>
          <ul><li>24-month safety-event windows</li><li>Current severity + OOS weighting</li><li>Recency weighting</li><li>Relevant-inspection denominators</li><li>Exposure/utilization logic where applicable</li></ul>
        </article>
        <article className="panel method-card preview-method">
          <div className="method-top"><span className="status-pill status-preview">Preview</span><EvidenceBadge kind="TRANSPORT_CALCULATED" /></div>
          <div className="eyebrow">FMCSA approved future methodology</div><h2>Next SMS · isolated engine</h2>
          <p>Kept independently because FMCSA has approved material changes but has not activated them as the current SMS methodology.</p>
          <ul><li>Violation grouping changes</li><li>1 / 2 violation weights</li><li>Compliance-category reorganization</li><li>Proportionate percentile mechanics</li><li>Changed intervention thresholds</li></ul>
        </article>
      </section>
      <section className="panel formula-contract">
        <div className="panel-heading"><div><div className="eyebrow">Calculation provenance</div><h2>Every result must be replayable.</h2></div></div>
        <div className="contract-grid"><div><strong>Source as-of</strong><span>Which FMCSA snapshot supplied the inputs</span></div><div><strong>Ruleset</strong><span>Exact methodology version</span></div><div><strong>Inputs</strong><span>Numerators, denominators, event weights and exposure</span></div><div><strong>Confidence</strong><span>Observation sufficiency and known source limitations</span></div></div>
      </section>
    </main>
  );
}

function SourceHealth({ sourceHealth }: { sourceHealth: SourceHealthPayload }) {
  const rows = useMemo(() => {
    const healthById = new Map(sourceHealth.sources.map((source) => [source.id, source]));
    return sourceCatalog.map((source) => ({ ...source, health: healthById.get(source.id) }));
  }, [sourceHealth]);

  return (
    <main className="page-shell wide-shell">
      <section className="page-heading"><div><div className="eyebrow">Data lineage</div><h1>Source Health</h1><p>Availability and schema checks for the FMCSA/DOT datasets that underpin Transport3r.</p></div><div className="as-of-block"><span>Last automated probe</span><strong>{sourceHealth.generated_at ? new Date(sourceHealth.generated_at).toLocaleString() : 'Not run yet'}</strong></div></section>
      <section className="panel source-table-panel">
        <div className="source-table">
          <div className="source-row source-header"><span>Status</span><span>Dataset</span><span>Family</span><span>Cadence</span><span>Role</span><span>Schema</span></div>
          {rows.map((source) => {
            const status = source.health?.status ?? 'pending';
            return <div className="source-row" key={source.id}>
              <span><span className={`health-dot health-${status}`} /> {status}</span>
              <span><strong>{source.name}</strong><code>{source.id}</code></span>
              <span>{source.family}</span>
              <span>{source.cadence}</span>
              <span>{source.role}</span>
              <span>{source.health?.schema_fields ?? '—'} fields</span>
            </div>;
          })}
        </div>
      </section>
    </main>
  );
}

function App() {
  const route = window.location.hash.replace('#/', '') as Page;
  const [page, setPage] = useState<Page>(nav.some((item) => item.id === route) ? route : 'overview');
  const [sourceHealth, setSourceHealth] = useState<SourceHealthPayload>({ generated_at: null, sources: [] });

  useEffect(() => {
    const onHash = () => {
      const next = window.location.hash.replace('#/', '') as Page;
      setPage(nav.some((item) => item.id === next) ? next : 'overview');
    };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/source-health.json`, { cache: 'no-store' })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((payload: SourceHealthPayload) => setSourceHealth(payload))
      .catch(() => setSourceHealth({ generated_at: null, sources: [] }));
  }, []);

  return (
    <div className="app-shell">
      <header className="top-nav">
        <Wordmark />
        <nav aria-label="Primary navigation">
          {nav.map((item) => <a key={item.id} href={`#/${item.id}`} className={page === item.id ? 'active' : ''}>{item.label}</a>)}
        </nav>
        <div className="nav-meta"><span className="nav-dot" /><span>FMCSA workspace</span></div>
      </header>
      {page === 'overview' && <Overview sourceHealth={sourceHealth} />}
      {page === 'prospect' && <CarrierSearch />}
      {page === 'portfolio' && <Portfolio />}
      {page === 'alerts' && <Alerts />}
      {page === 'methodology' && <Methodology />}
      {page === 'sources' && <SourceHealth sourceHealth={sourceHealth} />}
      <footer className="app-footer"><span>Transport3r</span><span>FMCSA-first transportation insurance intelligence</span><span>Evidence before score</span></footer>
    </div>
  );
}

export default App;
