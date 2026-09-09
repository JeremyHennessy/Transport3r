"""Durable, idempotent comparisons of verified observations; never a live scheduler."""
import argparse,datetime as dt,json,pathlib,sqlite3
from evidence_warehouse import connect,verify_cut,cut_eligible
from snapshot_store import digest,now

VERSION='PUBLIC_CHANGE_RULES_1'
DDL='''CREATE TABLE IF NOT EXISTS alert_runs(previous_cut TEXT NOT NULL,current_cut TEXT NOT NULL,rule_version TEXT NOT NULL,detected_at TEXT NOT NULL,PRIMARY KEY(previous_cut,current_cut,rule_version));
CREATE TABLE IF NOT EXISTS alerts(alert_id TEXT PRIMARY KEY,dot TEXT NOT NULL,rule TEXT NOT NULL,source TEXT NOT NULL,previous_cut TEXT NOT NULL,current_cut TEXT NOT NULL,previous_observed_at TEXT NOT NULL,current_observed_at TEXT NOT NULL,detected_at TEXT NOT NULL,previous_state TEXT NOT NULL,current_state TEXT NOT NULL,evidence_link TEXT NOT NULL,materiality TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alert_issues(previous_cut TEXT NOT NULL,current_cut TEXT NOT NULL,dot TEXT NOT NULL,source TEXT NOT NULL,reason TEXT NOT NULL,UNIQUE(previous_cut,current_cut,dot,source,reason));'''

def compare_states(dot,source,previous,current):
    alerts=[];issues=[]
    if source=='az4n-8mr2':
        if len(previous)!=1 or len(current)!=1:return [],['CENSUS_IDENTITY_NOT_UNIQUE']
        for field in ['power_units','total_drivers','mcs150_mileage','mcs150_mileage_year','status_code','mcs150_date']:
            before,after=previous[0].get(field),current[0].get(field)
            if before is None or after is None:issues.append('UNKNOWN_'+field);continue
            if before==after:continue
            if field in ('power_units','total_drivers','mcs150_mileage'):
                try:
                    a,b=int(before),int(after)
                    if a<0 or b<0:raise ValueError()
                except (ValueError,TypeError):issues.append('INVALID_'+field);continue
                if abs(b-a)<max(1,abs(a)*.1):continue
                rule='Reported exposure changed by at least 10% and one unit; not verified operating exposure.'
            else:rule='Reported status/date/year changed; source fields, not a coverage or safety determination.'
            alerts.append({'rule':'CENSUS_'+field,'previous':before,'current':after,'materiality':rule})
    elif source in ('aayw-vxb3','fx4q-ay7w'):
        key='crash_id' if source=='aayw-vxb3' else 'inspection_id'
        for rows in [previous,current]:
            ids=[r.get(key) for r in rows]
            if any(not id for id in ids) or len(set(ids))!=len(ids):return [],['EVENT_IDENTITY_NOT_UNIQUE']
        known={row[key] for row in previous}
        for row in current:
            if row[key] in known:continue
            if source=='fx4q-ay7w':
                try:
                    if int(row.get('oos_total',''))<=0:continue
                except (ValueError,TypeError):issues.append('UNKNOWN_OOS:'+row[key]);continue
            alerts.append({'rule':'NEWLY_OBSERVED_CRASH_REPORT' if source=='aayw-vxb3' else 'NEWLY_OBSERVED_OOS_INSPECTION','previous':None,'current':row,'materiality':'Absent from the earlier complete source query and present now. Newly observed, not necessarily newly occurred; involvement does not establish fault.'})
    elif source in ('inys-ebih','c5y8-a4uz','3uet-3z4i','wb4f-neki','876r-jsdb'):
        def state(rows):return sorted([{k:v for k,v in row.items() if k!='source_row_id'} for row in rows],key=digest)
        before,after=state(previous),state(current)
        if before!=after:alerts.append({'rule':'VIOLATION_EVIDENCE_CHANGED' if source=='876r-jsdb' else 'AUTHORITY_OR_FILING_RECORD_SET_CHANGED','previous':before,'current':after,'materiality':'Returned official record set changed; review source fields and event dates. This is an evidence change, not established deterioration. No automatic current prohibition, cancellation or coverage-gap determination.'})
    return alerts,sorted(set(issues))

def run(evidence_db,alerts_db,previous_cut=None,current_cut=None):
    source=connect(evidence_db)
    try:
        cuts=source.execute('SELECT cut_id,available_at,manifest_json FROM cuts ORDER BY available_us').fetchall()
        cuts=[cut for cut in cuts if cut_eligible(json.loads(cut['manifest_json']))]
        if len(cuts)<2:return {'status':'BASELINE_ONLY','alerts':0,'reason':'Two persisted verified observations are required.'}
        current_cut=current_cut or cuts[-1]['cut_id'];previous_cut=previous_cut or cuts[-2]['cut_id']
        prior=verify_cut(source,previous_cut);current=verify_cut(source,current_cut)
        if prior['available_at']>=current['available_at']:raise ValueError('Strictly ordered observations required')
        def members(cut):return {r[0] for r in source.execute('SELECT dot FROM members WHERE cut_id=?',(cut,))}
        dots=members(previous_cut)
        if dots!=members(current_cut):raise ValueError('Comparable cohort membership required')
        source_ids=set(prior['source_rows'])&set(current['source_rows']);detected=now()
        path=pathlib.Path(alerts_db);path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(path);db.executescript(DDL)
        existing=db.execute('SELECT 1 FROM alert_runs WHERE previous_cut=? AND current_cut=? AND rule_version=?',(previous_cut,current_cut,VERSION)).fetchone()
        if existing:
            db.close()
            return {'status':'ALREADY_COMPARED','previous_cut':previous_cut,'current_cut':current_cut}
        observation_times={(cut,sid):json.loads(lineage)['after']['observed_at'] for cut,sid,lineage in source.execute('SELECT cut_id,source_id,lineage_json FROM sources WHERE cut_id IN (?,?)',(previous_cut,current_cut))}
        with db:
            count=0;issue_count=0
            for dot in sorted(dots):
                for sid in sorted(source_ids&{'az4n-8mr2','aayw-vxb3','fx4q-ay7w','inys-ebih','c5y8-a4uz','3uet-3z4i','wb4f-neki','876r-jsdb'}):
                    def rows(cut):return [json.loads(r[0]) for r in source.execute('SELECT payload FROM records WHERE cut_id=? AND dot=? AND source_id=? ORDER BY ordinal',(cut,dot,sid))]
                    changes,issues=compare_states(dot,sid,rows(previous_cut),rows(current_cut))
                    for item in changes:
                        identity=digest([VERSION,previous_cut,current_cut,dot,sid,item]);link=f'https://jeremyhennessy.github.io/Transport3r/#/carrier/{dot}/evidence'
                        db.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,dot,item['rule'],sid,previous_cut,current_cut,observation_times[(previous_cut,sid)],observation_times[(current_cut,sid)],detected,json.dumps(item['previous']),json.dumps(item['current']),link,item['materiality']));count+=1
                    for issue in issues:db.execute('INSERT INTO alert_issues VALUES (?,?,?,?,?)',(previous_cut,current_cut,dot,sid,issue));issue_count+=1
            db.execute('INSERT INTO alert_runs VALUES (?,?,?,?)',(previous_cut,current_cut,VERSION,detected))
        db.close()
        return {'status':'COMPARED','previous_cut':previous_cut,'current_cut':current_cut,'alerts':count,'issues':issue_count,'rule_version':VERSION,'sms_movement':'NOT_EVALUATED_UNBOUND_RELEASE','scheduled':False}
    finally:source.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence-db',required=True);parser.add_argument('--alerts-db',required=True);parser.add_argument('--previous-cut');parser.add_argument('--current-cut');args=parser.parse_args()
    print(json.dumps(run(args.evidence_db,args.alerts_db,args.previous_cut,args.current_cut),indent=2))
