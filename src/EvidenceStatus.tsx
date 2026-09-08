import type { CarrierEvidence } from './carrierEvidence';
import { evidenceIssues } from './carrierEvidence';

export function EvidenceStatus({ evidence }: { evidence: CarrierEvidence }) {
  const issues = evidenceIssues(evidence);
  if (!issues.length) return null;
  return <div className="c360-source-errors"><strong>{issues.length} source request{issues.length === 1 ? '' : 's'} incomplete or unavailable</strong><p>The rest of this tab remains usable. Unavailable data is not zero; partial results are not complete totals.</p><div>{issues.map(({key, message}) => <span key={key}><code>{key}</code>{message}</span>)}</div></div>;
}

export function FleetEvidenceFailure({ error }: { error: string }) {
  return <div className="c360-review warning"><strong>Inspection-unit evidence unavailable.</strong><p>{error} Reported fleet exposure remains separate; unavailable observations do not mean zero vehicles.</p></div>;
}
