import { useMemo, useState } from 'react';
import type { CarrierEvidence } from './carrierEvidence';
import { COVERAGE_LABELS, coverageReport, type CoverageStatus } from './evidenceCoverage';
import { censusStatusLabel, formatDateValue, type DataRow } from './datahub';

export function CoveragePanel({ evidence, census }: { evidence: CarrierEvidence; census?: DataRow }) {
  const [filter, setFilter] = useState('all');
  const report = useMemo(() => coverageReport(evidence, census), [evidence, census]);
  const rows = report.sources.filter(row => filter === 'all' || row.status === filter);
  function download() {
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url;
    link.download = `transport3r-${evidence.dotNumber}-${evidence.mode}-coverage.json`;
    link.hidden = true; document.body.append(link); link.click(); link.remove();
    // Leave time for the browser to start writing the download before revoking its URL.
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  }
  return <details className="t3-coverage" open={evidence.mode === 'evidence'}>
    <summary>Source coverage and dates · {report.sources.length} requests · {report.sources.filter(row => row.status !== 'complete').length} partial, empty or unavailable</summary>
    <p>Request totals describe the named scope, not lifetime activity or SAFER’s 24-month window. Loaded event ranges are not proof of complete history.</p>
    {report.exposure && <p>Exposure report: {formatDateValue(report.exposure.reportDate ?? undefined)} · {censusStatusLabel(report.exposure.registration ?? undefined)} registration. {report.exposure.reviewNotes.join(' ')}</p>}
    <div className="t3-coverage-controls"><label>Coverage filter <select value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All requests</option>{Object.entries(COVERAGE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><button type="button" onClick={download}>Export coverage JSON</button><span role="status">{rows.length} of {report.sources.length} sources</span></div>
    <div className="t3-coverage-scroll"><table><caption>USDOT {evidence.dotNumber} · {evidence.mode} evidence coverage</caption><thead><tr><th>Source / scope</th><th>Coverage / counts</th><th>Loaded dates</th><th>Acquisition / metadata</th></tr></thead><tbody>{rows.map(row => <tr key={row.key}>
      <td><a href={`https://data.transportation.gov/d/${row.sourceId}`} target="_blank" rel="noreferrer">{row.key} ↗</a><small>{row.sourceName} · {row.sourceId}</small><small>{row.scope === 'loaded_inspections' ? 'Loaded inspection IDs' : row.scope === 'dockets' ? 'Linked dockets' : row.scope === 'carrier' ? 'This USDOT' : 'Scope unavailable'}</small></td>
      <td><strong>{COVERAGE_LABELS[row.status as CoverageStatus]}</strong><small>{row.loaded?.toLocaleString() ?? '—'} rows loaded · {row.requestTotal?.toLocaleString() ?? '—'} request total</small><small>{row.reason}</small></td>
      <td>{row.range?.start ? `${row.range.start} → ${row.range.end}` : 'Range unavailable'}<small>{row.dateFields.join(', ') || 'No event date mapping established'}</small>{row.range && <small>{row.range.valid} valid · {row.range.missing} missing · {row.range.invalid} invalid · {row.range.conflicting} conflicting dates</small>}</td>
      <td>Acquired: {row.acquiredAt ?? 'Unavailable / no request issued'}<small>Saved rows update: {row.metadataUpdatedAt ?? 'Unavailable'}</small><small>Catalog captured: {row.metadataCapturedAt ?? 'Unavailable'}</small></td>
    </tr>)}</tbody></table></div>
    {!rows.length && <p>No sources match this coverage filter.</p>}
    <p>Saved metadata dates are not a live freshness check. Export includes every source in this tab, including filtered-out sources; event records are not included. Risk score unavailable.</p>
  </details>;
}
