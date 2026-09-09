"""Private local portfolio foundation. This database is never served by GitHub Pages."""
import argparse,datetime as dt,json,pathlib,re,sqlite3
from snapshot_store import now,digest
VERSION='INSURER_PORTFOLIO_1'
FIELDS={'account_id','policy_id','dot_number','policy_start','policy_end','status','currency','limit_minor','premium_minor','class_code','territory','broker','scheduled_units','insured_vmt','notes','review_status'}
def validate(record):
    if not isinstance(record,dict) or set(record)-FIELDS:raise ValueError('Unknown portfolio fields')
    for key in ['account_id','policy_id','dot_number','policy_start','policy_end','status','review_status']:
        if not isinstance(record.get(key),str) or not record[key].strip():raise ValueError('Required field: '+key)
    if not re.fullmatch(r'[1-9][0-9]*',record['dot_number']):raise ValueError('Valid USDOT required')
    if any(not re.fullmatch(r'\d{4}-\d{2}-\d{2}',record[key]) for key in ['policy_start','policy_end']):raise ValueError('ISO calendar dates required')
    start,end=dt.date.fromisoformat(record['policy_start']),dt.date.fromisoformat(record['policy_end'])
    if start>=end:raise ValueError('Policy period must have a positive duration')
    if record['status'] not in ['quoted','active','expired','cancelled','watch']:raise ValueError('Invalid policy status')
    if record['review_status'] not in ['unreviewed','in_review','reviewed']:raise ValueError('Invalid review status')
    for field in ['limit_minor','premium_minor','scheduled_units','insured_vmt']:
        value=record.get(field)
        if value is not None and (type(value)is not int or value<0):raise ValueError('Nonnegative integer or null required: '+field)
    if any(record.get(field) is not None for field in ['premium_minor','limit_minor']) and not re.fullmatch(r'[A-Z]{3}',record.get('currency') or ''):raise ValueError('Explicit ISO currency code required')
    for field in ['currency','class_code','territory','broker','notes']:
        if record.get(field) is not None and not isinstance(record[field],str):raise ValueError('Text or null required: '+field)
    if record.get('currency') is not None and not re.fullmatch(r'[A-Z]{3}',record['currency']):raise ValueError('Three uppercase currency letters required')
    for field,value in record.items():
        if isinstance(value,str) and len(value)>(8000 if field=='notes' else 250):raise ValueError('Portfolio text exceeds limit')
    return {field:record.get(field) for field in sorted(FIELDS)}

def import_records(path,records):
    rows=[validate(record) for record in records]
    keys=[(row['account_id'],row['policy_id']) for row in rows]
    if len(keys)!=len(set(keys)):raise ValueError('Duplicate account/policy in import')
    path=pathlib.Path(path).resolve()
    if any(part.lower() in ('public','dist') for part in path.parts):raise ValueError('Private portfolio cannot be stored in a served directory')
    path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(path)
    db.executescript('CREATE TABLE IF NOT EXISTS portfolio(account_id TEXT NOT NULL,policy_id TEXT NOT NULL,version TEXT NOT NULL,payload TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(account_id,policy_id));CREATE TABLE IF NOT EXISTS portfolio_history(change_id TEXT PRIMARY KEY,account_id TEXT NOT NULL,policy_id TEXT NOT NULL,previous_payload TEXT,current_payload TEXT NOT NULL,changed_at TEXT NOT NULL);')
    changes=0
    with db:
        for row in rows:
            key=(row['account_id'],row['policy_id']);payload=json.dumps(row,sort_keys=True);prior=db.execute('SELECT payload FROM portfolio WHERE account_id=? AND policy_id=?',key).fetchone()
            if prior and prior[0]==payload:continue
            at=now();db.execute('INSERT INTO portfolio_history VALUES (?,?,?,?,?,?)',(digest([key,prior[0] if prior else None,payload,at]),*key,prior[0] if prior else None,payload,at))
            db.execute('INSERT OR REPLACE INTO portfolio VALUES (?,?,?,?,?)',(*key,VERSION,payload,at));changes+=1
    db.close();return {'status':'STORED_LOCALLY','records':len(rows),'changes':changes,'schema':VERSION,'public_upload':False}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--db',required=True);parser.add_argument('--input',required=True);args=parser.parse_args()
    payload=json.loads(pathlib.Path(args.input).read_text(encoding='utf-8'))
    if payload.get('schema')!=VERSION or not isinstance(payload.get('records'),list):raise ValueError('Versioned portfolio envelope required')
    print(json.dumps(import_records(args.db,payload['records']),indent=2))
