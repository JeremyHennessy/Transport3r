"""Knowledge-time eligibility audit; deliberately does not emit scores or mature labels."""
import argparse,datetime as dt,json,pathlib
from cohort_snapshot import load_verified,source_dot
from snapshot_store import now,write_once
from validate_fmcsa_data_contract import parse_fmcsa_date
from verify_snapshot import timestamp

TIMELINES={
 'daily_inspections':{'source':'fx4q-ay7w','event_field':'insp_date','knowledge':'cut acquisition; later corrections remain possible'},
 'daily_crashes':{'source':'aayw-vxb3','event_field':'report_date','knowledge':'cut acquisition; event occurrence is not first availability'},
 'census_exposure':{'source':'az4n-8mr2','event_field':'mcs150_date','knowledge':'reported date does not establish when this value became available'},
 'sms':{'sources':['kjg3-diqy','rbkj-cgst','8mt8-2mdr','4wxs-vbns','4y6x-dmck','h9zy-gjn8','m3ry-qcip','h3zn-uid9'],'knowledge':'requires official monthly artifact identity bound to these exact extracts'},
 'authority':{'source':'yu5v-wbh6','event_field':'status_change_date','knowledge':'action effective date differs from source availability'},
 'insurance':{'source':'3uet-3z4i','event_fields':['effective_date','cancl_effective_date'],'knowledge':'filing lifecycle dates do not prove insurance coverage'},
 'change_feeds':{'knowledge':'latest published differences; not a durable historical event ledger by themselves'},
 'future_labels':{'knowledge':'requires future persisted surveillance, reporting-lag policy and mature horizons'},
}
OUTCOMES=[{'id':'future_crash_vehicle_report','horizon_days':180,'grain':'involved commercial vehicle report','not_claim':'fault or insurance loss'},
          {'id':'future_oos_inspection','horizon_days':90,'grain':'distinct inspection with known positive oos_total','not_claim':'carrier-wide safety determination'},
          {'id':'future_authority_record_change','horizon_days':90,'grain':'docket and authority lifecycle','not_claim':'current legal prohibition'},
          {'id':'future_filing_record_disruption','horizon_days':90,'grain':'verified policy/filing lifecycle','not_claim':'coverage gap without document confirmation'},
          {'id':'future_severe_crash_vehicle_report','horizon_days':365,'grain':'vehicle report with known fatal/injury indicator','not_claim':'insurance severity or loss'},
          {'id':'future_violation_evidence_change','horizon_days':90,'grain':'verified inspection/violation records','not_claim':'deterioration without comparable enforcement exposure'}]

def exposure_eligibility(row,as_of):
    report=parse_fmcsa_date(row.get('mcs150_date'));day=timestamp(as_of).date();issues=[]
    if row.get('status_code')!='A':issues.append('INACTIVE_OR_UNKNOWN_REGISTRATION')
    if report is None:issues.append('MISSING_REPORT_DATE')
    elif report>day:issues.append('FUTURE_REPORT_DATE')
    elif (day-report).days>730:issues.append('STALE_REPORTED_EXPOSURE')
    for field in ['power_units','total_drivers','mcs150_mileage']:
        raw=row.get(field)
        if not isinstance(raw,str) or not raw.isdigit() or int(raw)<=0:issues.append('INELIGIBLE_'+field.upper())
    year=row.get('mcs150_mileage_year')
    if not isinstance(year,str) or not year.isdigit() or not day.year-2<=int(year)<=day.year:issues.append('MILEAGE_YEAR_INELIGIBLE')
    return issues

def assess(cut,as_of=None):
    m,cohort,data=load_verified(cut);as_of=as_of or now()
    if timestamp(m['completed_at'])>timestamp(as_of):raise ValueError('Cut was not knowable at the requested observation')
    if timestamp(as_of)>timestamp(now()):raise ValueError('Future observation unavailable')
    rows=[]
    for dot in cohort['dots']:
        census=[row for row in data['az4n-8mr2'] if row.get('dot_number')==dot]
        issues=exposure_eligibility(census[0],as_of) if len(census)==1 else ['CENSUS_IDENTITY_NOT_UNIQUE']
        rows.append({'dot_number':dot,'observation_date':as_of,'source_cut':m['snapshot_id'],'source_cut_available_at':m['completed_at'],'exposure_source':'az4n-8mr2','exposure_report_date':census[0].get('mcs150_date') if len(census)==1 else None,'exposure_issues':issues,'training_eligible':False,'label_eligible':False,'labels':{target['id']:None for target in OUTCOMES},'future_label_windows':{target['id']:{'start_exclusive':as_of,'end_inclusive':(timestamp(as_of)+dt.timedelta(days=target['horizon_days'])).isoformat(),'status':'FOLLOW_UP_NOT_ESTABLISHED'} for target in OUTCOMES}})
    return {'version':'TEMPORAL_READINESS_1','created_at':now(),'source_cut':m['snapshot_id'],'observation':as_of,'timelines':TIMELINES,'carriers':rows,'eligible_training_rows':0,'outcomes':OUTCOMES,'blockers':['EXACT_DATAHUB_SMS_RELEASE_BINDING_UNVERIFIED','NO_MATURE_FUTURE_SURVEILLANCE','NO_MATCHED_HISTORICAL_MONTH_END_CUTS','NO_INSURER_CLAIMS_OR_LOSS_OUTCOMES'],'website_snapshot_is_not_datahub_binding':True,'forecast_status':'BLOCKED','tri_v02_status':'NOT_TRAINED_OR_SCORED','powerbi_numerical_reconciliation':'BLOCKED_UNMATCHED_SOURCE_CUT_AND_DAX_EXECUTION'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--cut',required=True);parser.add_argument('--output',required=True);parser.add_argument('--as-of');args=parser.parse_args()
    result=assess(args.cut,args.as_of);write_once(pathlib.Path(args.output),result);print(json.dumps({'status':'AUDITED','carriers':len(result['carriers']),'eligible_training_rows':0,'blockers':result['blockers']},indent=2))
