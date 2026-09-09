"""Descriptive current-publication comparisons; no SMS or claims predictions."""
import datetime as dt
import json
import pathlib
from private_workspace_store import dot

def open_warehouse(path):
    import duckdb
    db=duckdb.connect(str(path),read_only=True)
    try:
        acceptance=json.loads(db.execute('SELECT acceptance_json FROM warehouse_acceptance').fetchone()[0])
        if acceptance.get('status')!='VERIFIED':raise ValueError('Warehouse is not verified')
        return db
    except Exception:
        db.close();raise

def census(db,dots):
    ids=[dot(x) for x in dots]
    cursor=db.execute('SELECT * FROM raw_az4n_8mr2 WHERE dot_number IN ('+','.join('?' for _ in ids)+')',ids)
    fields=[f[0] for f in cursor.description]
    rows=[dict(zip(fields,row)) for row in cursor.fetchall()]
    if len({r['dot_number'] for r in rows})!=len(rows):raise ValueError('Census identity is not unique')
    return rows

def group_summary(db,dots):
    dots=sorted({dot(x) for x in dots},key=int)
    rows=census(db,dots);totals={}
    for field in ('power_units','total_drivers','mcs150_mileage'):
        known=[int(r[field]) for r in rows if isinstance(r.get(field),str) and r[field].isdigit()]
        totals[field]={'sum':sum(known) if known else None,'known':len(known),'denominator':len(dots)}
    return {'members':dots,'matched':len(rows),'missing':sorted(set(dots)-{r['dot_number'] for r in rows}),
            'reported_totals':totals,'reports':[{'dot':r['dot_number'],'name':r.get('legal_name'),'status':r.get('status_code'),'report_date':r.get('mcs150_date'),'mileage_year':r.get('mcs150_mileage_year')} for r in rows],
            'limitation':'Reviewed relationships only. Report dates may differ. These are summed registration reports, not deduplicated physical vehicles, insured exposure or a corporate risk score.'}

def peers(db,seed):
    target=census(db,[seed])
    if len(target)!=1:raise ValueError('Unique Census carrier required')
    row=target[0];keys=('phy_country','carrier_operation','fleetsize')
    if any(not row.get(key) for key in keys):raise ValueError('Country, operation and fleet band are required for peers')
    lineage=db.execute("SELECT cut,available_at,sha256 FROM source_lineage WHERE source_id='az4n-8mr2'").fetchone()
    if not lineage:raise ValueError('Census lineage missing')
    day=dt.datetime.fromisoformat(lineage[1].replace('Z','+00:00')).date()
    # Each excluded row stays in the candidate denominator. No unknown-to-zero conversion.
    db.execute('''CREATE OR REPLACE TEMP VIEW peer_candidates AS SELECT *,
      try_cast(power_units AS BIGINT) AS pu,try_cast(total_drivers AS BIGINT) AS drivers,
      coalesce(try_strptime(mcs150_date,'%Y%m%d'),try_strptime(substr(mcs150_date,1,10),'%Y-%m-%d')) AS reported
      FROM raw_az4n_8mr2''')
    where='phy_country=? AND carrier_operation=? AND fleetsize=? AND status_code=\'A\''
    values=[row[key] for key in keys]
    eligible="regexp_full_match(power_units,'[0-9]+') AND regexp_full_match(total_drivers,'[0-9]+') AND pu>0 AND drivers>0 AND reported::DATE BETWEEN ? AND ? AND NOT (pu>=20 AND pu::DOUBLE>10.0*drivers) AND NOT (drivers>=20 AND drivers::DOUBLE>10.0*pu)"
    dates=[day-dt.timedelta(days=730),day]
    candidate_count=db.execute('SELECT count(*) FROM peer_candidates WHERE '+where,values).fetchone()[0]
    unique_count=db.execute('SELECT count(DISTINCT dot_number) FROM peer_candidates WHERE '+where,values).fetchone()[0]
    if unique_count!=candidate_count:raise ValueError('Peer Census identities are not unique')
    result=db.execute('SELECT count(*),quantile_cont(pu,[0.25,0.5,0.75]),quantile_cont(drivers,[0.25,0.5,0.75]) FROM peer_candidates WHERE '+where+' AND '+eligible,values+dates).fetchone()
    included=db.execute('SELECT count(*) FROM peer_candidates WHERE dot_number=? AND '+where+' AND '+eligible,[seed]+values+dates).fetchone()[0]==1
    return {'kind':'TRANSPORT_CALCULATED_DESCRIPTIVE_EXPOSURE','ruleset':'CENSUS_PEERS_1','dot':seed,
            'cohort':dict(zip(keys,values)),'registration':'A','candidate_count':candidate_count,'eligible_count':result[0],
            'excluded_count':candidate_count-result[0],'target_eligible':included,'target':{k:row.get(k) for k in ('power_units','total_drivers','mcs150_date')},
            'status':'AVAILABLE' if result[0]>=30 and included else 'INSUFFICIENT_COMPARABLE_EVIDENCE',
            'quartiles':{'power_units':result[1],'drivers':result[2]} if result[0]>=30 and included else None,
            'quartile_order':['p25','median','p75'],'source':{'id':'az4n-8mr2','cut':lineage[0],'available_at':lineage[1],'sha256':lineage[2]},
            'eligibility':'Same country, operation and fleet band; active; positive known units/drivers; report age 0–730 days at source availability; excludes >=20 units with >10 units per driver or >=20 drivers with >10 drivers per unit. Minimum 30 eligible registrations. Target included in cohort.',
            'limitation':'Current-publication exposure comparison only. Reporting periods vary. Not an official SMS percentile, safety benchmark, insurance price or prediction.'}
