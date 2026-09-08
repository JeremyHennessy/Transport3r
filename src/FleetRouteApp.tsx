import { useEffect, useMemo, useState } from 'react';
import {
  CarrierEvidence,
  UNIT_FIELD_ALIASES,
  loadCarrierEvidence,
  observedVins,
  rowCountLabel,
} from './carrierEvidence';
import { DataRow, readNumber, readValue } from './datahub';

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
  statusCode?: string;
  raw: DataRow;
};

type EquipmentRow = {
  label: string;
  owned: number;
  termLeased: number;
  tripLeased: number;
};

const DATAHUB = 'https://data.transportation.gov/resource';
const OPERATION_LABELS: Record<string, string> = {
  A: 'Interstate',
  B: 'Intrastate hazmat',
  C: 'Intrastate non-hazmat',
};

const EQUIPMENT_FIELDS = [
  ['Trucks', 'OWNTRUCK', 'TRMTRUCK', 'TRPTRUCK'],
  ['Tractors', 'OWNTRACT', 'TRMTRACT', 'TRPTRACT'],
  ['Trailers', 'OWNTRAIL', 'TRMTRAIL', 'TRPTRAIL'],
  ['Motor coaches', 'OWNCOACH', 'TRMCOACH', 'TRPCOACH'],
  ['School buses 1–8', 'OWNSCHOOL_1_8', 'TRMSCHOOL_1_8', 'TRPSCHOOL_1_8'],
  ['School buses 9–15', 'OWNSCHOOL_9_15', 'TRMSCHOOL_9_15', 'TRPSCHOOL_9_15'],
  ['School buses 16+', 'OWNSCHOOL_16', 'TRMSCHOOL_16', 'TRPSCHOOL_16'],
  ['Buses 16+', 'OWNBUS_16', 'TRMBUS_16', 'TRPBUS_16'],
  ['Vans 1–8', 'OWNVAN_1_8', 'TRMVAN_1_8', 'TRPVAN_1_8'],
  ['Vans 9–15', 'OWNVAN_9_15', 'TRMVAN_9_15', 'TRPVAN_9_15'],
  ['Limousines 1–8', 'OWNLIMO_1_8', 'TRMLIMO_1_8', 'TRPLIMO_1_8'],
  ['Limousines 9–15', 'OWNLIMO_9_15', 'TRMLIMO_9_15', 'TRPLIMO_9_15'],
  ['Limousines 16+', 'OWNLIMO_16', 'TRMLIMO_16', 'TRPLIMO_16'],
] as const;

function parseDotNumber(): string | null {
  const parts = window.location.hash.replace(/^#\//, '').split('/').filter(Boolean);
  if (parts[0] !== 'carrier' || !/^\d+$/.test(parts[1] ?? '') || parts[2] !== 'fleet') return null;
  return parts[1];
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
    if (!rows.length) throw new Error(`USDOT ${dotNumber} was not found in Company Census`);
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
  const parsed = typeof value === 'number' ? value : Number(String(value).replaceAll(',', ''));
  return Number.isFinite(parsed) ? parsed.toLocaleString() : String(value);
}

function formatOperation(raw?: string): string {
  if (!raw) return 'Operation unavailable';
  return OPERATION_LABELS[raw.toUpperCase()] ?? raw;
}

function censusNumber(row: DataRow, field: string): number {
  return readNumber(row, [field]) ?? 0;
}

function Brand() {
  return <a className="t3-brand" href="#/overview" aria-label="Transport3r overview"><span className="t3-mark" aria-hidden="true"><svg viewBox="0 0 42 42"><path d="M8 10.5h26v6H23.8V34h-6V16.5H8z"/><path d="M27 21h7v13h-7z" className="accent"/></svg></span><span className="t3-brand-text">Transport<span>3r</span></span></a>;
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <div className="c360-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>;
}

export default function FleetRouteApp() {
  const [dotNumber, setDotNumber] = useState<string | null>(() => parseDotNumber());
  const [carrier, setCarrier] = useState<Carrier | null>(null);
  const [evidence, setEvidence] = useState<CarrierEvidence | null>(null);
  const [carrierError, setCarrierError] = useState<string | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);

  useEffect(() => {
    const onHash = () => setDotNumber(parseDotNumber());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    if (!dotNumber) return;
    let current = true;
    setCarrier(null);
    setEvidence(null);
    setCarrierError(null);
    setEvidenceError(null);
    loadCarrier(dotNumber)
      .then((loaded) => { if (current) { setCarrier(loaded); document.title = `${loaded.legalName} · Fleet · Transport3r`; } })
      .catch((cause) => { if (current) setCarrierError(cause instanceof Error ? cause.message : String(cause)); });
    loadCarrierEvidence(dotNumber, 'fleet')
      .then((loaded) => { if (current) setEvidence(loaded); })
      .catch((cause) => { if (current) setEvidenceError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { current = false; };
  }, [dotNumber]);

  const equipment = useMemo<EquipmentRow[]>(() => {
    if (!carrier) return [];
    return EQUIPMENT_FIELDS.map(([label, own, term, trip]) => ({
      label,
      owned: censusNumber(carrier.raw, own),
      termLeased: censusNumber(carrier.raw, term),
      tripLeased: censusNumber(carrier.raw, trip),
    })).filter((row) => row.owned + row.termLeased + row.tripLeased > 0);
  }, [carrier]);

  if (!dotNumber) return <div className="t3-fatal"><strong>Invalid Fleet route.</strong><a href="#/carriers">Return to Carriers</a></div>;

  const units = evidence?.slices.units?.rows ?? [];
  const vins = observedVins(evidence);
  const truckUnits = carrier ? readValue(carrier.raw, ['TRUCK_UNITS']) : undefined;
  const busUnits = carrier ? readValue(carrier.raw, ['BUS_UNITS']) : undefined;
  const fleetSizeCode = carrier ? readValue(carrier.raw, ['FLEETSIZE']) : undefined;
  const reported = Number(carrier?.powerUnits ?? 0);
  const observationRatio = Number.isFinite(reported) && reported > 0 ? Math.round((vins.length / reported) * 100) : null;

  const sections = [
    ['summary', 'Summary', 'Decision view'],
    ['safety', 'Safety', 'Inspections & crashes'],
    ['fleet', 'Fleet', 'Reported + observed'],
    ['authority', 'Authority', 'MOTUS & OOS'],
    ['insurance', 'Insurance', 'Filings & history'],
    ['sms', 'SMS', 'Official + replay'],
    ['evidence', 'Evidence', 'All source lineage'],
  ] as const;

  return <div className="t3-app c360-app">
    <header className="t3-topbar"><Brand/><nav className="t3-primary-nav" aria-label="Primary navigation"><a href="#/overview">Overview</a><a href="#/carriers" className="active">Carriers</a><a href="#/portfolio">Portfolio</a><a href="#/alerts">Alerts</a><a href="#/methodology">Methodology</a><a href="#/sources">Data Sources</a></nav><span className="t3-health neutral"><i/>USDOT {dotNumber}</span></header>
    <main className="c360-main">
      {carrierError && <div className="t3-error"><strong>Carrier identity could not load.</strong><span>{carrierError}</span></div>}
      {!carrier && !carrierError && <div className="c360-loading"><span className="t3-spinner"/><div><strong>Loading reported fleet exposure</strong><span>Reading the current FMCSA Company Census record first.</span></div></div>}
      {carrier && <>
        <section className="c360-identity"><div className="c360-title-block"><div className="t3-eyebrow">Carrier 360 · Fleet · USDOT {carrier.dotNumber}</div><h1>{carrier.legalName}</h1>{carrier.dbaName && <p>DBA {carrier.dbaName}</p>}<div className="c360-meta"><span>{[carrier.city, carrier.state].filter(Boolean).join(', ') || 'Location unavailable'}</span><span>{formatOperation(carrier.operation)}</span><span>HM {carrier.hazmat || '—'}</span><span>Status {carrier.statusCode || '—'}</span></div></div><div className="c360-title-actions"><span className="c360-badge official">Official FMCSA</span><a className="t3-button text" href="#/carriers">Back to carriers</a></div></section>
        <section className="c360-exposure-strip"><Metric label="Reported power units" value={formatNumber(carrier.powerUnits)} /><Metric label="Drivers" value={formatNumber(carrier.drivers)} /><Metric label="Reported VMT" value={formatNumber(carrier.mileage)} detail={carrier.mileageYear ? `MCS-150 year ${carrier.mileageYear}` : 'Mileage year unavailable'} /><Metric label="Fleet-size band" value={fleetSizeCode || '—'} detail="FMCSA Company Census band" /></section>
        <nav className="c360-tabs" aria-label="Carrier evidence sections">{sections.map(([id, label, description]) => <a key={id} href={`#/carrier/${carrier.dotNumber}/${id}`} className={id === 'fleet' ? 'active' : ''}><strong>{label}</strong><span>{description}</span></a>)}</nav>
        <section className="c360-card">
          <div className="c360-section-head"><div><div className="t3-eyebrow">Company Census fleet exposure</div><h2>Reported fleet composition</h2></div><span className="c360-badge official">Official FMCSA</span></div>
          <div className="c360-metric-grid six"><Metric label="Power units" value={formatNumber(carrier.powerUnits)} detail="Reported total"/><Metric label="Truck units" value={formatNumber(truckUnits)} detail="Reported trucks"/><Metric label="Bus units" value={formatNumber(busUnits)} detail="Reported buses"/><Metric label="Drivers" value={formatNumber(carrier.drivers)} detail="Reported drivers"/><Metric label="Observed VINs" value={formatNumber(vins.length)} detail="Inspection evidence"/><Metric label="Observed / reported" value={observationRatio === null ? '—' : `${observationRatio}%`} detail="Not ownership coverage"/></div>
          <h3 className="c360-subhead">Ownership / lease mix reported on MCS-150</h3>
          {equipment.length ? <div className="c360-decision-grid">{equipment.map((row) => <article key={row.label}><span>{row.label}</span><strong>{formatNumber(row.owned + row.termLeased + row.tripLeased)} reported</strong><p>Owned {formatNumber(row.owned)} · Term leased {formatNumber(row.termLeased)} · Trip leased {formatNumber(row.tripLeased)}</p></article>)}</div> : <div className="c360-empty"><strong>No detailed owned/leased equipment counts were populated in the current Census row.</strong><p>The reported power-unit total above remains the authoritative public fleet exposure field.</p></div>}
          <h3 className="c360-subhead">Vehicles observed in FMCSA inspections</h3>
          {evidenceError && <div className="t3-error"><strong>Inspection-unit evidence could not load.</strong><span>{evidenceError}</span></div>}
          {!evidence && !evidenceError && <div className="c360-loading"><span className="t3-spinner"/><div><strong>Loading observed vehicles</strong><span>Joining published inspections to Inspection Units.</span></div></div>}
          {evidence && <>
            <div className="c360-metric-grid four"><Metric label="Inspection rows loaded" value={rowCountLabel(evidence.slices.inspections)} /><Metric label="Inspection-unit rows" value={rowCountLabel(evidence.slices.units)} /><Metric label="Unique observed VINs" value={formatNumber(vins.length)} /><Metric label="Coverage meaning" value="Observed only" detail="Not a complete insured schedule" /></div>
            {!units.length ? <div className="c360-review warning"><strong>No individual vehicle records were observed in the available FMCSA inspection-unit history for this carrier.</strong><p>The carrier still reports {formatNumber(carrier.powerUnits)} power units. FMCSA does not publish a complete VIN-level fleet schedule for every carrier; this section can only enumerate vehicles that appear in public inspection-unit records.</p></div> : <div className="c360-table fleet"><div className="c360-table-row header"><span>VIN</span><span>Make</span><span>Type</span><span>Plate</span><span>State</span><span>Unit</span></div>{units.slice(0, 500).map((row, index) => <div className="c360-table-row" key={`${readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? 'unit'}-${index}`}><span className="mono">{readValue(row, [...UNIT_FIELD_ALIASES.vin]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.make]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.type]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.plate]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.plateState]) ?? '—'}</span><span>{readValue(row, [...UNIT_FIELD_ALIASES.unitNumber]) ?? '—'}</span></div>)}</div>}
            {Object.keys(evidence.errors).length > 0 && <div className="c360-source-errors"><strong>{Object.keys(evidence.errors).length} fleet source request(s) unavailable</strong><p>Unavailable source evidence is not treated as zero.</p></div>}
          </>}
          <p className="c360-disclaimer">Company Census equipment counts are carrier-reported FMCSA values. Inspection-unit VINs establish a public roadside inspection association only and do not prove current ownership or inclusion on an insured vehicle schedule.</p>
        </section>
      </>}
    </main>
    <footer className="t3-footer"><span>Transport3r</span><span>FMCSA reported fleet + inspection-observed vehicles</span><span>Evidence before score</span></footer>
  </div>;
}
