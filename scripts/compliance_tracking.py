"""Evidence-based compliance reviews. Never a legal compliance certification."""
from contextlib import closing
import datetime as dt
import json
import pathlib
from snapshot_store import digest, now
from private_workspace_store import dot

VERSION = 'COMPLIANCE_REVIEW_1'
SOURCES = {'az4n-8mr2':'Registration', 'inys-ebih':'Operating authority', 'c5y8-a4uz':'Active/pending filings',
           '3uet-3z4i':'Filing history', 'wb4f-neki':'Revocation/suspension records',
           'p2mt-9ige':'New Entrant OOS orders', 'yu5v-wbh6':'Authority history'}


def day(value):
    text=str(value or '').strip()
    if text in ('','0','00000000'):return None
    try:
        return dt.datetime.strptime(text,'%Y%m%d').date() if len(text)==8 and text.isdigit() else dt.date.fromisoformat(text[:10])
    except ValueError:return None


def business_rows(rows):
    # Exact duplicate source evidence is not a second filing/order. Keep published row count separately.
    unique={digest({k.lower():v for k,v in r.items() if not k.startswith('_') and k!='source_row_id'}):
            {k.lower():v for k,v in r.items() if not k.startswith('_') and k!='source_row_id'} for r in rows}
    return [unique[k] for k in sorted(unique)]


def order_state(row,at):
    issued=day(row.get('oos_date'));raw=row.get('rescind_date');rescinded=day(raw)
    if not issued or (raw not in (None,'') and not rescinded) or (rescinded and rescinded<issued):return 'UNKNOWN'
    if issued>at:return 'FUTURE_ISSUE'
    if rescinded:return 'RESCINDED' if rescinded<=at else 'RESCISSION_SCHEDULED'
    return 'ISSUED_NO_RESCISSION_RECORDED'


def assess(seed,cut,observed_at,sources,mode):
    seed=dot(seed);at=day(observed_at)
    if not at:raise ValueError('A valid observation date is required')
    checks=[]
    def add(code,title,sid,state,summary,action,values):
        checks.append({'id':code,'title':title,'source_id':sid,'state':state,'summary':summary,'action':action,
                       'values':values,'fingerprint':digest([code,state,values])})
    data={sid:business_rows(sources[sid].get('rows',[])) for sid in SOURCES if sid in sources and sources[sid].get('status')=='VERIFIED'}
    for sid,title in SOURCES.items():
        if sid not in data:add('SOURCE_'+sid,title,sid,'DATA_GAP','Verified source evidence unavailable.','Refresh this carrier; do not infer a clean result from a failed source.',{})
    rows=data.get('az4n-8mr2')
    if rows is not None:
        if len(rows)!=1:add('REGISTRATION','Registration identity','az4n-8mr2','DATA_GAP','No unique Census registration.','Verify USDOT identity with FMCSA.',{'rows':len(rows)})
        else:
            r=rows[0];status=r.get('status_code')
            state='INFORMATION' if status=='A' else 'REVIEW' if status in ('I','P') else 'DATA_GAP'
            add('REGISTRATION','Registration status','az4n-8mr2',state,'Published Census status: '+str(status or 'unknown')+'.','Confirm registration status and whether the planned operation requires authority.',{'status':status})
            report=day(r.get('mcs150_date'));age=(at-report).days if report else None
            state='DATA_GAP' if age is None or age<0 else 'REVIEW' if age>730 else 'INFORMATION'
            add('REPORT_AGE','Registration report age','az4n-8mr2',state,
                'Report date '+str(report or 'unavailable')+'; '+('age unknown' if age is None else str(age)+' days old at observation')+'.',
                'Verify the registered details and applicable biennial filing schedule. The 730-day flag is a review heuristic, not a statutory due-date calculation.',{'report_date':r.get('mcs150_date'),'age_band':'unknown' if age is None else 'future' if age<0 else 'over_730_days' if age>730 else 'within_730_days'})
    rows=data.get('inys-ebih')
    if rows is not None:
        evidence=[{k:r.get(k) for k in ('docket_number','op_auth_type','op_auth_status','cargo_req','bond_req','cargo_file','bond_file')} for r in rows]
        statuses=[str(r.get('op_auth_status') or '').strip().lower() for r in rows]
        conflict={}
        for r in rows:conflict.setdefault((r.get('docket_number'),r.get('op_auth_type')),set()).add(r.get('op_auth_status'))
        state='DATA_GAP' if not rows or any(not x for x in statuses) or any(len(v)>1 for v in conflict.values()) else 'REVIEW' if any(x!='active' for x in statuses) else 'INFORMATION'
        add('AUTHORITY','Operating authority','inys-ebih',state,f'{len(rows)} distinct authority rows; '+('; '.join(sorted(set(statuses))) or 'no status returned')+'.',
            'Review each authority type and its applicability in FMCSA Licensing & Insurance. Census registration status is separate.',evidence)
    rows=data.get('c5y8-a4uz')
    if rows is not None:
        unknown=sum(day(r.get('effective_date')) is None for r in rows);future=sum(day(r.get('effective_date')) is not None and day(r.get('effective_date'))>at for r in rows)
        add('FILINGS','Active/pending insurance filings','c5y8-a4uz','DATA_GAP' if not rows or unknown else 'REVIEW' if future else 'INFORMATION',
            f'{len(rows)} distinct filing rows; {future} future effective dates; {unknown} unknown dates.',
            'Check policy documents, filing type, dates and required authority. No returned filing does not establish uninsured operation; raw amounts are not converted into certified coverage limits.',rows)
    rows=data.get('3uet-3z4i')
    if rows is not None:
        relevant=[];unknown=0
        for r in rows:
            effective=day(r.get('cancl_effective_date'))
            if not effective:unknown+=1
            if effective and -30 <= (effective-at).days <= 30:relevant.append(r)
        add('FILING_CHANGES','Recent/upcoming filing-history changes','3uet-3z4i','REVIEW' if relevant else 'DATA_GAP' if unknown else 'INFORMATION',
            f'{len(relevant)} changes effective within 30 days before/after observation; {unknown} unresolved dates in history.',
            'Review cancellation, replacement, name-change and transfer reasons separately. History alone does not establish a coverage gap.',{'near_observation':relevant,'unknown_dates':unknown})
    rows=data.get('wb4f-neki')
    if rows is not None:
        unknown=sum(day(r.get('order1_effective_date')) is None for r in rows)
        add('REVOCATION_RECORDS','Revocation/suspension evidence','wb4f-neki','REVIEW' if rows else 'INFORMATION',
            f'{len(rows)} distinct order records; {unknown} unresolved effective dates.',
            'Verify current effect, scope and any later reinstatement with official authority evidence. An historical order is not a current prohibition.',rows)
    rows=data.get('p2mt-9ige')
    if rows is not None:
        states=[{'state':order_state(r,at),'record':r} for r in rows]
        counts={s:sum(r['state']==s for r in states) for s in sorted({r['state']for r in states})}
        state='REVIEW' if any(r['state'] in ('ISSUED_NO_RESCISSION_RECORDED','RESCISSION_SCHEDULED') for r in states) else 'DATA_GAP' if any(r['state'] in ('UNKNOWN','FUTURE_ISSUE')for r in states) else 'INFORMATION'
        add('NEW_ENTRANT_OOS','New Entrant OOS / rescission','p2mt-9ige',state,
            '; '.join(f'{k}: {v}' for k,v in counts.items()) or 'No New Entrant order rows returned.',
            'Confirm the order and rescission dates with FMCSA. The source STATUS field is entity status, not proof of order effect.',states)
    rows=data.get('yu5v-wbh6')
    if rows is not None:
        recent=[r for r in rows if day(r.get('status_change_date')) and abs((day(r['status_change_date'])-at).days)<=30]
        unknown=sum(day(r.get('status_change_date')) is None for r in rows)
        add('AUTHORITY_CHANGES','Recent authority-history changes','yu5v-wbh6','REVIEW' if recent else 'DATA_GAP' if unknown else 'INFORMATION',
            f'{len(recent)} changes within 30 days before/after observation; {unknown} unknown dates.',
            'Inspect the affected authority type, reason and effective date; compare with the current authority rows.',{'near_observation':recent,'unknown_dates':unknown})
    gaps=sum(c['state']=='DATA_GAP' for c in checks);reviews=sum(c['state']=='REVIEW' for c in checks)
    return {'id':digest([VERSION,seed,cut]),'version':VERSION,'dot':seed,'cut':cut,'observed_at':observed_at,'mode':mode,
            'name':(data.get('az4n-8mr2') or [{}])[0].get('legal_name'),'status':'REVIEW_NEEDED' if reviews else 'INCOMPLETE_EVIDENCE' if gaps else 'NO_RULE_TRIGGER',
            'review_count':reviews,'gap_count':gaps,'checks':checks,'sources':sources,
            'limitation':'Evidence review at the recorded observation time, not certification of legal compliance, operating permission or insurance coverage. No rule trigger is not a clean-carrier conclusion. Public-data changes are never submitted to FMCSA by this app.'}


def persist(db,result):
    old=db.execute('SELECT payload FROM compliance_observations WHERE dot=? ORDER BY observed_at DESC,id DESC LIMIT 1',(result['dot'],)).fetchone()
    previous=json.loads(old[0]) if old else None
    payload=json.dumps(result,sort_keys=True)
    existing=db.execute('SELECT payload FROM compliance_observations WHERE id=?',(result['id'],)).fetchone()
    if existing:
        if existing[0]!=payload:raise ValueError('Previously stored compliance observation changed')
        return {'observations':0,'delivered':0}
    delivered=0
    with db:
        db.execute('INSERT INTO compliance_observations VALUES (?,?,?,?,?)',(result['id'],result['dot'],result['observed_at'],result['cut'],payload))
        subscription=db.execute('SELECT created_at FROM subscriptions WHERE dot=? AND enabled=1',(result['dot'],)).fetchone()
        if previous and subscription and previous['version']==result['version'] and subscription[0]<=previous['observed_at']<result['observed_at']:
            before={c['id']:c for c in previous['checks']};after={c['id']:c for c in result['checks']}
            changes=[key for key in sorted(set(before)|set(after)) if before.get(key,{}).get('fingerprint')!=after.get(key,{}).get('fingerprint')]
            if changes:
                at=now();identity=digest([VERSION,result['dot'],previous['id'],result['id']])
                alert={'rule':'COMPLIANCE_EVIDENCE_CHANGED','materiality':'Compliance assessment changed between verified observations, including dated lifecycle/window transitions. Review improvements, deteriorations and unknowns; no automatic legal or coverage determination.',
                       'dot':result['dot'],'previous_observed_at':previous['observed_at'],'current_observed_at':result['observed_at'],'detected_at':at,
                       'previous_cut':previous['cut'],'current_cut':result['cut'],'previous_state':{k:before.get(k) for k in changes},'current_state':{k:after.get(k) for k in changes},
                       'evidence_link':f'http://127.0.0.1:4789/#compliance','observation_id':result['id']}
                cursor=db.execute('INSERT OR IGNORE INTO inbox VALUES (?,?,?,?,NULL)',(identity,result['dot'],json.dumps(alert),at));delivered=cursor.rowcount
    return {'observations':1,'delivered':delivered}


def capture_verified_cut(evidence_path,db):
    from evidence_warehouse import connect, verify_cut
    with closing(connect(evidence_path)) as evidence:
        evidence.execute('BEGIN')
        cut=evidence.execute('SELECT * FROM cuts ORDER BY available_us DESC LIMIT 1').fetchone()
        if not cut:raise ValueError('No verified observation available')
        verify_cut(evidence,cut['cut_id'])
        metadata={r['source_id']:dict(r) for r in evidence.execute('SELECT * FROM sources WHERE cut_id=?',(cut['cut_id'],))}
        if not set(SOURCES)<=set(metadata):raise ValueError('Complete compliance source set required')
        total={'observations':0,'delivered':0}
        for (seed,) in evidence.execute('SELECT dot FROM members WHERE cut_id=? ORDER BY dot',(cut['cut_id'],)):
            sources={}
            for sid in SOURCES:
                meta=metadata[sid];lineage=json.loads(meta['lineage_json'])
                rows=[json.loads(r[0]) for r in evidence.execute('SELECT payload FROM records WHERE cut_id=? AND dot=? AND source_id=? ORDER BY ordinal',(cut['cut_id'],seed,sid))]
                sources[sid]={'status':'VERIFIED','rows':rows,'published_carrier_rows':len(rows),'available_at':lineage['after']['observed_at'],
                              'sha256':meta['rows_sha256'],'hash_scope':'complete scoped source rows','url':'https://data.transportation.gov/d/'+sid}
            counts=persist(db,assess(seed,cut['cut_id'],cut['available_at'],sources,'MONITORED_VERIFIED_CUT'))
            for key in total:total[key]+=counts[key]
        return total


def nationwide_baseline(warehouse,seed):
    from workspace_analytics import open_warehouse
    with closing(open_warehouse(warehouse)) as source:
        sources={}
        for sid in SOURCES:
            meta=source.execute('SELECT available_at,sha256 FROM source_lineage WHERE source_id=?',[sid]).fetchone()
            if not meta:raise ValueError('Required source unavailable: '+sid)
            rows=source.execute('SELECT * FROM carrier_'+sid.replace('-','_')+' WHERE _dot_number=?',[dot(seed)])
            fields=[r[0]for r in rows.description];values=[dict(zip(fields,row)) for row in rows.fetchall()]
            sources[sid]={'status':'VERIFIED','rows':values,'published_carrier_rows':len(values),'available_at':meta[0],
                          'sha256':meta[1],'hash_scope':'complete nationwide source file','url':'https://data.transportation.gov/d/'+sid}
        cut='NATIONWIDE:'+digest({sid:{k:v for k,v in s.items() if k!='rows'}for sid,s in sources.items()})
        return assess(seed,cut,max(s['available_at']for s in sources.values()),sources,'NATIONWIDE_BASELINE')


def latest(db,seed):
    row=db.execute('SELECT payload FROM compliance_observations WHERE dot=? ORDER BY observed_at DESC,id DESC LIMIT 1',(dot(seed),)).fetchone()
    return json.loads(row[0]) if row else None


def save_action(db,body,reviewer):
    identifier=body.get('observation_id');row=db.execute('SELECT payload FROM compliance_observations WHERE id=?',(identifier,)).fetchone()
    if not row:raise ValueError('Load a verified compliance review first')
    evidence=json.loads(row[0]);check=next((c for c in evidence['checks'] if c['id']==body.get('check_id')),None)
    if not check:raise ValueError('Unknown compliance check')
    status=body.get('status');notes=body.get('notes','');due=body.get('due_date') or None
    if status not in ('open','in_review','resolved') or not isinstance(notes,str) or not 10<=len(notes.strip())<=8000:raise ValueError('A review state and 10–8,000 characters of rationale are required')
    if due and (not isinstance(due,str) or not day(due) or str(day(due))!=due):raise ValueError('Use a valid YYYY-MM-DD follow-up date')
    identity=digest([evidence['dot'],check['id']]);at=now()
    with db:
        prior=db.execute('SELECT * FROM compliance_actions WHERE id=?',(identity,)).fetchone()
        db.execute('INSERT OR REPLACE INTO compliance_actions VALUES (?,?,?,?,?,?,?,?,?,?,?)',(identity,evidence['dot'],check['id'],identifier,check['fingerprint'],status,due,notes.strip(),reviewer,at,check['title']))
        db.execute('INSERT INTO compliance_action_history(action_id,payload,changed_at) VALUES (?,?,?)',(identity,json.dumps({'previous':dict(prior) if prior else None,'observation_id':identifier,'check':check,'status':status,'due_date':due,'notes':notes.strip(),'reviewer':reviewer}),at))
    return identity


def actions(db,seed=None):
    rows=[dict(r) for r in db.execute('SELECT * FROM compliance_actions'+(' WHERE dot=?' if seed else '')+' ORDER BY updated_at DESC',([seed]if seed else []))]
    today=dt.date.today()
    for r in rows:
        r['overdue']=r['status']!='resolved' and bool(r['due_date']) and day(r['due_date'])<today
        current=latest(db,r['dot']);check=next((c for c in current['checks'] if c['id']==r['check_id']),None) if current else None
        r['evidence_changed']=not check or check['fingerprint']!=r['fingerprint']
    return rows
