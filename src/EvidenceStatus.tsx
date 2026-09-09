import type { CarrierEvidence } from './carrierEvidence';
import { evidenceIssues } from './carrierEvidence';
import { censusReviewNotes } from './datahub';
import { CoveragePanel } from './CoveragePanel';

export function ExposureContext({ date, status }: { date?: string; status?: string }) {
  const notes = censusReviewNotes(date, status);
  if (!notes.length) return null;
  return <div className="c360-review warning"><strong>Reported exposure needs verification</strong>{notes.map(note => <p key={note}>{note}</p>)}</div>;
}

export function EvidenceStatus({ evidence }: { evidence: CarrierEvidence }) {
  const issues = evidenceIssues(evidence);
  return <><CoveragePanel evidence={evidence}/>{issues.length > 0 && <div className="c360-source-errors"><strong>{issues.length} source request{issues.length === 1 ? '' : 's'} incomplete or unavailable</strong><p>The rest of this tab remains usable. Unavailable data is not zero; partial results are not complete totals.</p><div>{issues.map(({key, message}) => <span key={key}><code>{key}</code>{message}</span>)}</div></div>}</>;
}

export function FleetEvidenceFailure({ error }: { error: string }) {
  return <div className="c360-review warning"><strong>Inspection-unit evidence unavailable.</strong><p>{error} Reported fleet exposure remains separate; unavailable observations do not mean zero vehicles.</p></div>;
}
