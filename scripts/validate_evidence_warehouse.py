"""Live acquisition-to-warehouse gate, or validation of an already preserved extended cut."""
import argparse
import collections
import datetime as dt
import json
import pathlib

from cohort_snapshot import acquire, hash_file, load_verified, source_dot
from evidence_warehouse import carrier_evidence, connect, promote, verify
from inspection_evidence_audit import audit_cut
from inspection_children import PARENT, CHILDREN, parent_index
from docket_identity import BRIDGE, docket_index
from snapshot_store import now, write_once
from verify_snapshot import timestamp


def validate(output, cut=None, per_stratum=1, profile='underwriting_evidence_v2'):
    output = pathlib.Path(output)
    output.mkdir(parents=True,exist_ok=False)
    report = {'status':'RUNNING','started_at':now()}
    try:
        if cut is None:
            cut, manifest = acquire(output/'raw',per_stratum=per_stratum,profile=profile)
            if manifest['status'] != 'COMPLETE':
                raise ValueError('Live acquisition did not complete every required source')
        cut = pathlib.Path(cut)
        manifest, cohort, data = load_verified(cut)
        profile = manifest.get('source_profile')
        if profile not in ['underwriting_evidence_v1','underwriting_evidence_v2','underwriting_evidence_v3']:
            raise ValueError('This gate requires a complete extended profile')
        day = timestamp(manifest['completed_at']).date()
        inspection_audit = audit_cut(cut, day-dt.timedelta(days=729), day)
        write_once(output/'inspection-audit.json', inspection_audit)
        if inspection_audit['status'] != 'PASS':
            raise ValueError('Inspection parent/date integrity is incomplete; see inspection-audit.json')
        db = output/'evidence.sqlite'
        first = promote(cut,db)
        second = promote(cut,db)
        if first['promotion'] != 'INSERTED' or second['promotion'] != 'ALREADY_PRESENT':
            raise ValueError('Idempotent promotion did not preserve a single cut')
        verified = verify(db)
        parents = parent_index(data[PARENT]) if profile in ('underwriting_evidence_v2','underwriting_evidence_v3') else None
        dockets=docket_index(data[BRIDGE]) if profile=='underwriting_evidence_v3' else None
        expected = collections.Counter((sid,source_dot(sid,row,parents,dockets)) for sid,rows in data.items() for row in rows)
        connection = connect(db)
        try:
            actual = {(row[0],row[1]):row[2] for row in connection.execute('SELECT source_id,dot,count(*) FROM records GROUP BY source_id,dot')}
        finally:
            connection.close()
        checks = [{'source_id':sid,'dot':dot,'raw_count':expected[sid,dot],'warehouse_count':actual.get((sid,dot),0)}
                  for sid in data for dot in cohort['dots']]
        if any(check['raw_count'] != check['warehouse_count'] for check in checks):
            raise ValueError('Raw-to-warehouse source/carrier count mismatch')
        largest = max(cohort['dots'],key=lambda dot:expected['fx4q-ay7w',dot])
        exported = carrier_evidence(db,largest,manifest['completed_at'],profile=profile,include_records=True)
        inspection = next(source for source in exported['sources'] if source['source_id']=='fx4q-ay7w')
        if len(inspection['rows']) != expected['fx4q-ay7w',largest] or any(len(s['rows'])!=expected[s['source_id'],largest] for s in exported['sources']):
            raise ValueError('Export did not preserve complete inspection records')
        write_once(output/'carrier-export.json',exported)
        write_once(output/'carrier-count-checks.json',checks)
        report.update(status='PASS',cut_id=manifest['snapshot_id'],source_manifest_sha256=hash_file(cut/'manifest.json'),
                      cohort_sha256=manifest['cohort_sha256'],profile=profile,carriers=len(cohort['dots']),sources=len(data),
                      child_rows_verified=sum(len(data.get(sid,[])) for sid in CHILDREN),
                      total_rows=sum(len(rows) for rows in data.values()),source_rows={sid:len(rows) for sid,rows in data.items()},
                      inspection_audit={'status':inspection_audit['status'],
                                        'matched_violation_rows':inspection_audit['matched_violation_rows'],
                                        'sha256':hash_file(output/'inspection-audit.json')},
                      carrier_source_checks=len(checks),warehouse=verified,
                      exported_dot=largest,exported_inspections=inspection['carrier_rows'],
                      export_sha256=hash_file(output/'carrier-export.json'),
                      limitations='Complete for the preserved cohort queries only; not a nationwide warehouse, common monthly SMS snapshot, or historically validated training panel.')
    except Exception as error:
        report.update(status='FAIL',error=f'{type(error).__name__}: {error}')
    report['completed_at'] = now()
    write_once(output/'validation.json',report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    parser.add_argument('--cut')
    parser.add_argument('--profile',default='underwriting_evidence_v2',choices=['underwriting_evidence_v1','underwriting_evidence_v2','underwriting_evidence_v3'])
    parser.add_argument('--per-stratum',type=int,default=1)
    args = parser.parse_args()
    result = validate(args.output,args.cut,args.per_stratum,args.profile)
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)
