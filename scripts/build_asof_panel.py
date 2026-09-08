"""Build offline evidence features only from verified cuts already available as of the observation."""
import argparse
import calendar
import datetime as dt
import json
import pathlib
from collections import Counter

from cohort_snapshot import ROOT, SOURCES, hash_file, load_verified
from snapshot_store import now, write_once
from validate_fmcsa_data_contract import parse_decimal, parse_fmcsa_date
from verify_snapshot import timestamp

VERSION = 'CARRIER_ASOF_FEATURES_0_1'
SMS = {'AB_PASSENGER':'m3ry-qcip','C_PASSENGER':'h3zn-uid9','AB_PROPERTY':'4y6x-dmck','C_PROPERTY':'h9zy-gjn8'}
MEASURES = ['unsafe_driv','hos_driv','driv_fit','contr_subst','veh_maint']

def number(value, integer=False):
    n = parse_decimal(str(value) if value is not None else None)
    if n is None or n < 0 or (integer and n != int(n)):
        return None
    return int(n) if integer else float(n)

def event_window(rows, date_field, id_field, day, days):
    lower = day-dt.timedelta(days=days)
    valid, unknown, future, seen = [], 0, 0, set()
    for row in rows:
        key, date = row.get(id_field), parse_fmcsa_date(row.get(date_field))
        if not key or key in seen:
            raise ValueError(f'Missing/duplicate event identity: {id_field}')
        seen.add(key)
        if date is None:
            unknown += 1
        elif date > day:
            future += 1
        elif lower < date <= day:
            valid.append(row)
    return valid, unknown, future

def features(dot, data, as_of):
    day = timestamp(as_of).date()
    rows = {sid:[r for r in data[sid] if str(r.get('dot_number'))==dot] for sid in SOURCES}
    census = rows['az4n-8mr2']
    issues = []
    if len(census) != 1:
        issues.append('CENSUS_MISSING_OR_AMBIGUOUS')
    entity = census[0] if len(census)==1 else {}
    inspection_population_available = entity.get('status_code') == 'A'
    if not inspection_population_available:
        issues.append('INSPECTION_POPULATION_UNAVAILABLE')
    units = number(entity.get('power_units'),True)
    drivers = number(entity.get('total_drivers'),True)
    census_date = parse_fmcsa_date(entity.get('mcs150_date'))
    out = {'dot_number':dot, 'as_of':as_of, 'feature_schema_version':VERSION,
           'power_units_reported':units, 'drivers_reported':drivers, 'vmt_reported':number(entity.get('mcs150_mileage')),
           'vmt_year':number(entity.get('mcs150_mileage_year'),True),
           'mcs150_age_days':(day-census_date).days if census_date and census_date <= day else None,
           'carrier_operation':entity.get('carrier_operation'), 'hm_indicator':entity.get('hm_ind'),
           'passenger_indicator':entity.get('crgo_passengers'), 'census_status':entity.get('status_code'),
           'fleet_group':'UNKNOWN' if units is None else 'ZERO_REPORTED' if units==0 else '1_6' if units<=6 else '7_100' if units<=100 else '101_999' if units<1000 else '1000_PLUS'}
    if units is None or units == 0:
        issues.append('POWER_UNIT_DENOMINATOR_UNAVAILABLE')
    for days in [30,90,180,365]:
        inspections, bad, future = event_window(rows['fx4q-ay7w'],'insp_date','inspection_id',day,days)
        known_oos = [number(r.get('oos_total'),True) for r in inspections]
        incomplete = not inspection_population_available or bad>0 or any(x is None for x in known_oos)
        out[f'known_inspections_{days}d'] = len(inspections)
        out[f'inspections_{days}d'] = len(inspections) if not bad and inspection_population_available else None
        out[f'oos_inspections_{days}d'] = sum(x>0 for x in known_oos if x is not None) if not incomplete else None
        out[f'oos_rate_{days}d'] = out[f'oos_inspections_{days}d']/len(inspections) if inspections and not incomplete else None
        crashes, crash_bad, crash_future = event_window(rows['aayw-vxb3'],'report_date','crash_id',day,days)
        out[f'crash_vehicle_reports_{days}d'] = len(crashes) if not crash_bad else None
        # These are reports of involved commercial vehicles, not distinct crashes or fault determinations.
        out[f'crash_vehicle_reports_per_current_power_unit_{days}d'] = len(crashes)/units if units and not crash_bad else None
        severe, severe_unknown = 0, 0
        for crash in crashes:
            f, i = number(crash.get('fatalities'),True), number(crash.get('injuries'),True)
            tow = str(crash.get('tow_away','')).strip().upper()
            if (f is not None and f>0) or (i is not None and i>0) or tow in {'Y','YES','1'}:
                severe += 1
            elif f is None or i is None or tow not in {'N','NO','0'}:
                severe_unknown += 1
        out[f'severe_vehicle_reports_{days}d'] = severe if not severe_unknown and not crash_bad else None
        out[f'known_severe_vehicle_reports_{days}d'] = severe
        if days==365:
            if bad: issues.append('INSPECTION_DATES_UNKNOWN')
            if crash_bad: issues.append('CRASH_DATES_UNKNOWN')
            if incomplete: issues.append('OOS_FEATURE_INCOMPLETE')
            if severe_unknown: issues.append('CRASH_SEVERITY_INCOMPLETE')
            out.update({'unknown_inspection_dates':bad,'unknown_crash_dates':crash_bad,
                        'future_inspections_excluded':future,'future_crash_reports_excluded':crash_future})
    # Keep all official populations separate. No first-row preference, clipping, percentile conversion or averaging.
    official = {}
    for population, sid in SMS.items():
        candidates = rows[sid]
        status = 'AVAILABLE' if len(candidates)==1 else 'NO_ROW' if not candidates else 'AMBIGUOUS'
        item = {'source_id':sid,'status':status,'measures':{},'percentiles':{}}
        if len(candidates)==1:
            for basic in MEASURES:
                item['measures'][basic] = number(candidates[0].get(basic+'_measure'))
                pct = number(candidates[0].get(basic+'_pct'))
                item['percentiles'][basic] = pct if pct is not None and pct<=100 else None
        official[population] = item
    out['official_sms_by_population'] = official
    out['coverage_issues'] = issues
    out['future_labels'] = {target:{'value':None,'status':'FOLLOW_UP_NOT_ESTABLISHED'} for target in ['oos_next_90d','crash_report_next_180d','severe_report_next_365d']}
    out['model_eligibility'] = 'BLOCKED_NO_TEMPORAL_VALIDATION'
    return out

def build(cuts, as_of, output, month_end=False):
    at = timestamp(as_of)
    if at > timestamp(now()):
        raise ValueError('Cannot construct a future as-of observation')
    if at.utcoffset() != dt.timedelta(0):
        raise ValueError('Panel cutoffs must use UTC')
    if month_end and (at.day != calendar.monthrange(at.year,at.month)[1] or at.time()!=dt.time(23,59,59)):
        raise ValueError('Monthly rows require the completed UTC month end at 23:59:59')
    # Verify every supplied artifact even when it is too new to serve as a feature cut.
    verified = [(path,load_verified(path)) for path in cuts]
    if len({tuple(result[1]['dots']) for _,result in verified})>1:
        raise ValueError('Source cuts use different cohorts; population changes require explicit governance')
    eligible = [(path,result) for path,result in verified if timestamp(result[0]['completed_at'])<=at and timestamp(result[1]['selected_at'])<=at]
    if not eligible:
        raise ValueError('No verified source cut was available at the requested as-of time')
    path, (manifest, cohort, data) = max(eligible,key=lambda x:timestamp(x[1][0]['completed_at']))
    # A single row never combines current Census with an older source cut.
    rows = [features(dot,data,as_of) for dot in cohort['dots']]
    for row in rows:
        row['source_cut'] = manifest['snapshot_id']
        row['source_cut_available_at'] = manifest['completed_at']
    output = pathlib.Path(output)
    output.mkdir(parents=True,exist_ok=False)
    with (output/'features.jsonl').open('x',encoding='utf-8',newline='\n') as handle:
        for row in rows:
            handle.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
    report = {'feature_schema_version':VERSION,'as_of':as_of,'grain':'USDOT_MONTH_END' if month_end else 'USDOT_AS_OF',
              'created_at':now(), 'row_count':len(rows), 'source_cut':manifest['snapshot_id'],
              'source_cut_available_at':manifest['completed_at'],'source_manifest_sha256':hash_file(pathlib.Path(path)/'manifest.json'),
              'cohort_sha256':manifest['cohort_sha256'],'features_sha256':hash_file(output/'features.jsonl'),
              'code_sha256':{name:hash_file(pathlib.Path(__file__).parent/name) for name in
                             ['build_asof_panel.py','cohort_snapshot.py','snapshot_store.py','verify_snapshot.py','validate_fmcsa_data_contract.py']},
              'source_rows':{s['id']:s['row_count'] for s in manifest['datasets']},
              'fleet_groups':dict(Counter(row['fleet_group'] for row in rows)),
              'coverage_issues':dict(Counter(issue for row in rows for issue in row['coverage_issues'])),
              'feature_coverage':{field:{'known':sum(row[field] is not None for row in rows),'total':len(rows)} for field in
                                  ['power_units_reported','drivers_reported','vmt_reported','mcs150_age_days','inspections_365d','oos_rate_365d','severe_vehicle_reports_365d']},
              'sms_population_coverage':{population:dict(Counter(row['official_sms_by_population'][population]['status'] for row in rows)) for population in SMS},
              'history_status':'CURRENT_BASELINE_ONLY','forecast_status':'BLOCKED_NO_MATURE_LABELS',
              'representative_validation_population':False}
    write_once(output/'manifest.json',report)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cut',action='append',required=True)
    parser.add_argument('--as-of',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--month-end',action='store_true')
    args=parser.parse_args()
    print(json.dumps(build(args.cut,args.as_of,args.output,args.month_end),indent=2))
