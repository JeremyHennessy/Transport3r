import {OfficialSmsPanel} from './OfficialSmsPanel';
import { InspectionDetail, ObservedVinDetail } from './InspectionDrilldowns';
import { loadInspectionEvidence } from './inspectionEvidence';
import { SafetyWindowPanel } from './SafetyWindowPanel';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import {
  CarrierEvidence,
  CarrierEvidenceMode,
  UNIT_FIELD_ALIASES,
  VIOLATION_FIELD_ALIASES,
  activeInsuranceRows,
  authorityStatusLabel,
  sourceEmptyMessage,
  loadCarrierEvidence,
  observedVins,
  officialSmsRows,
  officialSmsSourceId,
  oosViolationCount,
  aggregateRows,
  evidenceIssues,
  MOTUS_DELTA_KEYS,
  observedVinCountLabel,
  rowCount,
  rowCountLabel,
  loadedRowCountLabel,
  inspectionCountDetail,
  inspectionAvailability,
  severeCrashCounts,
} from './carrierEvidence';
import { DataRow, formatDateValue, censusStatusLabel, driverReportDetail, censusReviewNotes, mileageYearLabel, readNumber, readValue, schemaLabel } from './datahub';
import { EvidenceStatus, ExposureContext } from './EvidenceStatus';
import { orderSummary, filingChangeSummary, motusMaximumCoverageLabel, MOTUS_COVERAGE_UNIT_NOTE } from './evidenceLifecycle';
import { replayCarrierInspectionMeasures, replaySummary, smsReplayMessages } from './smsReplay';

type CarrierSection = 'summary' | 'safety' | 'fleet' | 'authority' | 'insurance' | 'sms' | 'evidence';

type ParsedRoute =
  | { kind: 'section'; dotNumber: string; section: CarrierSection }
  | { kind: 'inspection'; dotNumber: string; inspectionId: string }
  | { kind: 'vin'; dotNumber: string; vin: string; inspectionId?: string };

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
  mileage?: string;
  mileageYear?: string;
  hazmat?: string;
  statusCode?: string;
  raw: DataRow;
};

const DATAHUB = 'https://data.transportation.gov/resource';
const SECTIONS: Array<{ id: CarrierSection; label: string; description: string }> = [
  { id: 'summary', label: 'Summary', description: 'Decision view' },
  { id: 'safety', label: 'Safety', description: 'Inspections & crashes' },
  { id: 'fleet', label: 'Fleet', description: 'Observed vehicles' },
  { id: 'authority', label: 'Authority', description: 'MOTUS & OOS' },
  { id: 'insurance', label: 'Insurance', description: 'Filings & history' },
  { id: 'sms', label: 'SMS', description: 'Official + replay' },
  { id: 'evidence', label: 'Evidence', description: 'All source lineage' },
];

const OPERATION_LABELS: Record<string, string> = {
  A: 'Interstate',
  B: 'Intrastate hazmat',
  C: 'Intrastate non-hazmat',
};

function parseRoute(): ParsedRoute | null {
  const parts = window.location.hash.split('?')[0].replace(/^#\//, '').split('/').filter(Boolean);
  if (parts[0] !== 'carrier' || !/^\d+$/.test(parts[1] ?? '')) return null;
  const dotNumber = parts[1];
  if (parts[2] === 'vin' && parts[3]) {
    try {
      const vin = decodeURIComponent(parts[3]);
      const seed = new URLSearchParams(window.location.hash.split('?')[1] ?? '').get('inspection');
      if (!vin.trim() || vin.length > 64 || (seed && !/^[1-9]\d*$/.test(seed))) return null;
      return { kind: 'vin', dotNumber, vin, inspectionId: seed ?? undefined };
    } catch { return null; }
  }
  if (parts[2] === 'inspection' && /^[1-9]\d*$/.test(parts[3] ?? '')) return { kind: 'inspection', dotNumber, inspectionId: parts[3] };
  const section = (parts[2] ?? 'summary') as CarrierSection;
  return { kind: 'section', dotNumber, section: SECTIONS.some((candidate) => candidate.id === section) ? section : 'summary' };
}

function routeMode(route: ParsedRoute): CarrierEvidenceMode {
  return route.kind === 'inspection' || (route.kind === 'vin' && route.inspectionId) ? 'inspection' : route.kind === 'vin' ? 'fleet' : route.section;
}

export function carrierFromRow(row: DataRow): Carrier {
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
    mileage: readValue(row, ['MCS150_MILEAGE', 'MILEAGE', 'VMT']),
    mileageYear: readValue(row, ['MCS150_MILEAGE_YEAR', 'MILEAGE_YEAR', 'VMT_YEAR']),
    hazmat: readValue(row, ['HM_IND', 'HAZMAT_IND', 'HAZMAT_FLAG']),
    statusCode: readValue(row, ['STATUS_CODE', 'STATUS']),
    raw: row,
  };
}

async function loadCarrier(dotNumber: string): Promise<Carrier> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 9000);
  try {
    const params = new URLSearchParams({ '$where': `dot_number=${Number(dotNumber)}`, '$limit': '1' });
    const response = await fetch(`${DATAHUB}/az4n-8mr2.json?${params.toString()}`, { signal: controller.signal });
    if (!response.ok) throw new Error(`Company Census returned HTTP ${response.status}`);
    const rows = await response.json() as DataRow[];
    if (!rows.length) throw new Error(`USDOT ${dotNumber} was not found in the current Company Census file`);
    return carrierFromRow(rows[0]);
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw new Error('Company Census request timed out');
    throw cause;
  } finally {
    window.clearTimeout(timeout);
  }
}

function formatNumber(value?: string | number | null): string {
  if (value === undefined || value === null || value === '') return '—';
  const numeric = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''));
  return Number.isFinite(numeric) ? numeric.toLocaleString() : String(value);
}

function formatMeasure(value?: number | null): string {
  return value === null || value === undefined ? '—' : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '');
}

const formatDate = formatDateValue;

function formatOperation(raw?: string): string {
  if (!raw) return 'Operation unavailable';
  return OPERATION_LABELS[raw.toUpperCase()] ?? raw;
}

function inspectionId(row: DataRow): string | undefined {
  return readValue(row, ['INSPECTION_ID', 'UNIQUE_ID', 'INSP_ID']);
}

function Brand() {
  return <a className="t3-brand" href="#/overview" aria-label="Transport3r overview"><span className="t3-mark" aria-hidden="true"><svg viewBox="0 0 42 42"><path d="M8 10.5h26v6H23.8V34h-6V16.5H8z"/><path d="M27 21h7v13h-7z" className="accent"/></svg></span><span className="t3-brand-text">Transport<span>3r</span></span></a>;
}

function Badge({ children, tone = 'official' }: { children: ReactNode; tone?: 'official' | 'calculated' | 'warning' | 'good' | 'neutral' }) {
  return <span className={`c360-badge ${tone}`}>{children}</span>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="c360-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

function SectionHeading({ eyebrow, title, badges }: { eyebrow: string; title: string; badges?: ReactNode }) {
  return <div className="c360-section-head"><div><div className="t3-eyebrow">{eyebrow}</div><h2>{title}</h2></div>{badges}</div>;
}

const SourceErrors = EvidenceStatus;

function RawRecords({ rows, empty = 'No rows returned.' }: { rows: DataRow[]; empty?: string }) {
  if (!rows.length) return <div className="c360-empty"><strong>{empty}</strong></div>;
  return <div className="c360-raw-list">{rows.map((row, index) => <details key={index}><summary>Record {index + 1}</summary><pre>{JSON.stringify(row, null, 2)}</pre></details>)}</div>;
}

export function CarrierHeader({ carrier, route }: { carrier: Carrier; route: ParsedRoute }) {
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'manual'>('idle');
  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopyState('copied');
    } catch {
      window.prompt('Copy this carrier URL:', window.location.href);
      setCopyState('manual');
    }
  }
  return <>
    <section className="c360-identity">
      <div className="c360-title-block"><div className="t3-eyebrow">Carrier 360 · USDOT {carrier.dotNumber}</div><h1>{carrier.legalName}</h1>{carrier.dbaName && <p>DBA {carrier.dbaName}</p>}<div className="c360-meta"><span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || 'Location unavailable'}</span><span>{formatOperation(carrier.operation)}</span><span>HM {carrier.hazmat || '—'}</span><span>Status {censusStatusLabel(carrier.statusCode)}</span></div></div>
      <div className="c360-title-actions"><Badge>Official FMCSA spine</Badge><button className="t3-button secondary" onClick={copyLink}>{copyState === 'copied' ? 'Link copied' : 'Copy carrier link'}</button><a className="t3-button text" href="#/carriers">Back to carriers</a></div>
    </section>
    <ExposureContext date={carrier.mcs150Date} status={carrier.statusCode}/>
    <section className="c360-exposure-strip"><Metric label="Reported power units" value={formatNumber(carrier.powerUnits)} /><Metric label="Drivers" value={formatNumber(carrier.drivers)} detail={driverReportDetail(carrier.mcs150Date, carrier.statusCode)} /><Metric label="Reported VMT" value={formatNumber(carrier.mileage)} detail={`MCS-150 mileage · ${mileageYearLabel(carrier.mileageYear)}`} /><Metric label="Operating class" value={formatOperation(carrier.operation)} /></section>
    <nav className="c360-tabs" aria-label="Carrier evidence sections">{SECTIONS.map((section) => <a key={section.id} href={`#/carrier/${carrier.dotNumber}/${section.id}`} className={route.kind === 'section' && route.section === section.id ? 'active' : ''}><strong>{section.label}</strong><span>{section.description}</span></a>)}</nav>
  </>;
}

export function Summary({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const crashes = severeCrashCounts(evidence);
  const oos = oosViolationCount(evidence);
  const activeInsurance = activeInsuranceRows(evidence).length;
  const newEntrant = rowCount(evidence.slices.newEntrantOos);
  const revokeHistory = rowCount(evidence.slices.motusRevokeSuspend);
  const changes = aggregateRows(evidence, MOTUS_DELTA_KEYS);
  const orders = orderSummary(evidence);
  const availability = inspectionAvailability(evidence);
  const concerns: string[] = censusReviewNotes(carrier.mcs150Date, carrier.statusCode);
  if (availability) concerns.push(availability);
  if (orders.review) concerns.push(orders.review);
  if (revokeHistory) concerns.push(`${revokeHistory} revoke/suspend history row${revokeHistory === 1 ? '' : 's'} returned; history is not the same as current status.`);
  if (crashes.fatal) concerns.push(`${crashes.fatal} loaded crash record${crashes.fatal === 1 ? '' : 's'} reports one or more fatalities.`);
  if (crashes.injury) concerns.push(`${crashes.injury} loaded crash record${crashes.injury === 1 ? '' : 's'} reports injuries.`);
  if (evidenceIssues(evidence).length || crashes.incomplete || oos === null) concerns.push('Summary evidence is incomplete or unavailable; no complete review conclusion can be drawn.');
  if (oos) concerns.push(`${oos} loaded violation row${oos === 1 ? '' : 's'} is flagged out of service.`);

  return <section className="c360-card">
    <SectionHeading eyebrow="Decision summary" title="Underwriting evidence at a glance" badges={<div className="c360-badge-stack"><Badge>Official FMCSA</Badge><Badge tone="neutral">Risk score unavailable</Badge>{changes.loaded > 0 && <Badge tone="warning">Recent MOTUS change</Badge>}</div>} />
    <div className="c360-metric-grid four"><Metric label="Inspection file records" value={rowCountLabel(evidence.slices.inspections)} detail={inspectionCountDetail(evidence.slices.inspections)}/><Metric label="Loaded crashes" value={rowCountLabel(evidence.slices.crash)} detail={`${formatNumber(crashes.fatal)}${crashes.incomplete && crashes.fatal !== null ? "+" : ""} fatality-involved · ${formatNumber(crashes.injury)}${crashes.incomplete && crashes.injury !== null ? "+" : ""} injury-involved`}/><Metric label="Active/pending filings" value={rowCountLabel(evidence.slices.motusInsurance)} detail="MOTUS insurance"/><Metric label="24h MOTUS changes" value={changes.label} detail="Loaded carrier/insurance/revoke deltas"/></div>
    <div className="c360-decision-grid">
      <article><span>Identity & exposure</span><strong>{formatNumber(carrier.powerUnits)} power units · {formatNumber(carrier.drivers)} drivers</strong><p>Reported VMT {formatNumber(carrier.mileage)}{` (${mileageYearLabel(carrier.mileageYear)})`}. Census values describe the carrier report, not an insured schedule.</p></article>
      <article><span>Safety</span><strong>{loadedRowCountLabel(evidence.slices.inspections)} inspections · {rowCountLabel(evidence.slices.crash)} crashes loaded</strong><p>{formatNumber(oos)} loaded OOS violation rows. Crash involvement does not establish fault.</p></article>
      <article><span>Authority / enforcement</span><strong>{authorityStatusLabel(evidence)}</strong><p>{rowCountLabel(evidence.slices.motusRevokeSuspend)} historical revoke/suspend rows · {rowCountLabel(evidence.slices.newEntrantOos)} New Entrant OOS rows.</p></article>
      <article><span>Coverage continuity</span><strong>{rowCountLabel(evidence.slices.motusInsurance)} active/pending filing rows</strong><p>{rowCountLabel(evidence.slices.motusInsuranceDelta)} insurance changes in the loaded 24-hour difference feed.</p></article>
    </div>
    <div className={`c360-review ${concerns.length ? 'warning' : 'clear'}`}><strong>{concerns.length ? 'Evidence requiring review' : 'No hard-review flags derived from the loaded summary checks'}</strong>{concerns.length ? <ul>{concerns.map((item) => <li key={item}>{item}</li>)}</ul> : <p>This is not a clearance decision. Missing or unavailable evidence is never treated as a clean value.</p>}</div>
    <OfficialSmsPanel evidence={evidence}/>
    <div className="c360-note" data-testid="risk-availability"><strong>Risk score unavailable</strong><p>No numeric Transport3r risk model has been released for any carrier. Missing inspections do not produce a zero or low-risk score. Official SMS evidence and replay results are available separately when the sources return applicable records.</p><a href={`#/carrier/${carrier.dotNumber}/sms`}>Review SMS evidence →</a></div>
    <div className="c360-next-tabs"><a href={`#/carrier/${carrier.dotNumber}/safety`}><strong>Safety</strong><span>Inspect events and violations →</span></a><a href={`#/carrier/${carrier.dotNumber}/authority`}><strong>Authority</strong><span>Verify legal operating state →</span></a><a href={`#/carrier/${carrier.dotNumber}/insurance`}><strong>Insurance</strong><span>Trace filing continuity →</span></a><a href={`#/carrier/${carrier.dotNumber}/sms`}><strong>SMS</strong><span>Compare official vs replay →</span></a></div>
    <SourceErrors evidence={evidence}/>
  </section>;
}

export function Safety({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const inspections = evidence.slices.inspections?.rows ?? [];
  const violations = evidence.slices.violations?.rows ?? [];
  const crashes = evidence.slices.crash?.rows ?? [];
  const oos = oosViolationCount(evidence);
  return <section className="c360-card">
    <SectionHeading eyebrow="Daily safety evidence" title="Inspections, violations and crashes" badges={<Badge>Official FMCSA</Badge>} />
    <div className="c360-metric-grid six"><Metric label="Inspections" value={rowCountLabel(evidence.slices.inspections)} detail={inspectionCountDetail(evidence.slices.inspections)}/><Metric label="Violation rows" value={rowCountLabel(evidence.slices.violations)} detail={`${loadedRowCountLabel(evidence.slices.inspections)} loaded inspections`}/><Metric label="OOS violation rows" value={`${formatNumber(oos)}${oos !== null && evidence.slices.violations?.truncated ? '+' : ''}`} detail="Loaded violation evidence"/><Metric label="Crash rows" value={rowCountLabel(evidence.slices.crash)}/><Metric label="Citation rows" value={rowCountLabel(evidence.slices.citations)} detail="Loaded inspection window"/><Metric label="Special study rows" value={rowCountLabel(evidence.slices.specialStudies)} detail="Loaded inspection window"/></div>
    {inspectionAvailability(evidence) && <div className="c360-review warning"><strong>Inspection evidence availability</strong><p>{inspectionAvailability(evidence)}</p><p>Match the exact USDOT, source window and report dates before comparing another carrier or SAFER.</p></div>}
    <p className="c360-disclaimer"><a href={`https://safer.fmcsa.dot.gov/query.asp?searchtype=ANY&query_type=queryCarrierSnapshot&query_param=USDOT&query_string=${carrier.dotNumber}`} target="_blank" rel="noreferrer">Check this USDOT in official SAFER ↗</a></p>
    <SafetyWindowPanel key={carrier.dotNumber} dot={carrier.dotNumber} registry={evidence.registry}/>
    <h3 className="c360-subhead">Recent inspections</h3><div className="c360-table inspection"><div className="c360-table-row header"><span>Date</span><span>State</span><span>Level</span><span>Vehicle viol.</span><span>Driver viol.</span><span></span></div>{inspections.slice(0, 30).map((row, index) => { const id = inspectionId(row); return <div className="c360-table-row" key={id ?? index}><span>{formatDate(readValue(row, ['INSP_DATE', 'INSPECTION_DATE', 'REPORT_DATE']))}</span><span>{readValue(row, ['REPORT_STATE', 'STATE']) ?? '—'}</span><span>{readValue(row, ['INSP_LEVEL_ID', 'INSPECTION_LEVEL', 'LEVEL']) ?? '—'}</span><span>{formatNumber(readNumber(row, ['VEHICLE_VIOL_TOTAL', 'VEHICLE_VIOLATIONS', 'VEH_VIOLATIONS', 'VEH_VIOL_TOTAL']))}</span><span>{formatNumber(readNumber(row, ['DRIVER_VIOLATIONS', 'DRV_VIOLATIONS', 'DRIVER_VIOL_TOTAL']))}</span><span>{id ? <a href={`#/carrier/${carrier.dotNumber}/inspection/${id}`}>Open →</a> : '—'}</span></div>; })}</div>
    {!inspections.length && <div className="c360-empty"><strong>{sourceEmptyMessage(evidence, 'inspections', 'No daily inspection records returned for this USDOT.')}</strong><p>Older inspections can fall outside the currently published source window.</p></div>}
    <h3 className="c360-subhead">Violation evidence</h3><div className="c360-table violations"><div className="c360-table-row header"><span>Code</span><span>Description / BASIC</span><span>OOS</span><span>Unit</span><span>Inspection</span></div>{violations.slice(0, 40).map((row, index) => <div className="c360-table-row" key={index}><span className="mono">{readValue(row, ['VIOLATION_CODE', 'VIOL_CODE', 'CODE']) ?? '—'}</span><span>{readValue(row, [...VIOLATION_FIELD_ALIASES.description]) ?? readValue(row, ['BASIC_DESC']) ?? '—'}</span><span>{readValue(row, [...VIOLATION_FIELD_ALIASES.oos]) ?? '—'}</span><span>{readValue(row, [...VIOLATION_FIELD_ALIASES.unit]) ?? '—'}</span><span>{readValue(row, ['INSPECTION_ID', 'INSP_ID']) ?? '—'}</span></div>)}</div>
    <h3 className="c360-subhead">Recent crash involvement</h3><div className="c360-table crash"><div className="c360-table-row header"><span>Date</span><span>State</span><span>Fatalities</span><span>Injuries</span><span>Tow-away</span></div>{crashes.slice(0, 30).map((row, index) => <div className="c360-table-row" key={readValue(row, ['REPORT_NUMBER', 'CRASH_ID']) ?? index}><span>{formatDate(readValue(row, ['CRASH_DATE', 'REPORT_DATE']))}</span><span>{readValue(row, ['REPORT_STATE', 'STATE']) ?? '—'}</span><span>{formatNumber(readNumber(row, ['FATALITIES', 'FATALITY_CNT', 'FATALITY_COUNT']))}</span><span>{formatNumber(readNumber(row, ['INJURIES', 'INJURY_CNT', 'INJURY_COUNT']))}</span><span>{readValue(row, ['TOW_AWAY', 'TOWAWAY', 'TOW_AWAY_FLAG']) ?? '—'}</span></div>)}</div>
    <p className="c360-disclaimer">Crash records represent reported commercial-motor-vehicle crash involvement and do not by themselves establish fault.</p><SourceErrors evidence={evidence}/>
  </section>;
}

function Fleet({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const units = evidence.slices.units?.rows ?? [];
  const vins = observedVins(evidence);
  const reported = Number(carrier.powerUnits);
  const ratio = Number.isFinite(reported) && reported > 0 ? Math.round((vins.length / reported) * 100) : null;
  return <section className="c360-card"><SectionHeading eyebrow="Roadside vehicle observations" title="Fleet evidence" badges={<Badge>Official FMCSA</Badge>} /><div className="c360-metric-grid four"><Metric label="Reported power units" value={formatNumber(carrier.powerUnits)} detail="Company Census report"/><Metric label="Unique observed VINs" value={observedVinCountLabel(evidence)} detail="Loaded inspection-unit evidence"/><Metric label="Inspection-unit rows" value={rowCountLabel(evidence.slices.units)} detail="Most recent inspection-ID window"/><Metric label="Observed / reported" value={ratio === null ? '—' : `${ratio}%`} detail="Context only — not ownership coverage"/></div>{!units.length ? <div className="c360-empty"><strong>No inspection-unit rows returned for the loaded inspection window.</strong><p>This is not evidence that the carrier has no vehicles.</p></div> : <div className="c360-table fleet"><div className="c360-table-row header"><span>VIN</span><span>Make</span><span>Type</span><span>Plate</span><span>State</span><span>Unit</span></div>{units.slice(0, 250).map((row, index) => <div className="c360-table-row" key={`${readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? 'unit'}-${index}`}><span className="mono">{readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.make]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.type]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.plate]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.plateState]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.unitNumber]) ?? '—'}</span></div>)}</div>}<p className="c360-disclaimer">Observed VINs establish an FMCSA inspection association only. They do not prove current ownership or inclusion on an insured vehicle schedule.</p><SourceErrors evidence={evidence}/></section>;
}

export function Authority({ evidence }: { evidence: CarrierEvidence }) {
  const current = evidence.slices.motusCarrier?.rows ?? [];
  const history = evidence.slices.motusAuthHistory?.rows ?? [];
  const revoke = evidence.slices.motusRevokeSuspend?.rows ?? [];
  const boc3 = evidence.slices.motusBoc3?.rows ?? [];
  const recent = aggregateRows(evidence, ['motusCarrierDelta', 'motusAuthDelta', 'motusBoc3Delta', 'motusRevokeSuspendDelta']);
  return <section className="c360-card"><SectionHeading eyebrow="Modern MOTUS + enforcement" title="Operating authority" badges={<Badge>Official FMCSA</Badge>} /><div className="c360-metric-grid five"><Metric label="Current carrier rows" value={rowCountLabel(evidence.slices.motusCarrier)}/><Metric label="Authority history" value={rowCountLabel(evidence.slices.motusAuthHistory)}/><Metric label="Revoke / suspend" value={rowCountLabel(evidence.slices.motusRevokeSuspend)}/><Metric label="BOC-3 rows" value={rowCountLabel(evidence.slices.motusBoc3)}/><Metric label="24h authority changes" value={recent.label}/></div><h3 className="c360-subhead">Current / baseline authority</h3><div className="c360-table authority"><div className="c360-table-row header"><span>Docket</span><span>Type</span><span>Status</span><span>Legal name</span></div>{current.slice(0, 100).map((row, index) => <div className="c360-table-row" key={index}><span>{readValue(row, ['DOCKET_NUMBER', 'DOCKET_NO']) ?? '—'}</span><span>{readValue(row, ['OP_AUTH_TYPE', 'AUTH_TYPE']) ?? '—'}</span><span>{readValue(row, ['OP_AUTH_STATUS', 'AUTH_STATUS']) ?? '—'}</span><span>{readValue(row, ['LEGAL_NAME', 'CARRIER_NAME']) ?? '—'}</span></div>)}</div><div className="c360-split"><div><h3 className="c360-subhead">Authority history</h3><RawRecords rows={history.slice(0, 25)} empty={sourceEmptyMessage(evidence, 'motusAuthHistory')}/></div><div><h3 className="c360-subhead">Revoke / suspend history</h3><RawRecords rows={revoke.slice(0, 25)} empty={sourceEmptyMessage(evidence, 'motusRevokeSuspend')}/></div></div><h3 className="c360-subhead">BOC-3 administrative evidence</h3><RawRecords rows={boc3.slice(0, 20)} empty={sourceEmptyMessage(evidence, 'motusBoc3', 'No BOC-3 rows returned for this USDOT.')}/><h3 className="c360-subhead">Recent authority changes</h3><div className="c360-change-grid"><article><span>Carrier delta</span><strong>{rowCountLabel(evidence.slices.motusCarrierDelta)}</strong><p>Changes in the carrier/authority repository from the latest daily difference feed.</p></article><article><span>Authority history delta</span><strong>{rowCountLabel(evidence.slices.motusAuthDelta)}</strong><p>New lifecycle-history rows in the daily difference feed.</p></article><article><span>BOC-3 delta</span><strong>{rowCountLabel(evidence.slices.motusBoc3Delta)}</strong><p>Process-agent changes from the latest daily difference feed.</p></article><article><span>Revoke/suspend delta</span><strong>{rowCountLabel(evidence.slices.motusRevokeSuspendDelta)}</strong><p>Changed historical rows; verify current authority separately.</p></article><article><span>New Entrant OOS</span><strong>{rowCountLabel(evidence.slices.newEntrantOos)}</strong><p>{orderSummary(evidence).text}</p></article></div><SourceErrors evidence={evidence}/></section>;
}

export function Insurance({ evidence }: { evidence: CarrierEvidence }) {
  const current = evidence.slices.motusInsurance?.rows ?? [];
  const history = evidence.slices.motusInsuranceHistory?.rows ?? [];
  return <section className="c360-card"><SectionHeading eyebrow="MOTUS insurance filings" title="Coverage continuity" badges={<Badge>Official FMCSA</Badge>} /><div className="c360-metric-grid four"><Metric label="Active / pending" value={rowCountLabel(evidence.slices.motusInsurance)}/><Metric label="Filing history" value={rowCountLabel(evidence.slices.motusInsuranceHistory)}/><Metric label="24h active changes" value={rowCountLabel(evidence.slices.motusInsuranceDelta)}/><Metric label="24h history changes" value={rowCountLabel(evidence.slices.motusInsuranceHistoryDelta)}/></div><h3 className="c360-subhead">Active / pending filings</h3><div className="c360-table insurance"><div className="c360-table-row header"><span>Policy</span><span>Type</span><span>Insurer</span><span>Limit</span><span>Transaction / effective</span></div>{current.slice(0, 100).map((row, index) => <div className="c360-table-row" key={index}><span>{readValue(row, ['POLICY_NO', 'POLICY_NUMBER']) ?? '—'}</span><span>{readValue(row, ['INS_TYPE_CODE', 'INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']) ?? '—'}</span><span>{readValue(row, ['INSURANCE_COMPANY_NAME', 'INS_COMPANY_NAME', 'COMPANY_NAME']) ?? '—'}</span><span>{motusMaximumCoverageLabel(row)}</span><span>{formatDate(readValue(row, ['TRANS_DATE', 'EFFECTIVE_DATE']))}</span></div>)}</div><h3 className="c360-subhead">Insurance history</h3><div className="c360-table insurance"><div className="c360-table-row header"><span>Policy</span><span>Type</span><span>Insurer</span><span>Limit</span><span>Cancellation / transaction</span></div>{history.slice(0, 150).map((row, index) => <div className="c360-table-row" key={index}><span>{readValue(row, ['POLICY_NO', 'POLICY_NUMBER']) ?? '—'}</span><span>{readValue(row, ['INS_TYPE_CODE', 'INS_TYPE', 'INSURANCE_TYPE', 'INSURANCE_TYPE_CODE']) ?? '—'}</span><span>{readValue(row, ['INSURANCE_COMPANY_NAME', 'INS_COMPANY_NAME', 'COMPANY_NAME']) ?? '—'}</span><span>{motusMaximumCoverageLabel(row)}</span><span>{formatDate(readValue(row, ['CANCL_EFFECTIVE_DATE', 'CANCEL_EFFECTIVE_DATE', 'CANCELLATION_DATE', 'TRANS_DATE']))}</span></div>)}</div><div className="c360-note"><strong>Why the daily differences matter</strong><p>{filingChangeSummary(evidence)} {MOTUS_COVERAGE_UNIT_NOTE}</p></div><SourceErrors evidence={evidence}/></section>;
}

export function Sms({ evidence }: { evidence: CarrierEvidence }) {
  const officialRows = officialSmsRows(evidence);
  const sourceId = officialSmsSourceId(evidence);
  const replays = replayCarrierInspectionMeasures(evidence);
  const replayStats = replaySummary(replays);
  const replayMessages = smsReplayMessages(replays);
  const outputUnavailable = replays.some(replay => replay.officialOutputIssues.length > 0);
  const officialEntries = officialRows[0] && sourceId ? Object.entries(officialRows[0]).filter(([, value]) => value !== null && value !== undefined && String(value).trim() !== '').filter(([key]) => /(basic|measure|alert|threshold|inspection|crash|power|driver|rating|percent|_pct)/i.test(key)).slice(0, 40) : [];
  return <section className="c360-card"><SectionHeading eyebrow="SMS v3.21 · monthly calculation state" title="Official output and Transport replay" badges={<div className="c360-badge-stack"><Badge>Official FMCSA</Badge><Badge tone="calculated">Transport calculated</Badge></div>} /><div className="c360-metric-grid four"><Metric label="SMS inspection inputs" value={rowCountLabel(evidence.slices.smsInspection)}/><Metric label="SMS violation inputs" value={rowCountLabel(evidence.slices.smsViolation)}/><Metric label="Official output rows" value={aggregateRows(evidence, ['smsABProperty', 'smsCProperty', 'smsABPass', 'smsCPass']).label} detail={sourceId ?? 'No output source returned'}/><Metric label="Replay validation" value={`${replayStats.matches}/${replayStats.validationCandidates}`} detail={`${replayStats.mismatches} mismatches in this carrier view`}/></div><OfficialSmsPanel evidence={evidence}/><h3 className="c360-subhead">Inspection-based measure replay</h3><div className="c360-replay-grid">{replays.map((replay) => <article key={replay.basic} className={`status-${replay.status.toLowerCase()}`}><div className="c360-replay-head"><strong>{replay.label}</strong><Badge tone={replay.status === 'MATCH' || replay.status === 'CLOSE' ? 'good' : replay.status === 'MISMATCH' ? 'warning' : 'neutral'}>{replay.status}</Badge></div><div className="c360-replay-values"><div><span>Official</span><strong>{formatMeasure(replay.officialMeasure)}</strong></div><div><span>Replay</span><strong>{formatMeasure(replay.calculatedMeasure)}</strong></div><div><span>Delta</span><strong>{formatMeasure(replay.delta)}</strong></div></div><small>Numerator {formatNumber(replay.numerator)} · denominator {formatNumber(replay.denominator)} · {replay.relevantInspections} relevant inspections · group {replay.safetyEventGroup ?? '—'}</small></article>)}</div><div className="c360-review clear"><strong>Published SMS values and Transport3r calculations</strong><p>Published passenger percentiles are displayed above when reported by FMCSA. Unpublished percentiles are not reconstructed. Measure replay is a separate validation layer; proprietary TRI remains unreleased.</p></div>{replayMessages.length > 0 && <div className="c360-source-errors"><strong>SMS replay could not be fully validated</strong><div>{replayMessages.map(message => <span key={message}>{message}</span>)}</div></div>}<h3 className="c360-subhead">Official public output fields</h3>{officialEntries.length && sourceId ? <div className="c360-official-grid">{officialEntries.map(([key, value]) => <div key={key}><span>{schemaLabel(evidence.registry, sourceId, key)}</span><strong>{String(value)}</strong></div>)}</div> : <div className="c360-empty"><strong>{outputUnavailable ? 'Official SMS output is unavailable or inconsistent.' : 'No applicable public SMS output row returned.'}</strong><p>This is not treated as a zero-risk result.</p></div>}<SourceErrors evidence={evidence}/></section>;
}

export function Evidence({ carrier, evidence }: { carrier: Carrier; evidence: CarrierEvidence }) {
  const issues = evidenceIssues(evidence);
  return <section className="c360-card"><SectionHeading eyebrow="Full configured source sweep" title="Evidence lineage" badges={<Badge tone={issues.length ? 'warning' : 'good'}>{issues.length ? `${issues.length} source${issues.length === 1 ? '' : 's'} incomplete or unavailable` : 'Loaded without source errors'}</Badge>} /><SourceErrors evidence={evidence}/><details className="c360-raw-census"><summary>Raw Company Census record</summary><pre>{JSON.stringify(carrier.raw, null, 2)}</pre></details><p className="c360-disclaimer">The Evidence tab intentionally performs the broadest source sweep. Other Carrier 360 tabs load only the evidence needed for their underwriting question.</p></section>;
}

export default function CarrierRouteApp() {
  const [route, setRoute] = useState<ParsedRoute | null>(() => parseRoute());
  const [carrier, setCarrier] = useState<Carrier | null>(null);
  const [evidence, setEvidence] = useState<CarrierEvidence | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [carrierError, setCarrierError] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => setRoute(parseRoute());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (!route) return;
    let current = true;
    setCarrierError(null);
    loadCarrier(route.dotNumber).then((loaded) => { if (current) { setCarrier(loaded); document.title = `${loaded.legalName} · Transport3r`; } }).catch((cause) => { if (current) setCarrierError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { current = false; };
  }, [route?.dotNumber]);

  const mode = route ? routeMode(route) : 'summary';
  const selectedInspection = route && route.kind !== 'section' ? route.inspectionId : undefined;
  useEffect(() => {
    if (!route) return;
    let current = true;
    setEvidence(null);
    setEvidenceError(null);
    const task = selectedInspection ? loadInspectionEvidence(route.dotNumber, selectedInspection) : loadCarrierEvidence(route.dotNumber, mode);
    task.then((loaded) => { if (current) setEvidence(loaded); }).catch((cause) => { if (current) setEvidenceError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { current = false; };
  }, [route?.dotNumber, mode, selectedInspection, refresh]);

  const content = useMemo(() => {
    if (!route || !carrier || !evidence || evidence.dotNumber !== route.dotNumber || evidence.mode !== mode || evidence.inspectionId !== selectedInspection) return null;
    const displayEvidence = { ...evidence, census: carrier.raw };
    if (route.kind === 'inspection') return <InspectionDetail evidence={displayEvidence} onRetry={() => setRefresh(value => value+1)}/>;
    if (route.kind === 'vin') return <ObservedVinDetail evidence={displayEvidence} vin={route.vin}/>;
    if (route.section === 'summary') return <Summary carrier={carrier} evidence={displayEvidence}/>;
    if (route.section === 'safety') return <Safety carrier={carrier} evidence={displayEvidence}/>;
    if (route.section === 'fleet') return <Fleet carrier={carrier} evidence={displayEvidence}/>;
    if (route.section === 'authority') return <Authority evidence={displayEvidence}/>;
    if (route.section === 'insurance') return <Insurance evidence={displayEvidence}/>;
    if (route.section === 'sms') return <Sms evidence={displayEvidence}/>;
    return <Evidence carrier={carrier} evidence={displayEvidence}/>;
  }, [route, carrier, evidence, mode, selectedInspection]);

  if (!route) return <div className="t3-fatal"><strong>Invalid carrier route.</strong><a href="#/carriers">Return to Carriers</a></div>;

  return <div className="t3-app c360-app"><header className="t3-topbar"><Brand/><nav className="t3-primary-nav" aria-label="Primary navigation"><a href="#/overview">Overview</a><a href="#/carriers" className="active">Carriers</a><a href="#/portfolio">Portfolio</a><a href="#/alerts">Alerts</a><a href="#/methodology">Methodology</a><a href="#/sources">Data Sources</a></nav><span className="t3-health neutral"><i/>USDOT {route.dotNumber}</span></header><main className="c360-main">{carrierError && <div className="t3-error"><strong>Carrier identity could not load.</strong><span>{carrierError}</span><a href="#/carriers">Return to carrier table</a></div>}{carrier && <CarrierHeader carrier={carrier} route={route}/>} {evidenceError && <div className="t3-error"><strong>This evidence tab could not load.</strong><span>{evidenceError}</span></div>}{carrier && !evidence && !evidenceError && <div className="c360-loading"><span className="t3-spinner"/><div><strong>Loading {mode} evidence</strong><span>Only the FMCSA datasets required for this tab are being queried.</span></div></div>}{content}</main><footer className="t3-footer"><span>Transport3r</span><span>Shareable FMCSA carrier intelligence</span><span>Evidence before score</span></footer></div>;
}
