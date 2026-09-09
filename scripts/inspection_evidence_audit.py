"""Audit complete preserved inspection grains, SMS parent joins and explicit event windows.

This diagnostic does not calculate SMS measures, infer missing months, or align
daily and monthly source releases. Its counts are evidence counts, not risk scores.
"""
import argparse
import collections
import datetime as dt
import json
import pathlib

from cohort_snapshot import hash_file, load_verified
from snapshot_store import write_once
from validate_fmcsa_data_contract import parse_fmcsa_date
from verify_snapshot import timestamp

DAILY, SMS, VIOLATION = 'fx4q-ay7w', 'rbkj-cgst', '8mt8-2mdr'
VERSION = 'INSPECTION_EVIDENCE_AUDIT_1'


def index_parents(rows, field):
    parents = {}
    for row in rows:
        key = row.get(field)
        if not isinstance(key, str) or not key.strip() or key in parents:
            raise ValueError('Missing/duplicate parent identity: '+field)
        parents[key] = row
    return parents


def calendar_counts(rows, start, end):
    months = collections.Counter()
    unknown = future = before = selected = 0
    dates = []
    for row in rows:
        day = parse_fmcsa_date(row.get('insp_date'))
        if day is None:
            unknown += 1
        else:
            dates.append(day.isoformat())
            if day > end:
                future += 1
            elif day < start:
                before += 1
            else:
                selected += 1
                months[day.strftime('%Y-%m')] += 1
    # Zero observed rows in a month is not proof that the upstream month is complete.
    month = start.replace(day=1)
    monthly = []
    while month <= end:
        key = month.strftime('%Y-%m')
        monthly.append({'month': key, 'known_rows': months[key],
                        'window_rows': None if unknown else months[key],
                        'interpretation': 'OBSERVED_ROWS' if months[key] else 'NO_OBSERVED_ROWS'})
        month = dt.date(month.year+month.month//12, month.month%12+1, 1)
    return {'source_rows': len(rows), 'known_window_rows': selected, 'window_rows': None if unknown else selected,
            'unknown_dates': unknown, 'after_window': future, 'before_window': before,
            'earliest': min(dates, default=None), 'latest': max(dates, default=None), 'months': monthly}


def audit_rows(data, dots, start, end):
    if not {DAILY, SMS, VIOLATION}.issubset(data):
        raise ValueError('Complete daily inspections and both SMS inputs are required')
    if start > end or (end-start).days > 3660:
        raise ValueError('Explicit ordered event window must be at most ten years')
    daily = index_parents(data[DAILY], 'inspection_id')
    parents = index_parents(data[SMS], 'unique_id')
    members = set(dots)
    by_carrier = collections.defaultdict(lambda: collections.defaultdict(list))
    for sid in [DAILY, SMS, VIOLATION]:
        seen = set()
        for row in data[sid]:
            identity = row.get('source_row_id')
            if not identity or identity in seen or row.get('dot_number') not in members:
                raise ValueError('Duplicate/missing raw identity or out-of-cohort row')
            seen.add(identity)
            by_carrier[row['dot_number']][sid].append(row)
    issues, joins = [], collections.Counter()
    matched = collections.defaultdict(set)
    selected_matched = collections.defaultdict(set)
    for row in data[VIOLATION]:
        dot, key = row['dot_number'], row.get('unique_id')
        parent = parents.get(key)
        reason = None
        day = parse_fmcsa_date(row.get('insp_date'))
        if parent is None:
            reason = 'ORPHAN_VIOLATION'
        elif parent['dot_number'] != dot:
            reason = 'CROSS_CARRIER_PARENT'
        elif day is None or parse_fmcsa_date(parent.get('insp_date')) is None:
            reason = 'UNKNOWN_JOIN_DATE'
        elif day != parse_fmcsa_date(parent['insp_date']):
            reason = 'CONFLICTING_JOIN_DATE'
        if reason:
            issues.append({'dot_number': dot, 'unique_id': key, 'source_row_id': row['source_row_id'], 'reason': reason})
        else:
            joins[dot] += 1
            matched[dot].add(key)
            if start <= day <= end:
                selected_matched[dot].add(key)
    carriers = []
    for dot in dots:
        sources = {sid: calendar_counts(by_carrier[dot][sid], start, end) for sid in [DAILY, SMS, VIOLATION]}
        carrier_issues = [issue for issue in issues if issue['dot_number']==dot]
        # A bad parent date can hide an in-window inspection even without violations.
        dates_valid = not any(s['unknown_dates'] for s in sources.values())
        join_valid = not carrier_issues and dates_valid
        carriers.append({'dot_number': dot, 'sources': sources, 'matched_violation_rows': joins[dot],
                         'known_distinct_sms_parents_with_violations': len(matched[dot]),
                         'window_sms_parents_with_violations': len(selected_matched[dot]) if join_valid else None,
                         'join_issues': carrier_issues, 'date_window_status': 'VALID_DATES' if dates_valid else 'INCOMPLETE',
                         'cross_source_comparison': 'NOT_COMPARABLE_DIFFERENT_SOURCE_POPULATIONS_AND_RELEASES'})
    bad_dates = sum(s['unknown_dates'] for c in carriers for s in c['sources'].values())
    return {'version': VERSION, 'status': 'PASS' if not issues and not bad_dates else 'INCOMPLETE',
            'window_start': start.isoformat(), 'window_end': end.isoformat(), 'window_bounds': 'BOTH_INCLUSIVE',
            'daily_parent_rows': len(daily), 'sms_parent_rows': len(parents), 'sms_violation_rows': len(data[VIOLATION]),
            'matched_violation_rows': sum(joins.values()), 'join_issue_count': len(issues), 'unknown_dates': bad_dates,
            'carrier_count': len(dots), 'carriers': carriers, 'sms_release_alignment': 'NOT_ESTABLISHED',
            'risk_score': None, 'historical_training_eligibility': 'NOT_ESTABLISHED'}


def audit_cut(cut, start, end, as_of=None):
    cut = pathlib.Path(cut)
    manifest, cohort, data = load_verified(cut, as_of)
    as_of = as_of or manifest['completed_at']
    if end > timestamp(as_of).date():
        raise ValueError('Event window ends after requested knowledge time')
    result = audit_rows(data, cohort['dots'], start, end)
    result.update(cut_id=manifest['snapshot_id'], manifest_sha256=hash_file(cut/'manifest.json'),
                  available_at=manifest['completed_at'], as_of=as_of,
                  source_lineage=[{'source_id': s['id'], 'available_at': s['available_at'], 'lineage_sha256': s['lineage_sha256']}
                                  for s in manifest['datasets'] if s['id'] in [DAILY,SMS,VIOLATION]])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cut')
    parser.add_argument('--start', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--end', required=True, type=dt.date.fromisoformat)
    parser.add_argument('--as-of')
    parser.add_argument('--output', required=True, type=pathlib.Path)
    args = parser.parse_args()
    report = audit_cut(args.cut, args.start, args.end, args.as_of)
    write_once(args.output, report)
    print(json.dumps({k:v for k,v in report.items() if k!='carriers'}, indent=2))
    raise SystemExit(0 if report['status']=='PASS' else 2)
