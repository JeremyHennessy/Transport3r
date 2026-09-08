import { useEffect, useMemo, useState } from 'react';
import {
  CarrierEvidence,
  UNIT_FIELD_ALIASES,
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
import { replayCarrierInspectionMeasures, replaySummary } from './smsReplay';

type CarrierSection = 'summary' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence';

type ParsedRoute =
  | { kind: 'section'; dotNumber: string; section: CarrierSection }
  | { kind: 'inspection'; dotNumber: string; inspectionId: string };

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
const SECTIONS: Array<{ id: CarrierSection; label: string }> = [
  { id: 'summary', label: 'Summary' },
  { id: 'safety', label: 'Safety' },
  { id: 'fleet', label: 'Fleet' },
  { id: 'authority', label: 'Authority' },
  { id: 'insurance', label: 'Insurance' },
  { id: 'sms', label: 'SMS' },
  { id: 'evidence', label: 'Evidence' },
];

function parseRoute(): ParsedRoute | null {
  const parts = window.location.hash.replace(/^#\//, '').split('/').filter(Boolean);
  if (parts[0] !== 'carrier' || !/^\d+$/.test(parts[1] ?? '')) return null;
  const dotNumber = parts[1];
  if (parts[2] === 'inspection' && parts[3]) return { kind: 'inspection', dotNumber, inspectionId: parts[3] };
  const section = (parts[2] ?? 'summary') as CarrierSection;
  return { kind: 'section', dotNumber, section: SECTIONS.some((candidate) => candidate.id === section) ? section : 'summary' };
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
    raw: row,
  };
}

async function loadCarrier(dotNumber: string): Promise<Carrier> {
  const params = new URLSearchParams({ '$where': `dot_number=${Number(dotNumber)}`, '$limit': '1' });
  const response = await fetch(`${DATAHUB}/az4n-8mr2.json?${params.toString()}`);
  if (!response.ok) throw new Error(`Company Census returned HTTP ${response.status}`);
  const rows = await response.json() as DataRow[];
  if (!rows.length) throw new Error(`USDOT ${dotNumber} was not found in the current Company Census file`);
  return carrierFromRow(rows[0]);
}

function formatNumber(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''));
  return Number.isFinite(numeric) ? numeric.toLocaleString() : String(value);
}

function formatMeasure(value?: number | null): string {
  return value === null || value === undefined ? '—' : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

function formatDate(raw?: string): string {
  if (!raw) return '—';
  const direct = new Date(raw);
  if (!Number.isNaN(direct.valueOf())) return direct.toLocaleDateString();
  const compact = raw.match(/^(\d{2})(\d{2})(\d{4})$/);
  if (compact) return `${compact[1]}/${compact[2]}/${compact[3]}`;
  return raw;
}

function inspectionId(row: DataRow): string | undefined {
  return readValue(row, ['INSPECTION_ID', 'UNIQUE_ID', 'INSP_ID']);
}

function Wordmark() {
  return (
    <a className="wordmark route-wordmark" href="#/overview" aria-label="Transport3r home">
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

function Badge({ children, tone = 'official' }: { children: React.ReactNode; tone?: 'official' | 'calculated' | 'warning' | 'good' }) {
  return <span className={`route-badge route-badge-${tone}`}>{children}</span>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="route-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function CarrierHeader({ carrier, route }: { carrier: Carrier; route: ParsedRoute }) {
  return (
    <>
      <section className="route-carrier-header">
        <div className="route-carrier-title">
          <div className="eyebrow">Carrier 360 · Shareable FMCSA evidence</div>
          <h1>{carrier.legalName}</h1>
          {carrier.dbaName && <p>DBA {carrier.dbaName}</p>}
          <div className="route-carrier-meta">
            <span>USDOT {carrier.dotNumber}</span>
            <span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || 'Location unavailable'}</span>
            <span>{carrier.operation || 'Operation unavailable'}</span>
          </div>
        </div>
        <div className="route-header-actions">
          <Badge>Official FMCSA evidence</Badge>
          <a className="secondary-button" href="#/prospect">Carrier search</a>
        </div>
      </section>
      <nav className="route-section-nav" aria-label="Carrier sections">
        {SECTIONS.map((section) => (
          <a
            key={section.id}
            href={`#/carrier/${carrier.dotNumber}/${section.id}`}
            className={route.kind === 'section' && route.section === section.id ? 'active' : ''}
          >
            {section.label}
          </a>
        ))}
      </nav>
    </>
  );
}

function Summary({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const crashes = severeCrashCounts(evidence);
  const statuses = authorityStatuses(evidence);
  const vins = observedVins(evidence);
  const concerns: string[] = [];
  if (crashes.fatal) concerns.push(`${crashes.fatal} loaded crash record${crashes.fatal === 1 ? '' : 's'} with reported fatalities.`);
  if (crashes.injury) concerns.push(`${crashes.injury} loaded crash record${crashes.injury === 1 ? '' : 's'} with reported injuries.`);
  const oos = oosViolationCount(evidence);
  if (oos) concerns.push(`${oos} loaded inspection violation${oos === 1 ? '' : 's'} flagged out of service.`);
  const revokeRows = rowCount(evidence.slices.motusRevokeSuspend);
  if (revokeRows) concerns.push(`${revokeRows} historical MOTUS revocation/suspension row${revokeRows === 1 ? '' : 's'}; review current effect separately.`);

  return (
    <section className="route-section-card">
      <div className="route-section-heading">
        <div><div className="eyebrow">Decision summary</div><h2>Underwriting evidence at a glance</h2></div>
        <Badge>Official FMCSA</Badge>
      </div>
      <div className="route-metric-grid six">
        <Metric label="Power units" value={formatNumber(carrier.powerUnits)} />
        <Metric label="Drivers" value={formatNumber(carrier.drivers)} />
        <Metric label="Reported VMT" value={formatNumber(carrier.mileage)} detail={carrier.mileageYear ? `Mileage year ${carrier.mileageYear}` : undefined} />
        <Metric label="Inspections" value={formatNumber(rowCount(evidence.slices.inspections))} />
        <Metric label="Crashes" value={formatNumber(rowCount(evidence.slices.crash))} />
        <Metric label="Observed VINs" value={formatNumber(vins.length)} />
      </div>
      <div className="route-summary-grid">
        <article><span>Authority</span><strong>{statuses.length ? statuses.join(', ') : 'No current MOTUS status row returned'}</strong><p>{formatNumber(rowCount(evidence.slices.motusAuthHistory))} authority-history rows loaded.</p></article>
        <article><span>Insurance</span><strong>{formatNumber(activeInsuranceRows(evidence).length)} active/pending filing rows</strong><p>{formatNumber(rowCount(evidence.slices.motusInsuranceHistory))} insurance-history rows loaded.</p></article>
        <article><span>SMS</span><strong>{formatNumber(officialSmsRows(evidence).length)} official property output row</strong><p>Transport replay is shown separately on the SMS page.</p></article>
        <article><span>Transport risk index</span><strong>Not scored</strong><p>TRI remains blocked until percentile reconstruction is fully validated.</p></article>
      </div>
      <div className={`route-review-box ${concerns.length ? 'warning' : 'clear'}`}>
        <strong>{concerns.length ? 'Evidence requiring review' : 'No hard-review flags derived from the loaded checks'}</strong>
        {concerns.length ? <ul>{concerns.map((item) => <li key={item}>{item}</li>)}</ul> : <p>This is not a clearance decision; absence of a loaded event is not proof of absence.</p>}
      </div>
    </section>
  );
}

function Safety({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const inspections = evidence.slices.inspections?.rows.slice(0, 40) ?? [];
  const crashes = evidence.slices.crash?.rows.slice(0, 30) ?? [];
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">Daily safety evidence</div><h2>Inspections and crashes</h2></div><Badge>Official FMCSA</Badge></div>
      <div className="route-metric-grid four">
        <Metric label="Inspections" value={formatNumber(rowCount(evidence.slices.inspections))} />
        <Metric label="Violation rows" value={formatNumber(rowCount(evidence.slices.violations))} />
        <Metric label="OOS violation rows" value={formatNumber(oosViolationCount(evidence))} />
        <Metric label="Crash rows" value={formatNumber(rowCount(evidence.slices.crash))} />
      </div>
      <h3 className="route-subheading">Recent inspections</h3>
      <div className="route-table inspection-route-table">
        <div className="route-table-row header"><span>Date</span><span>State</span><span>Level</span><span>Vehicle viol.</span><span>Driver viol.</span><span /></div>
        {inspections.map((row, index) => {
          const id = inspectionId(row);
          return (
            <div className="route-table-row" key={id ?? index}>
              <span>{formatDate(readValue(row, ['INSP_DATE', 'INSPECTION_DATE', 'REPORT_DATE']))}</span>
              <span>{readValue(row, ['REPORT_STATE', 'STATE']) ?? '—'}</span>
              <span>{readValue(row, ['INSP_LEVEL_ID', 'INSPECTION_LEVEL', 'LEVEL']) ?? '—'}</span>
              <span>{formatNumber(readNumber(row, ['VEHICLE_VIOLATIONS', 'VEH_VIOLATIONS', 'VEH_VIOL_TOTAL']))}</span>
              <span>{formatNumber(readNumber(row, ['DRIVER_VIOLATIONS', 'DRV_VIOLATIONS', 'DRIVER_VIOL_TOTAL']))}</span>
              <span>{id ? <a className="route-drill-link" href={`#/carrier/${carrier.dotNumber}/inspection/${id}`}>Open →</a> : '—'}</span>
            </div>
          );
        })}
      </div>
      <h3 className="route-subheading">Recent crash involvement</h3>
      <div className="route-table crash-route-table">
        <div className="route-table-row header"><span>Date</span><span>State</span><span>Fatalities</span><span>Injuries</span><span>Tow-away</span></div>
        {crashes.map((row, index) => (
          <div className="route-table-row" key={readValue(row, ['REPORT_NUMBER', 'CRASH_ID']) ?? index}>
            <span>{formatDate(readValue(row, ['CRASH_DATE', 'REPORT_DATE']))}</span>
            <span>{readValue(row, ['REPORT_STATE', 'STATE']) ?? '—'}</span>
            <span>{formatNumber(readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT']))}</span>
            <span>{formatNumber(readNumber(row, ['INJURIES', 'INJURY_CNT', 'INJURY_COUNT']))}</span>
            <span>{readValue(row, ['TOW_AWAY', 'TOWAWAY', 'TOW_AWAY_FLAG']) ?? '—'}</span>
          </div>
        ))}
      </div>
      <p className="route-disclaimer">Crash records represent reported crash involvement and do not by themselves establish fault.</p>
    </section>
  );
}

function Fleet({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const units = evidence.slices.units?.rows ?? [];
  const vins = observedVins(evidence);
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">Observed fleet</div><h2>Vehicles seen in FMCSA inspections</h2></div><Badge>Official FMCSA</Badge></div>
      <div className="route-metric-grid four">
        <Metric label="Reported power units" value={formatNumber(carrier.powerUnits)} />
        <Metric label="Unique observed VINs" value={formatNumber(vins.length)} />
        <Metric label="Inspection-unit rows" value={formatNumber(rowCount(evidence.slices.units))} />
        <Metric label="Fleet coverage" value={carrier.powerUnits && Number(carrier.powerUnits) > 0 ? `${Math.round((vins.length / Number(carrier.powerUnits)) * 100)}% observed/report` : '—'} detail="Context only; not ownership coverage" />
      </div>
      {!units.length ? (
        <div className="route-empty"><strong>No inspection-unit rows returned for the loaded inspection set.</strong></div>
      ) : (
        <div className="route-table fleet-route-table">
          <div className="route-table-row header"><span>VIN</span><span>Make</span><span>Type</span><span>Plate</span><span>State</span><span>Unit</span></div>
          {units.slice(0, 250).map((row, index) => (
            <div className="route-table-row" key={`${readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? 'unit'}-${index}`}>
              <span className="mono-cell">{readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? '—'}</span>
              <span>{readValue(row, [...UNIT_FIELD_ALIASES.make]) ?? '—'}</span>
              <span>{readValue(row, [...UNIT_FIELD_ALIASES.type]) ?? '—'}</span>
              <span>{readValue(row, [...UNIT_FIELD_ALIASES.plate]) ?? '—'}</span>
              <span>{readValue(row, [...UNIT_FIELD_ALIASES.plateState]) ?? '—'}</span>
              <span>{readValue(row, [...UNIT_FIELD_ALIASES.unitNumber]) ?? '—'}</span>
            </div>
          ))}
        </div>
      )}
      <p className="route-disclaimer">Observed VINs establish an FMCSA inspection association only. They do not prove current ownership or inclusion on an insured vehicle schedule.</p>
    </section>
  );
}

function Authority({ evidence }: { evidence: CarrierEvidence }) {
  const current = evidence.slices.motusCarrier?.rows ?? [];
  const history = evidence.slices.motusAuthHistory?.rows ?? [];
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">Modern MOTUS</div><h2>Operating authority</h2></div><Badge>Official FMCSA</Badge></div>
      <div className="route-metric-grid four">
        <Metric label="Current/baseline rows" value={formatNumber(rowCount(evidence.slices.motusCarrier))} />
        <Metric label="Authority history" value={formatNumber(rowCount(evidence.slices.motusAuthHistory))} />
        <Metric label="Revoke/suspend history" value={formatNumber(rowCount(evidence.slices.motusRevokeSuspend))} />
        <Metric label="New Entrant OOS history" value={formatNumber(rowCount(evidence.slices.newEntrantOos))} />
      </div>
      <h3 className="route-subheading">Current / baseline authority</h3>
      <div className="route-table authority-route-table">
        <div className="route-table-row header"><span>Docket</span><span>Type</span><span>Status</span><span>Legal name</span></div>
        {current.slice(0, 100).map((row, index) => <div className="route-table-row" key={index}><span>{readValue(row, ['DOCKET_NUMBER', 'DOCKET_NO']) ?? '—'}</span><span>{readValue(row, ['OP_AUTH_TYPE', 'AUTH_TYPE']) ?? '—'}</span><span>{readValue(row, ['OP_AUTH_STATUS', 'AUTH_STATUS']) ?? '—'}</span><span>{readValue(row, ['LEGAL_NAME', 'CARRIER_NAME']) ?? '—'}</span></div>)}
      </div>
      <h3 className="route-subheading">Authority history</h3>
      <RawRecordList rows={history.slice(0, 30)} />
    </section>
  );
}

function Insurance({ evidence }: { evidence: CarrierEvidence }) {
  const current = evidence.slices.motusInsurance?.rows ?? [];
  const history = evidence.slices.motusInsuranceHistory?.rows ?? [];
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">Modern MOTUS</div><h2>Insurance filings</h2></div><Badge>Official FMCSA</Badge></div>
      <h3 className="route-subheading">Active / pending filings</h3>
      <div className="route-table insurance-route-table">
        <div className="route-table-row header"><span>Policy</span><span>Type</span><span>Insurer</span><span>Limit</span><span>Transaction / effective</span></div>
        {current.slice(0, 100).map((row, index) => <div className="route-table-row" key={index}><span>{readValue(row, ['POLICY_NO', 'POLICY_NUMBER']) ?? '—'}</span><span>{readValue(row, ['INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']) ?? '—'}</span><span>{readValue(row, ['INSURANCE_COMPANY_NAME', 'INS_COMPANY_NAME', 'COMPANY_NAME']) ?? '—'}</span><span>{formatNumber(readNumber(row, ['MAX_COV_AMOUNT', 'MAX_COVERAGE_AMOUNT', 'UNDERL_LIM_AMOUNT']))}</span><span>{formatDate(readValue(row, ['TRANS_DATE', 'EFFECTIVE_DATE']))}</span></div>)}
      </div>
      <h3 className="route-subheading">Insurance history</h3>
      <div className="route-table insurance-route-table">
        <div className="route-table-row header"><span>Policy</span><span>Type</span><span>Insurer</span><span>Limit</span><span>Cancellation / transaction</span></div>
        {history.slice(0, 150).map((row, index) => <div className="route-table-row" key={index}><span>{readValue(row, ['POLICY_NO', 'POLICY_NUMBER']) ?? '—'}</span><span>{readValue(row, ['INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']) ?? '—'}</span><span>{readValue(row, ['INSURANCE_COMPANY_NAME', 'INS_COMPANY_NAME', 'COMPANY_NAME']) ?? '—'}</span><span>{formatNumber(readNumber(row, ['MAX_COV_AMOUNT', 'MAX_COVERAGE_AMOUNT', 'UNDERL_LIM_AMOUNT']))}</span><span>{formatDate(readValue(row, ['CANCEL_EFFECTIVE_DATE', 'CANCELLATION_DATE', 'TRANS_DATE']))}</span></div>)}
      </div>
    </section>
  );
}

function Sms({ evidence }: { evidence: CarrierEvidence }) {
  const officialRows = officialSmsRows(evidence);
  const outputSourceId = evidence.slices.smsABProperty?.rows.length ? '4y6x-dmck' : 'h9zy-gjn8';
  const officialEntries = officialRows[0] ? Object.entries(officialRows[0])
    .filter(([, raw]) => raw !== null && raw !== undefined && String(raw).trim() !== '')
    .filter(([key]) => /(basic|measure|alert|threshold|inspection|crash|power|driver|rating)/i.test(key))
    .slice(0, 32) : [];
  const replays = replayCarrierInspectionMeasures(evidence);
  const summary = replaySummary(replays);
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">SMS v3.21 · Current methodology</div><h2>Official output and Transport replay</h2></div><div className="route-badge-stack"><Badge>Official FMCSA</Badge><Badge tone="calculated">Transport calculated</Badge></div></div>
      <div className="route-metric-grid four">
        <Metric label="SMS inspection inputs" value={formatNumber(rowCount(evidence.slices.smsInspection))} />
        <Metric label="SMS violation inputs" value={formatNumber(rowCount(evidence.slices.smsViolation))} />
        <Metric label="Official output rows" value={formatNumber(officialRows.length)} />
        <Metric label="Replay validation" value={`${summary.matches}/${summary.validationCandidates}`} detail={`${summary.mismatches} mismatches for this carrier`} />
      </div>
      <h3 className="route-subheading">Transport v3.21 measure replay</h3>
      <div className="sms-replay-grid">
        {replays.map((replay) => (
          <article key={replay.basic} className={`sms-replay-card status-${replay.status.toLowerCase()}`}>
            <div className="sms-replay-head"><strong>{replay.label}</strong><Badge tone="calculated">{replay.status}</Badge></div>
            <div className="sms-replay-values"><div><span>Official</span><strong>{formatMeasure(replay.officialMeasure)}</strong></div><div><span>Replay</span><strong>{formatMeasure(replay.calculatedMeasure)}</strong></div><div><span>Delta</span><strong>{formatMeasure(replay.delta)}</strong></div></div>
            <small>Numerator {formatNumber(replay.numerator)} · denominator {formatNumber(replay.denominator)} · {replay.relevantInspections} relevant inspections · group {replay.safetyEventGroup ?? '—'}</small>
          </article>
        ))}
      </div>
      <div className="route-review-box clear"><strong>Percentiles remain intentionally unavailable.</strong><p>The measure replay is validated; property percentile reconstruction is still under a separate full-population validation gate and is not being inferred from rounded bulk measures.</p></div>
      <h3 className="route-subheading">Official public output fields</h3>
      {officialEntries.length ? <div className="official-output-grid">{officialEntries.map(([key, raw]) => <div key={key}><span>{schemaLabel(evidence.registry, outputSourceId, key)}</span><strong>{String(raw)}</strong></div>)}</div> : <div className="route-empty"><strong>No public property-carrier SMS output row returned.</strong><p>This is not treated as a zero-risk value.</p></div>}
    </section>
  );
}

function Evidence({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">Source lineage</div><h2>Carrier evidence coverage</h2></div></div>
      <div className="route-source-grid">
        {Object.entries(evidence.slices).map(([key, slice]) => <article key={key}><span>{key}</span><strong>{formatNumber(slice?.total ?? slice?.rows.length ?? 0)}</strong><small>{slice?.sourceId} · {slice?.truncated ? 'partial rows loaded' : 'query complete'}</small></article>)}
      </div>
      {Object.keys(evidence.errors).length > 0 && <div className="route-review-box warning"><strong>Source joins with errors</strong><ul>{Object.entries(evidence.errors).map(([key, message]) => <li key={key}><code>{key}</code>: {message}</li>)}</ul></div>}
      <details className="raw-evidence"><summary>Raw current Company Census row</summary><pre>{JSON.stringify(carrier.raw, null, 2)}</pre></details>
      <p className="route-disclaimer">Evidence loaded {new Date(evidence.loadedAt).toLocaleString()}.</p>
    </section>
  );
}

function RawRecordList({ rows }: { rows: DataRow[] }) {
  if (!rows.length) return <div className="route-empty"><strong>No rows returned.</strong></div>;
  return <div className="raw-record-list">{rows.map((row, index) => <details key={index}><summary>Record {index + 1}</summary><pre>{JSON.stringify(row, null, 2)}</pre></details>)}</div>;
}

function InspectionDetail({ carrier, evidence, inspectionIdValue }: { carrier: Carrier; evidence: CarrierEvidence; inspectionIdValue: string }) {
  const inspection = (evidence.slices.inspections?.rows ?? []).find((row) => inspectionId(row) === inspectionIdValue);
  const belongs = (row: DataRow) => readValue(row, ['INSPECTION_ID', 'UNIQUE_ID', 'INSP_ID']) === inspectionIdValue;
  const units = (evidence.slices.units?.rows ?? []).filter(belongs);
  const violations = (evidence.slices.violations?.rows ?? []).filter(belongs);
  const citations = (evidence.slices.citations?.rows ?? []).filter(belongs);
  return (
    <section className="route-section-card">
      <div className="route-section-heading"><div><div className="eyebrow">Inspection drillthrough</div><h2>Inspection {inspectionIdValue}</h2></div><a className="secondary-button" href={`#/carrier/${carrier.dotNumber}/safety`}>Back to Safety</a></div>
      {!inspection ? <div className="route-review-box warning"><strong>This inspection is not in the currently loaded carrier inspection window.</strong><p>The current Carrier 360 loader caps inspection rows. Direct deep-history inspection lookup will be added separately rather than pretending the record was found.</p></div> : <>
        <div className="route-metric-grid four"><Metric label="Date" value={formatDate(readValue(inspection, ['INSP_DATE', 'INSPECTION_DATE', 'REPORT_DATE']))} /><Metric label="State" value={readValue(inspection, ['REPORT_STATE', 'STATE']) ?? '—'} /><Metric label="Level" value={readValue(inspection, ['INSP_LEVEL_ID', 'INSPECTION_LEVEL', 'LEVEL']) ?? '—'} /><Metric label="Units / violations" value={`${units.length} / ${violations.length}`} detail={`${citations.length} citation rows`} /></div>
        <h3 className="route-subheading">Inspection record</h3><RawRecordList rows={[inspection]} />
        <h3 className="route-subheading">Vehicle units</h3><div className="route-table fleet-route-table"><div className="route-table-row header"><span>VIN</span><span>Make</span><span>Type</span><span>Plate</span><span>State</span><span>Unit</span></div>{units.map((row, index) => <div className="route-table-row" key={index}><span className="mono-cell">{readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.make]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.type]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.plate]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.plateState]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.unitNumber]) ?? '—'}</span></div>)}</div>
        <h3 className="route-subheading">Violations</h3><RawRecordList rows={violations} />
        <h3 className="route-subheading">Citations</h3><RawRecordList rows={citations} />
      </>}
    </section>
  );
}

export default function CarrierRouteApp() {
  const [route, setRoute] = useState<ParsedRoute | null>(() => parseRoute());
  const [carrier, setCarrier] = useState<Carrier | null>(null);
  const [evidence, setEvidence] = useState<CarrierEvidence | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(parseRoute());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (!route) return;
    let current = true;
    setCarrier(null);
    setEvidence(null);
    setError(null);
    Promise.all([loadCarrier(route.dotNumber), loadCarrierEvidence(route.dotNumber)])
      .then(([loadedCarrier, loadedEvidence]) => {
        if (!current) return;
        setCarrier(loadedCarrier);
        setEvidence(loadedEvidence);
        document.title = `${loadedCarrier.legalName} · USDOT ${loadedCarrier.dotNumber} · Transport3r`;
      })
      .catch((cause) => { if (current) setError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { current = false; };
  }, [route?.dotNumber]);

  const sectionContent = useMemo(() => {
    if (!route || !carrier || !evidence) return null;
    if (route.kind === 'inspection') return <InspectionDetail carrier={carrier} evidence={evidence} inspectionIdValue={route.inspectionId} />;
    if (route.section === 'summary') return <Summary carrier={carrier} evidence={evidence} />;
    if (route.section === 'safety') return <Safety carrier={carrier} evidence={evidence} />;
    if (route.section === 'fleet') return <Fleet carrier={carrier} evidence={evidence} />;
    if (route.section === 'authority') return <Authority evidence={evidence} />;
    if (route.section === 'insurance') return <Insurance evidence={evidence} />;
    if (route.section === 'sms') return <Sms evidence={evidence} />;
    return <Evidence carrier={carrier} evidence={evidence} />;
  }, [route, carrier, evidence]);

  if (!route) return <div className="route-fatal">Invalid carrier route. <a href="#/prospect">Return to Carrier Search</a>.</div>;

  return (
    <div className="app-shell carrier-route-shell">
      <header className="top-nav route-top-nav"><Wordmark /><nav><a href="#/overview">Overview</a><a href="#/prospect">Carrier Search</a><a href="#/methodology">Methodology</a><a href="#/sources">Source Health</a></nav><div className="nav-meta"><span className="nav-dot" /><span>USDOT {route.dotNumber}</span></div></header>
      <main className="route-page-shell">
        {error && <div className="inline-error"><strong>Carrier page could not load.</strong> {error}</div>}
        {!error && (!carrier || !evidence) && <div className="route-loading"><span className="loading-spinner" /><div><strong>Loading carrier evidence</strong><span>Resolving current Company Census, daily safety, MOTUS and monthly SMS sources.</span></div></div>}
        {carrier && evidence && <><CarrierHeader carrier={carrier} route={route} />{sectionContent}</>}
      </main>
      <footer className="app-footer"><span>Transport3r</span><span>Shareable FMCSA carrier intelligence</span><span>Evidence before score</span></footer>
    </div>
  );
}
