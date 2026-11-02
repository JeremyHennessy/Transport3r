"""Private, audit-trailed insurance coverage reviews tied to saved account/policy/USDOT.

No insurance-coverage determination, loss prediction or risk score is computed.
This database is local-only; never serve it from GitHub Pages.
"""
import datetime as dt
import json
import urllib.parse
from snapshot_store import now, digest

LINES = {
    'auto-liability', 'physical-damage', 'motor-truck-cargo', 'workers-comp',
    'environmental-hazmat', 'business-interruption', 'broker-surety', 'cargo-theft',
}
STATES = {'needs_data', 'in_review', 'reviewed', 'escalated'}
DDL = """
CREATE TABLE IF NOT EXISTS insurance_reviews (
  id TEXT PRIMARY KEY, account_id TEXT NOT NULL, policy_id TEXT NOT NULL,
  dot TEXT NOT NULL, line TEXT NOT NULL, status TEXT NOT NULL,
  notes TEXT NOT NULL, evidence_url TEXT, source_cut TEXT, due_date TEXT,
  reviewer TEXT NOT NULL, updated_at TEXT NOT NULL,
  UNIQUE(account_id,policy_id,dot,line)
);
CREATE TABLE IF NOT EXISTS insurance_review_history (
  change_id INTEGER PRIMARY KEY AUTOINCREMENT, review_id TEXT NOT NULL,
  previous_json TEXT, current_json TEXT NOT NULL, reviewer TEXT NOT NULL,
  changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS insurance_reviews_due ON insurance_reviews(status,due_date);
CREATE INDEX IF NOT EXISTS insurance_history_ref ON insurance_review_history(review_id,change_id);
"""

def ensure(db):
    db.executescript(DDL)

def _bounded(body, field, limit, required=False):
    value = body.get(field, '')
    if not isinstance(value,str):
        raise ValueError(field + ' must be text')
    value = value.strip()
    if required and not value:
        raise ValueError(field + ' is required')
    if len(value)>limit:
        raise ValueError(field + ' exceeds maximum length')
    return value

def validate_review(body, portfolio_rows):
    if not isinstance(body,dict):
        raise ValueError('Review must be a JSON object')
    permitted={'account_id','policy_id','dot_number','line','status','notes','evidence_url','source_cut','due_date'}
    if set(body)-permitted:
        raise ValueError('Unknown review fields')
    account=_bounded(body,'account_id',250,True)
    policy=_bounded(body,'policy_id',250,True)
    dot=_bounded(body,'dot_number',10,True)
    if not dot.isascii() or not dot.isdigit() or dot[0]=='0':
        raise ValueError('Positive numeric USDOT required')
    if not any(x['account_id']==account and x['policy_id']==policy and x['dot_number']==dot for x in portfolio_rows):
        raise ValueError('Review must match an existing private account/policy/USDOT')
    line=_bounded(body,'line',64,True)
    if line not in LINES:
        raise ValueError('Unsupported insurance line')
    status=_bounded(body,'status',64,True)
    if status not in STATES:
        raise ValueError('Unsupported review status')
    notes=_bounded(body,'notes',8000,True)
    if len(notes)<10:
        raise ValueError('Review notes require at least 10 characters')
    evidence_url=_bounded(body,'evidence_url',2000) or None
    if evidence_url:
        p=urllib.parse.urlsplit(evidence_url)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:
            raise ValueError('Evidence URL must be HTTP(S) without embedded credentials')
    source_cut=_bounded(body,'source_cut',250) or None
    due_date=_bounded(body,'due_date',10) or None
    if due_date:
        if len(due_date)!=10 or due_date[4]!='-' or due_date[7]!='-':
            raise ValueError('Due date must be YYYY-MM-DD')
        try:
            if dt.date.fromisoformat(due_date).isoformat()!=due_date:
                raise ValueError('Due date must be YYYY-MM-DD')
        except ValueError:
            raise ValueError('Due date must be a valid calendar date')
    return {
      'account_id':account,'policy_id':policy,'dot':dot,'line':line,'status':status,
      'notes':notes,'evidence_url':evidence_url,'source_cut':source_cut,'due_date':due_date,
    }

def save_review(db, body, portfolio_rows, reviewer):
    ensure(db)
    if not isinstance(reviewer,str) or not reviewer.strip():
        raise ValueError('An authenticated reviewer is required')
    value=validate_review(body,portfolio_rows)
    review_id=digest(['INSURANCE_REVIEW_1',value['account_id'],value['policy_id'],value['dot'],value['line']])
    prior=db.execute('SELECT * FROM insurance_reviews WHERE id=?',(review_id,)).fetchone()
    unchanged=prior and all(prior[key]==value[key] for key in value)
    if unchanged:
        return {'id':review_id,'changed':False,'status':'SAVED_LOCALLY'}
    at=now()
    current={'id':review_id,**value,'reviewer':reviewer,'updated_at':at}
    with db:
        db.execute("""INSERT OR REPLACE INTO insurance_reviews
         (id,account_id,policy_id,dot,line,status,notes,evidence_url,source_cut,due_date,reviewer,updated_at)
         VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",tuple(current[k] for k in (
           'id','account_id','policy_id','dot','line','status','notes','evidence_url','source_cut','due_date','reviewer','updated_at')))
        db.execute('INSERT INTO insurance_review_history(review_id,previous_json,current_json,reviewer,changed_at) VALUES (?,?,?,?,?)',
          (review_id,json.dumps(dict(prior)) if prior else None,json.dumps(current,sort_keys=True),reviewer,at))
    return {'id':review_id,'changed':True,'status':'SAVED_LOCALLY'}

def list_reviews(db,limit=500):
    ensure(db)
    if not 1<=limit<=1000:
        raise ValueError('Limit out of range')
    return [dict(row) for row in db.execute('SELECT * FROM insurance_reviews ORDER BY updated_at DESC,id LIMIT ?', (limit,))]

def history(db,review_id):
    ensure(db)
    if not isinstance(review_id,str) or not 1<=len(review_id)<=128:
        raise ValueError('Review ID required')
    if not db.execute('SELECT 1 FROM insurance_reviews WHERE id=?',(review_id,)).fetchone():
        raise ValueError('Review not found')
    return [dict(row) for row in db.execute('SELECT * FROM insurance_review_history WHERE review_id=? ORDER BY change_id',(review_id,))]
