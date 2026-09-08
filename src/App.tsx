import { FormEvent, useEffect, useMemo, useState } from 'react';
import sourceCatalog from '../data/fmcsa_sources.json';
import {
  CarrierEvidence,
  activeInsuranceRows,
  authorityStatuses,
  loadCarrierEvidence,
  observedVins,
  officialSmsRows,
  oosViolationCount,
  rowCount,
  severeCrashCounts,
} from './carrierEvidence';
import { DataRow, readNumber, readValue, schemaLabel } from './datahub';

type Page = 'overview' | 'prospect' | 'portfolio' | 'alerts' | 'methodology' | 'sources';
type EvidenceClass = 'OFFICIAL_FMCSA' | 'TRANSPORT_CALCULATED' | 'TRANSPORT_MODELLED';
type CarrierTab = 'summary' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence';

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

function carrierFromRow(row: DataRow): Carrier {
  return {
    dotNumber: readValue(row, ['DOT_NUMBER', 'USDOT_NUMBER', 'USDOT_NUM', 'DOT_NO']) ?? 'Unknown',
    legalName: readValue(row, ['LEGAL_NAME', 'CARRIER_NAME', 'NAME']) ?? 'Unnamed carrier',
    dbaName: readValue(row, ['DBA_NAME', 'DBA']),
    city: readValue(row, ['PHY_CITY', 'PHYSICAL_CITY', 'CITY']),
    state: readValue(row, ['PHY_STATE', 'PHYSICAL_STATE', 'STATE']),
    operation: readValue(row, ['CARRIER_OPERATION', 'CARRIER_OPERATION_DESC', 'OPERATION']),
    powerUnits: readValue(row, ['NBR_POWER_UNIT', 'POWER_UNITS', 'TOTAL_POWER_UNITS']),
    drivers: readValue(row, ['DRIVER_TOTAL', 'TOTAL_DRIVERS', 'DRIVERS']),
    mileage: readValue(row, ['MCS150_MILEAGE', 'MILEAGE', 'VMT']),
    mileageYear: readValue(row, ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR', 'VMT_YEAR']),
    raw: row,
  };
}

function formatNumber(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''));
  return Number.isFinite(numeric) ? numeric.toLocaleString() : String(value);
}

function formatDate(raw?: string): string {
  if (!raw) return '—';
  const date = new Date(raw);
  return Number.isNaN(date.valueOf()) ? raw : date.toLocaleDateString();
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
            <span className="status-pill status-live">Carrier evidence live</span>
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
          <p>OOS history, authority changes, serious crashes and coverage evidence are surfaced independently of any future composite TRI score.</p>
          <div className="alert-rule critical"><span>Critical</span><strong>Current operational/legal blockers once deterministically resolved</strong></div>
          <div className="alert-rule high"><span>High</span><strong>Recent severe crash / OOS deterioration</strong></div>
          <div className="alert-rule watch"><span>Watch</span><strong>Stale census / abrupt fleet change</strong></div>
        </aside>
      </section>

      <section className="panel source-clock-panel">
        <div className="panel-heading"><div><div className="eyebrow">Source clocks</div><h2>Freshness is dataset-specific.</h2></div></div>
        <div className="clock-grid">
          <div><strong>Daily safety</strong><span>Company Census, crash and inspection families</span><small>FMCSA describes these as based on roughly 24-hour-old source data.</small></div>
          <div><strong>Daily authority</strong><span>Modern MOTUS baseline + difference files</span><small>Authority and insurance changes are tracked independently of SMS.</small></div>
          <div><strong>Monthly SMS</strong><span>Four inputs + four official output files</span><small>Monthly calculation snapshots are preserved as their own as-of state.</small></div>
        </div>
      </section>
    </main>
  );
}

function DataMetric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="evidence-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function EvidenceErrorList({ evidence }: { evidence: CarrierEvidence }) {
  const errors = Object.entries(evidence.errors);
  if (!errors.length) return <div className="evidence-ok"><span className="live-dot" /> All requested carrier evidence joins returned without source errors.</div>;
  return (
    <div className="evidence-errors">
      <strong>{errors.length} source join{errors.length === 1 ? '' : 's'} unavailable</strong>
      {errors.map(([key, message]) => <div key={key}><code>{key}</code><span>{message}</span></div>)}
    </div>
  );
}

function RecentInspectionTable({ evidence }: { evidence: CarrierEvidence }) {
  const rows = evidence.slices.inspections?.rows.slice(0, 10) ?? [];
  if (!rows.length) return <div className="empty-state"><strong>No inspection rows returned.</strong></div>;
  return (
    <div className="compact-table">
      <div className="compact-row compact-header"><span>Date</span><span>State</span><span>Level</span><span>Vehicle viol.</span><span>Driver viol.</span></div>
      {rows.map((row, index) => (
        <div className="compact-row" key={`${readValue(row, ['INSPECTION_ID']) ?? index}`}>
          <span>{formatDate(readValue(row, ['INSP_DATE', 'INSPECTION_DATE', 'REPORT_DATE']))}</span>
          <span>{readValue(row, ['REPORT_STATE', 'STATE']) ?? '—'}</span>
          <span>{readValue(row, ['INSP_LEVEL_ID', 'INSPECTION_LEVEL', 'LEVEL']) ?? '—'}</span>
          <span>{formatNumber(readNumber(row, ['VEHICLE_VIOLATIONS', 'VEH_VIOLATIONS', 'VEH_VIOL_TOTAL']))}</span>
          <span>{formatNumber(readNumber(row, ['DRIVER_VIOLATIONS', 'DRV_VIOLATIONS', 'DRIVER_VIOL_TOTAL']))}</span>
        </div>
      ))}
    </div>
  );
}

function CrashTable({ evidence }: { evidence: CarrierEvidence }) {
  const rows = evidence.slices.crash?.rows.slice(0, 10) ?? [];
  if (!rows.length) return <div className="empty-state"><strong>No crash rows returned.</strong></div>;
  return (
    <div className="compact-table crash-table">
      <div className="compact-row compact-header"><span>Date</span><span>State</span><span>Fatalities</span><span>Injuries</span><span>Tow-away</span></div>
      {rows.map((row, index) => (
        <div className="compact-row" key={`${readValue(row, ['REPORT_NUMBER']) ?? index}`}>
          <span>{formatDate(readValue(row, ['CRASH_DATE', 'REPORT_DATE']))}</span>
          <span>{readValue(row, ['REPORT_STATE', 'STATE']) ?? '—'}</span>
          <span>{formatNumber(readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT']))}</span>
          <span>{formatNumber(readNumber(row, ['INJURIES', 'INJURY_CNT', 'INJURY_COUNT']))}</span>
          <span>{readValue(row, ['TOW_AWAY', 'TOWAWAY', 'TOW_AWAY_FLAG']) ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

function FleetTable({ evidence }: { evidence: CarrierEvidence }) {
  const rows = evidence.slices.units?.rows.slice(0, 16) ?? [];
  if (!rows.length) return <div className="empty-state"><strong>No inspection-unit rows returned.</strong></div>;
  return (
    <div className="compact-table fleet-table">
      <div className="compact-row compact-header"><span>VIN</span><span>Make</span><span>Type</span><span>Plate</span><span>State</span></div>
      {rows.map((row, index) => (
        <div className="compact-row" key={`${readValue(row, ['VIN']) ?? index}`}>
          <span className="mono-cell">{readValue(row, ['VIN', 'VEHICLE_IDENTIFICATION_NUMBER']) ?? '—'}</span>
          <span>{readValue(row, ['VEHICLE_MAKE', 'MAKE']) ?? '—'}</span>
          <span>{readValue(row, ['UNIT_TYPE', 'VEHICLE_TYPE']) ?? '—'}</span>
          <span>{readValue(row, ['LICENSE', 'LICENSE_PLATE', 'PLATE']) ?? '—'}</span>
          <span>{readValue(row, ['LICENSE_STATE', 'PLATE_STATE', 'STATE']) ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

function AuthorityTable({ evidence }: { evidence: CarrierEvidence }) {
  const rows = evidence.slices.motusCarrier?.rows ?? [];
  if (!rows.length) return <div className="empty-state"><strong>No MOTUS carrier/authority rows returned.</strong></div>;
  return (
    <div className="compact-table authority-table">
      <div className="compact-row compact-header"><span>Docket</span><span>Type</span><span>Status</span><span>Legal name</span></div>
      {rows.slice(0, 20).map((row, index) => (
        <div className="compact-row" key={`${readValue(row, ['DOCKET_NUMBER']) ?? index}`}>
          <span>{readValue(row, ['DOCKET_NUMBER', 'DOCKET_NO']) ?? '—'}</span>
          <span>{readValue(row, ['OP_AUTH_TYPE', 'AUTH_TYPE']) ?? '—'}</span>
          <span>{readValue(row, ['OP_AUTH_STATUS', 'AUTH_STATUS']) ?? '—'}</span>
          <span>{readValue(row, ['LEGAL_NAME', 'CARRIER_NAME']) ?? '—'}</span>
        </div>
      ))}
    </div>
  );
}

function InsuranceTable({ rows, history = false }: { rows: DataRow[]; history?: boolean }) {
  if (!rows.length) return <div className="empty-state"><strong>No {history ? 'insurance-history' : 'active/pending insurance'} rows returned.</strong></div>;
  return (
    <div className="compact-table insurance-table">
      <div className="compact-row compact-header"><span>Policy</span><span>Type</span><span>Insurer</span><span>Limit</span><span>{history ? 'Cancellation / status' : 'Transaction'}</span></div>
      {rows.slice(0, 25).map((row, index) => (
        <div className="compact-row" key={`${readValue(row, ['POLICY_NO', 'POLICY_NUMBER']) ?? index}`}>
          <span>{readValue(row, ['POLICY_NO', 'POLICY_NUMBER']) ?? '—'}</span>
          <span>{readValue(row, ['INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']) ?? '—'}</span>
          <span>{readValue(row, ['INSURANCE_COMPANY_NAME', 'INS_COMPANY_NAME', 'COMPANY_NAME']) ?? '—'}</span>
          <span>{formatNumber(readNumber(row, ['MAX_COV_AMOUNT', 'MAX_COVERAGE_AMOUNT', 'UNDERL_LIM_AMOUNT']))}</span>
          <span>{formatDate(readValue(row, history ? ['CANCEL_EFFECTIVE_DATE', 'CANCELLATION_DATE', 'TRANS_DATE'] : ['TRANS_DATE', 'EFFECTIVE_DATE']))}</span>
        </div>
      ))}
    </div>
  );
}

function SmsOfficialPanel({ evidence }: { evidence: CarrierEvidence }) {
  const rows = officialSmsRows(evidence);
  if (!rows.length) return <div className="empty-state"><strong>No public property-carrier SMS output row returned for this USDOT.</strong><p>This can be a legitimate data-sufficiency or carrier-class result; it is not treated as a zero-risk score.</p></div>;
  const sourceId = evidence.slices.smsABProperty?.rows.length ? '4y6x-dmck' : 'h9zy-gjn8';
  const row = rows[0];
  const entries = Object.entries(row)
    .filter(([, raw]) => raw !== null && raw !== undefined && String(raw).trim() !== '')
    .filter(([key]) => /(basic|percent|measure|alert|threshold|power|driver|carrier|dot|rating|inspection|crash)/i.test(key))
    .slice(0, 28);
  return (
    <div className="sms-official-grid">
      {entries.map(([key, raw]) => (
        <div key={key}><span>{schemaLabel(evidence.registry, sourceId, key)}</span><strong>{String(raw)}</strong></div>
      ))}
    </div>
  );
}

function CarrierDecisionSummary({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const crashes = severeCrashCounts(evidence);
  const auth = authorityStatuses(evidence);
  const vins = observedVins(evidence);
  const oosViolations = oosViolationCount(evidence);
  const revocationHistory = rowCount(evidence.slices.motusRevokeSuspend);
  const entrantOosHistory = rowCount(evidence.slices.newEntrantOos);
  const activeInsurance = activeInsuranceRows(evidence).length;

  const concerns: string[] = [];
  if (crashes.fatal) concerns.push(`${crashes.fatal} crash record${crashes.fatal === 1 ? '' : 's'} with reported fatality count > 0 in the loaded crash window`);
  if (oosViolations) concerns.push(`${oosViolations} loaded inspection violation${oosViolations === 1 ? '' : 's'} flagged OOS`);
  if (revocationHistory) concerns.push(`${revocationHistory} MOTUS revocation/suspension history record${revocationHistory === 1 ? '' : 's'}; current effect must be read from the underlying record`);
  if (entrantOosHistory) concerns.push(`${entrantOosHistory} New Entrant OOS history record${entrantOosHistory === 1 ? '' : 's'}`);

  return (
    <section className="decision-summary">
      <div className="decision-summary-head">
        <div><div className="eyebrow">Deterministic account summary</div><h3>Underwriting evidence at a glance</h3></div>
        <EvidenceBadge kind="OFFICIAL_FMCSA" />
      </div>
      <div className="decision-summary-grid">
        <div><span>Scale</span><strong>{formatNumber(carrier.powerUnits)} power units · {formatNumber(carrier.drivers)} drivers</strong><p>Reported VMT {formatNumber(carrier.mileage)}{carrier.mileageYear ? ` (${carrier.mileageYear})` : ''}.</p></div>
        <div><span>Safety evidence</span><strong>{formatNumber(rowCount(evidence.slices.inspections))} inspections · {formatNumber(rowCount(evidence.slices.crash))} crashes</strong><p>{vins.length.toLocaleString()} unique VINs observed in loaded inspection-unit evidence.</p></div>
        <div><span>Authority / coverage</span><strong>{auth.length ? auth.join(', ') : 'No authority status returned'}</strong><p>{activeInsurance.toLocaleString()} active/pending MOTUS insurance filing row{activeInsurance === 1 ? '' : 's'} returned.</p></div>
        <div><span>Risk model</span><strong>TRI not scored yet</strong><p>The proprietary score remains blocked until the current SMS reproduction is validated against official monthly outputs.</p></div>
      </div>
      <div className={`deterministic-concerns ${concerns.length ? 'has-concerns' : ''}`}>
        <strong>{concerns.length ? 'Evidence requiring review' : 'No hard-review flags derived from the currently loaded checks'}</strong>
        {concerns.length ? <ul>{concerns.map((item) => <li key={item}>{item}</li>)}</ul> : <p>This is not a clearance decision; data sufficiency and source-specific limitations still apply.</p>}
      </div>
    </section>
  );
}

function Carrier360({ carrier, sourceHealth }: { carrier: Carrier; sourceHealth: SourceHealthPayload }) {
  const [tab, setTab] = useState<CarrierTab>('summary');
  const [evidence, setEvidence] = useState<CarrierEvidence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setLoading(true);
    setError(null);
    setEvidence(null);
    setTab('summary');
    loadCarrierEvidence(carrier.dotNumber)
      .then((loaded) => { if (current) setEvidence(loaded); })
      .catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : String(cause)); })
      .finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [carrier.dotNumber]);

  const tabs: Array<{ id: CarrierTab; label: string }> = [
    { id: 'summary', label: 'Summary' }, { id: 'safety', label: 'Safety' }, { id: 'fleet', label: 'Fleet' },
    { id: 'authority', label: 'Authority' }, { id: 'insurance', label: 'Insurance' }, { id: 'sms', label: 'SMS' }, { id: 'evidence', label: 'Evidence' },
  ];

  return (
    <div className="carrier-360">
      <div className="carrier-title-row">
        <div><div className="eyebrow">Carrier 360 · USDOT spine</div><h2>{carrier.legalName}</h2>{carrier.dbaName && <p>DBA {carrier.dbaName}</p>}</div>
        <EvidenceBadge kind="OFFICIAL_FMCSA" />
      </div>
      <div className="identity-strip">
        <div><span>USDOT</span><strong>{carrier.dotNumber}</strong></div>
        <div><span>Location</span><strong>{[carrier.city, carrier.state].filter(Boolean).join(', ') || '—'}</strong></div>
        <div><span>Operation</span><strong>{carrier.operation || '—'}</strong></div>
      </div>
      <div className="carrier-metrics">
        <div><span>Power units</span><strong>{formatNumber(carrier.powerUnits)}</strong></div>
        <div><span>Drivers</span><strong>{formatNumber(carrier.drivers)}</strong></div>
        <div><span>Reported VMT</span><strong>{formatNumber(carrier.mileage)}</strong><small>{carrier.mileageYear ? `Mileage year ${carrier.mileageYear}` : 'Mileage year unavailable'}</small></div>
      </div>

      {loading && <div className="evidence-loading"><span className="loading-spinner" /><div><strong>Loading FMCSA carrier evidence</strong><span>Inspections, VINs, violations, crashes, SMS, MOTUS and OOS sources are queried independently.</span></div></div>}
      {error && <div className="inline-error"><strong>Carrier evidence load failed.</strong> {error}</div>}

      {evidence && (
        <>
          <div className="carrier-tabs" role="tablist" aria-label="Carrier evidence sections">
            {tabs.map((item) => <button key={item.id} className={tab === item.id ? 'active' : ''} onClick={() => setTab(item.id)}>{item.label}</button>)}
          </div>

          {tab === 'summary' && <div className="carrier-tab-panel">
            <CarrierDecisionSummary carrier={carrier} evidence={evidence} />
            <div className="evidence-metric-grid">
              <DataMetric label="Inspections" value={formatNumber(rowCount(evidence.slices.inspections))} detail={evidence.slices.inspections?.truncated ? `${evidence.slices.inspections.rows.length} rows loaded` : 'Current daily inspection file'} />
              <DataMetric label="Violations" value={formatNumber(rowCount(evidence.slices.violations))} detail={`${formatNumber(oosViolationCount(evidence))} loaded OOS violations`} />
              <DataMetric label="Crashes" value={formatNumber(rowCount(evidence.slices.crash))} detail={`${formatNumber(severeCrashCounts(evidence).fatal)} fatality-involved loaded records`} />
              <DataMetric label="Observed VINs" value={formatNumber(observedVins(evidence).length)} detail="Observed in loaded inspection-unit evidence" />
              <DataMetric label="Insurance filings" value={formatNumber(rowCount(evidence.slices.motusInsurance))} detail="MOTUS active/pending source" />
              <DataMetric label="Official SMS rows" value={formatNumber(officialSmsRows(evidence).length)} detail="Public property-carrier output" />
            </div>
            <EvidenceErrorList evidence={evidence} />
          </div>}

          {tab === 'safety' && <div className="carrier-tab-panel">
            <div className="section-title"><div><div className="eyebrow">Daily safety evidence</div><h3>Inspections and crashes</h3></div><EvidenceBadge kind="OFFICIAL_FMCSA" /></div>
            <div className="evidence-metric-grid compact-metrics">
              <DataMetric label="Inspection records" value={formatNumber(rowCount(evidence.slices.inspections))} />
              <DataMetric label="Violation rows" value={formatNumber(rowCount(evidence.slices.violations))} />
              <DataMetric label="OOS violation rows" value={formatNumber(oosViolationCount(evidence))} />
              <DataMetric label="Crash records" value={formatNumber(rowCount(evidence.slices.crash))} />
            </div>
            <h4 className="subsection-label">Recent inspections</h4><RecentInspectionTable evidence={evidence} />
            <h4 className="subsection-label">Recent crashes</h4><CrashTable evidence={evidence} />
            <p className="evidence-disclaimer">Crash records represent reported crash involvement. They do not by themselves establish fault.</p>
          </div>}

          {tab === 'fleet' && <div className="carrier-tab-panel">
            <div className="section-title"><div><div className="eyebrow">Observed fleet</div><h3>Vehicles seen in inspections</h3></div><EvidenceBadge kind="OFFICIAL_FMCSA" /></div>
            <div className="evidence-metric-grid compact-metrics">
              <DataMetric label="Reported power units" value={formatNumber(carrier.powerUnits)} />
              <DataMetric label="Unique observed VINs" value={formatNumber(observedVins(evidence).length)} />
              <DataMetric label="Inspection-unit rows" value={formatNumber(rowCount(evidence.slices.units))} />
            </div>
            <FleetTable evidence={evidence} />
            <p className="evidence-disclaimer">Observed VINs prove an FMCSA inspection association, not current ownership or inclusion on an insured vehicle schedule.</p>
          </div>}

          {tab === 'authority' && <div className="carrier-tab-panel">
            <div className="section-title"><div><div className="eyebrow">Modern MOTUS</div><h3>Operating authority</h3></div><EvidenceBadge kind="OFFICIAL_FMCSA" /></div>
            <div className="evidence-metric-grid compact-metrics">
              <DataMetric label="Current/baseline authority rows" value={formatNumber(rowCount(evidence.slices.motusCarrier))} />
              <DataMetric label="Authority history rows" value={formatNumber(rowCount(evidence.slices.motusAuthHistory))} />
              <DataMetric label="Revoke/suspend history" value={formatNumber(rowCount(evidence.slices.motusRevokeSuspend))} />
              <DataMetric label="New Entrant OOS history" value={formatNumber(rowCount(evidence.slices.newEntrantOos))} />
            </div>
            <AuthorityTable evidence={evidence} />
          </div>}

          {tab === 'insurance' && <div className="carrier-tab-panel">
            <div className="section-title"><div><div className="eyebrow">Modern MOTUS</div><h3>Insurance filings</h3></div><EvidenceBadge kind="OFFICIAL_FMCSA" /></div>
            <h4 className="subsection-label">Active / pending filings</h4><InsuranceTable rows={evidence.slices.motusInsurance?.rows ?? []} />
            <h4 className="subsection-label">Insurance history</h4><InsuranceTable rows={evidence.slices.motusInsuranceHistory?.rows ?? []} history />
          </div>}

          {tab === 'sms' && <div className="carrier-tab-panel">
            <div className="section-title"><div><div className="eyebrow">Monthly Safety Measurement System</div><h3>Official public SMS output</h3></div><EvidenceBadge kind="OFFICIAL_FMCSA" /></div>
            <div className="evidence-metric-grid compact-metrics">
              <DataMetric label="SMS inspections" value={formatNumber(rowCount(evidence.slices.smsInspection))} detail="Current monthly input" />
              <DataMetric label="SMS violations" value={formatNumber(rowCount(evidence.slices.smsViolation))} detail="Current monthly input" />
              <DataMetric label="SMS crashes" value={formatNumber(rowCount(evidence.slices.smsCrash))} detail="Current monthly input" />
              <DataMetric label="Public output rows" value={formatNumber(officialSmsRows(evidence).length)} detail="AB or C property output" />
            </div>
            <SmsOfficialPanel evidence={evidence} />
            <div className="sms-replica-gate"><EvidenceBadge kind="TRANSPORT_CALCULATED" /><div><strong>SMS v3.21 replica gate</strong><span>Formula-derived Transport values will remain unavailable until the replay engine reproduces official output within defined tolerances.</span></div></div>
          </div>}

          {tab === 'evidence' && <div className="carrier-tab-panel">
            <div className="section-title"><div><div className="eyebrow">Lineage</div><h3>Carrier source coverage</h3></div></div>
            <div className="carrier-source-grid">
              {Object.entries(evidence.slices).map(([key, slice]) => <div key={key}><span>{key}</span><strong>{formatNumber(slice?.total ?? slice?.rows.length ?? 0)}</strong><small>{slice?.sourceId} · {slice?.truncated ? 'partial rows loaded' : 'query complete'}</small></div>)}
            </div>
            <EvidenceErrorList evidence={evidence} />
            <div className="as-of-note">Carrier evidence loaded {new Date(evidence.loadedAt).toLocaleString()}. Source-health snapshot: {sourceHealth.generated_at ? new Date(sourceHealth.generated_at).toLocaleString() : 'unavailable'}.</div>
            <details className="raw-evidence"><summary>Raw census evidence</summary><pre>{JSON.stringify(carrier.raw, null, 2)}</pre></details>
          </div>}
        </>
      )}
    </div>
  );
}

function CarrierSearch({ sourceHealth }: { sourceHealth: SourceHealthPayload }) {
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
    <main className="page-shell wide-shell">
      <section className="page-heading">
        <div><div className="eyebrow">Nationwide carrier intelligence</div><h1>Carrier Search</h1><p>Resolve a USDOT carrier and load the linked FMCSA safety, SMS, fleet-observation, MOTUS authority and insurance evidence.</p></div>
        <EvidenceBadge kind="OFFICIAL_FMCSA" />
      </section>

      <section className="search-panel panel">
        <form onSubmit={search} className="carrier-search-form">
          <div className="search-field"><label htmlFor="carrier-query">USDOT number or carrier name</label><div className="search-control"><input id="carrier-query" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="e.g. 178538 or carrier legal name" autoComplete="off" /><button className="primary-button" disabled={loading}>{loading ? 'Searching…' : 'Search FMCSA'}</button></div></div>
        </form>
        <div className="source-note"><span className="live-dot" /> Live public query: Company Census <code>az4n-8mr2</code> · downstream joins are schema-driven from the persisted 683-field registry.</div>
        {error && <div className="inline-error">{error}. The source-health page can confirm whether DataHub is currently reachable.</div>}
      </section>

      <section className="carrier-layout expanded-carrier-layout">
        <div className="panel results-panel">
          <div className="panel-heading compact"><h2>Results</h2><span className="muted">{results.length ? `${results.length} returned` : 'No search run'}</span></div>
          {!results.length && !loading && <div className="empty-state"><strong>Start with a USDOT number when possible.</strong><p>Name search is broader; USDOT gives the cleanest entity resolution and downstream joins.</p></div>}
          <div className="result-list">
            {results.map((carrier, index) => <button key={`${carrier.dotNumber}-${index}`} className={`carrier-result ${selected?.dotNumber === carrier.dotNumber ? 'selected' : ''}`} onClick={() => setSelected(carrier)}><div><strong>{carrier.legalName}</strong>{carrier.dbaName && <span className="dba">DBA {carrier.dbaName}</span>}</div><div className="carrier-result-meta"><span>USDOT {carrier.dotNumber}</span><span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || 'Location unavailable'}</span><span>{formatNumber(carrier.powerUnits)} PU</span></div></button>)}
          </div>
        </div>

        <div className="panel carrier-detail-panel">
          {!selected ? <div className="empty-state large"><strong>Carrier 360</strong><p>Select a carrier to load independently sourced inspections, violations, VIN observations, crashes, SMS inputs/output, MOTUS authority/insurance and OOS evidence.</p></div> : <Carrier360 carrier={selected} sourceHealth={sourceHealth} />}
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
        <div className="empty-icon">P</div><h2>No portfolio has been loaded.</h2><p>This is intentional. Transport3r will not invent exposure, policy or loss data. Portfolio records require an insurer-supplied account/policy spine or an explicitly saved watchlist.</p>
        <div className="empty-columns"><div><strong>Planned exposure</strong><span>Written premium, power units, VMT, limits, class and territory</span></div><div><strong>Monitoring</strong><span>New crash, OOS, authority, insurance and monthly SMS deltas</span></div><div><strong>Validation</strong><span>Score deciles against actual claims, frequency and severity</span></div></div>
      </section>
    </main>
  );
}

function Alerts() {
  const rules = [
    ['Critical', 'Current federal / New Entrant operational OOS order once effective status is deterministically resolved', 'FMCSA OOS source'],
    ['Critical', 'Operating authority currently suspended or revoked', 'MOTUS RevokeSuspend + carrier status'],
    ['Critical', 'Required insurance no longer on file', 'MOTUS insurance + history'],
    ['High', 'Recent fatal or injury crash', 'FMCSA crash records'],
    ['High', 'Material OOS-rate deterioration', 'Inspection + violation trend'],
    ['Watch', 'Stale MCS-150 / reported mileage', 'Company Census history'],
    ['Watch', 'Abrupt fleet-size or observed-VIN change', 'Census + inspection-unit history'],
  ];
  return <main className="page-shell"><section className="page-heading"><div><div className="eyebrow">Event monitoring</div><h1>Alerts</h1><p>Material facts remain independent from future composite model scores.</p></div></section><section className="panel"><div className="panel-heading"><div><h2>Alert rule registry</h2><p>Rules are defined; portfolio-level evaluation starts after durable daily carrier snapshots are present.</p></div><span className="status-pill status-build">No fabricated events</span></div><div className="rule-table">{rules.map(([level, rule, source]) => <div className="rule-row" key={rule}><span className={`rule-level level-${level.toLowerCase()}`}>{level}</span><strong>{rule}</strong><span>{source}</span></div>)}</div></section></main>;
}

function Methodology() {
  return (
    <main className="page-shell">
      <section className="page-heading"><div><div className="eyebrow">Versioned calculation contract</div><h1>Methodology</h1><p>Official outputs, reproduced calculations and proprietary underwriting models are separate products of separate rulesets.</p></div></section>
      <section className="methodology-grid">
        <article className="panel method-card active-method"><div className="method-top"><span className="status-pill status-live">Active</span><EvidenceBadge kind="TRANSPORT_CALCULATED" /></div><div className="eyebrow">FMCSA SMS</div><h2>v3.21 · June 2026</h2><p>Current live methodology. The reproduction harness will be validated against FMCSA monthly output files before any internal risk model is trusted.</p><ul><li>24-month safety-event windows</li><li>Current severity + OOS weighting</li><li>Recency weighting</li><li>Relevant-inspection denominators</li><li>Exposure/utilization logic where applicable</li></ul></article>
        <article className="panel method-card preview-method"><div className="method-top"><span className="status-pill status-preview">Preview</span><EvidenceBadge kind="TRANSPORT_CALCULATED" /></div><div className="eyebrow">FMCSA approved future methodology</div><h2>Next SMS · isolated engine</h2><p>Kept independently because FMCSA has approved material changes but has not activated them as the current SMS methodology.</p><ul><li>Violation grouping changes</li><li>1 / 2 violation weights</li><li>Compliance-category reorganization</li><li>Proportionate percentile mechanics</li><li>Changed intervention thresholds</li></ul></article>
      </section>
      <section className="panel formula-contract"><div className="panel-heading"><div><div className="eyebrow">Calculation provenance</div><h2>Every result must be replayable.</h2></div></div><div className="contract-grid"><div><strong>Source as-of</strong><span>Which FMCSA snapshot supplied the inputs</span></div><div><strong>Ruleset</strong><span>Exact methodology version</span></div><div><strong>Inputs</strong><span>Numerators, denominators, event weights and exposure</span></div><div><strong>Confidence</strong><span>Observation sufficiency and known source limitations</span></div></div></section>
    </main>
  );
}

function SourceHealth({ sourceHealth }: { sourceHealth: SourceHealthPayload }) {
  const rows = useMemo(() => {
    const healthById = new Map(sourceHealth.sources.map((source) => [source.id, source]));
    return sourceCatalog.map((source) => ({ ...source, health: healthById.get(source.id) }));
  }, [sourceHealth]);

  return <main className="page-shell wide-shell"><section className="page-heading"><div><div className="eyebrow">Data lineage</div><h1>Source Health</h1><p>Availability, schema and freshness checks for the FMCSA/DOT datasets that underpin Transport3r.</p></div><div className="as-of-block"><span>Last automated probe</span><strong>{sourceHealth.generated_at ? new Date(sourceHealth.generated_at).toLocaleString() : 'Not run yet'}</strong></div></section><section className="panel source-table-panel"><div className="source-table"><div className="source-row source-header"><span>Status</span><span>Dataset</span><span>Family</span><span>Cadence</span><span>Role</span><span>Schema</span></div>{rows.map((source) => { const status = source.health?.status ?? 'pending'; return <div className="source-row" key={source.id}><span><span className={`health-dot health-${status}`} /> {status}</span><span><strong>{source.name}</strong><code>{source.id}</code></span><span>{source.family}</span><span>{source.cadence}</span><span>{source.role}</span><span>{source.health?.schema_fields ?? '—'} fields</span></div>; })}</div></section></main>;
}

function App() {
  const route = window.location.hash.replace('#/', '') as Page;
  const [page, setPage] = useState<Page>(nav.some((item) => item.id === route) ? route : 'overview');
  const [sourceHealth, setSourceHealth] = useState<SourceHealthPayload>({ generated_at: null, sources: [] });

  useEffect(() => {
    const onHash = () => { const next = window.location.hash.replace('#/', '') as Page; setPage(nav.some((item) => item.id === next) ? next : 'overview'); };
    window.addEventListener('hashchange', onHash); return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/source-health.json`, { cache: 'no-store' })
      .then((response) => response.ok ? response.json() : Promise.reject(new Error(`HTTP ${response.status}`)))
      .then((payload: SourceHealthPayload) => setSourceHealth(payload))
      .catch(() => setSourceHealth({ generated_at: null, sources: [] }));
  }, []);

  return <div className="app-shell"><header className="top-nav"><Wordmark /><nav aria-label="Primary navigation">{nav.map((item) => <a key={item.id} href={`#/${item.id}`} className={page === item.id ? 'active' : ''}>{item.label}</a>)}</nav><div className="nav-meta"><span className="nav-dot" /><span>FMCSA workspace</span></div></header>{page === 'overview' && <Overview sourceHealth={sourceHealth} />}{page === 'prospect' && <CarrierSearch sourceHealth={sourceHealth} />}{page === 'portfolio' && <Portfolio />}{page === 'alerts' && <Alerts />}{page === 'methodology' && <Methodology />}{page === 'sources' && <SourceHealth sourceHealth={sourceHealth} />}<footer className="app-footer"><span>Transport3r</span><span>FMCSA-first transportation insurance intelligence</span><span>Evidence before score</span></footer></div>;
}

export default App;
