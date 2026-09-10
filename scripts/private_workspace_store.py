"""Single-owner local workspace. Private records never enter the Pages build."""
from contextlib import closing
import datetime as dt
import json
import pathlib
import re
import sqlite3
import urllib.parse
from snapshot_store import now, digest
from portfolio_store import import_records

DDL = '''
CREATE TABLE IF NOT EXISTS owner(name TEXT NOT NULL,salt TEXT NOT NULL,password_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS subscriptions(dot TEXT PRIMARY KEY,enabled INTEGER NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS inbox(alert_id TEXT PRIMARY KEY,dot TEXT NOT NULL,payload TEXT NOT NULL,delivered_at TEXT NOT NULL,read_at TEXT);
CREATE TABLE IF NOT EXISTS relationships(id TEXT PRIMARY KEY,dot_a TEXT NOT NULL,dot_b TEXT NOT NULL,kind TEXT NOT NULL,evidence_url TEXT NOT NULL,notes TEXT NOT NULL,status TEXT NOT NULL,reviewer TEXT,review_note TEXT,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS relationship_history(id INTEGER PRIMARY KEY AUTOINCREMENT,relationship_id TEXT NOT NULL,payload TEXT NOT NULL,changed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,started_at TEXT NOT NULL,finished_at TEXT,status TEXT NOT NULL,detail TEXT);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS screening_cases(id TEXT PRIMARY KEY,kind TEXT NOT NULL,dot TEXT NOT NULL,candidate_dot TEXT,status TEXT NOT NULL,notes TEXT NOT NULL,reviewer TEXT NOT NULL,evidence TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS screening_history(id INTEGER PRIMARY KEY AUTOINCREMENT,case_id TEXT NOT NULL,payload TEXT NOT NULL,changed_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS compliance_observations(id TEXT PRIMARY KEY,dot TEXT NOT NULL,observed_at TEXT NOT NULL,cut TEXT NOT NULL,payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS compliance_latest ON compliance_observations(dot,observed_at);
CREATE TABLE IF NOT EXISTS compliance_actions(id TEXT PRIMARY KEY,dot TEXT NOT NULL,check_id TEXT NOT NULL,observation_id TEXT NOT NULL,fingerprint TEXT NOT NULL,status TEXT NOT NULL,due_date TEXT,notes TEXT NOT NULL,reviewer TEXT NOT NULL,updated_at TEXT NOT NULL,title TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS compliance_action_history(id INTEGER PRIMARY KEY AUTOINCREMENT,action_id TEXT NOT NULL,payload TEXT NOT NULL,changed_at TEXT NOT NULL);
'''

def connect(path):
    path=pathlib.Path(path).resolve()
    if any(p.lower() in ('public','dist') for p in path.parts):
        raise ValueError('Private workspace cannot be stored under public or dist')
    path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row
    db.executescript(DDL)
    return db

def dot(value):
    if not isinstance(value,str) or not re.fullmatch(r'[1-9][0-9]{0,9}',value):
        raise ValueError('A positive USDOT number is required')
    return value

def save_portfolio(folder, records):
    if not isinstance(records,list) or len(records)>10000:raise ValueError('Import requires up to 10,000 records')
    return import_records(pathlib.Path(folder)/'portfolio.sqlite',records)

def portfolio(folder):
    path=pathlib.Path(folder)/'portfolio.sqlite'
    if not path.exists():return []
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)) as db:
        return [json.loads(r[0]) for r in db.execute('SELECT payload FROM portfolio ORDER BY account_id,policy_id')]

def relationship(db, body, reviewer):
    a,b=dot(body.get('dot_a')),dot(body.get('dot_b'))
    if a==b:raise ValueError('Relationship requires two distinct USDOT numbers')
    kind=body.get('kind')
    if kind not in ('parent_subsidiary','common_ownership','shared_registration_details'):raise ValueError('Unsupported relationship type')
    url=body.get('evidence_url','');parts=urllib.parse.urlsplit(url)
    if parts.scheme not in ('https','http') or not parts.hostname or parts.username or len(url)>2000:raise ValueError('Public evidence URL required')
    notes=body.get('notes','').strip()
    if not 10<=len(notes)<=8000:raise ValueError('Describe the evidence in 10 to 8,000 characters')
    if kind!='parent_subsidiary':a,b=sorted((a,b),key=int)
    identity=digest([a,b,kind,url,notes]);at=now()
    with db:
        if db.execute('SELECT 1 FROM relationships WHERE id=?',(identity,)).fetchone():return identity
        db.execute('INSERT INTO relationships VALUES (?,?,?,?,?,?,?,?,?,?)',(identity,a,b,kind,url,notes,'pending',None,None,at))
        db.execute('INSERT INTO relationship_history(relationship_id,payload,changed_at) VALUES (?,?,?)',(identity,json.dumps({'action':'proposed','actor':reviewer,'evidence_url':url,'notes':notes}),at))
    return identity

def review_relationship(db,body,reviewer):
    status=body.get('status');note=body.get('review_note','').strip()
    if status not in ('approved','rejected','revoked') or not 10<=len(note)<=8000:raise ValueError('Review decision and a substantive rationale required')
    with db:
        prior=db.execute('SELECT * FROM relationships WHERE id=?',(body.get('id'),)).fetchone()
        if not prior:raise ValueError('Relationship not found')
        at=now()
        db.execute('UPDATE relationships SET status=?,reviewer=?,review_note=?,updated_at=? WHERE id=?',(status,reviewer,note,at,prior['id']))
        db.execute('INSERT INTO relationship_history(relationship_id,payload,changed_at) VALUES (?,?,?)',(prior['id'],json.dumps({'previous':dict(prior),'status':status,'reviewer':reviewer,'rationale':note}),at))

def group_members(db,seed):
    members={dot(seed)}
    edges=db.execute("SELECT * FROM relationships WHERE status='approved' AND kind IN ('parent_subsidiary','common_ownership')").fetchall()
    changed=True
    while changed:
        changed=False
        for r in edges:
            if r['dot_a'] in members or r['dot_b'] in members:
                before=len(members);members.update((r['dot_a'],r['dot_b']));changed|=len(members)!=before
    return sorted(members,key=int)

def save_screening_case(db,body,reviewer,evidence):
    kind=body.get('kind');seed=dot(body.get('dot'))
    candidate=dot(body.get('candidate_dot')) if kind=='chameleon' else None
    if kind not in ('ghost','chameleon'):raise ValueError('Unsupported screening case')
    status=body.get('status');notes=body.get('notes','').strip()
    if status not in ('in_review','dismissed','escalated') or not 10<=len(notes)<=8000:
        raise ValueError('Select a review state and provide 10 to 8,000 characters of rationale')
    # One case per pair/rule, with successive source evidence and decisions in history.
    identity=digest([kind,seed,candidate]);at=now()
    with db:
        prior=db.execute('SELECT * FROM screening_cases WHERE id=?',(identity,)).fetchone()
        db.execute('INSERT OR REPLACE INTO screening_cases VALUES (?,?,?,?,?,?,?,?,?)',
                   (identity,kind,seed,candidate,status,notes,reviewer,json.dumps(evidence),at))
        db.execute('INSERT INTO screening_history(case_id,payload,changed_at) VALUES (?,?,?)',
                   (identity,json.dumps({'previous':dict(prior) if prior else None,'status':status,'notes':notes,'reviewer':reviewer,'evidence':evidence}),at))
    return identity

def deliver(db,alerts_path):
    """Atomic durable inbox delivery; a browser visit is not required."""
    path=pathlib.Path(alerts_path).resolve()
    if not path.exists():return 0
    subscriptions={r['dot']:r['created_at'] for r in db.execute('SELECT * FROM subscriptions WHERE enabled=1')}
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro',uri=True)) as source:
        source.row_factory=sqlite3.Row
        if not source.execute("SELECT 1 FROM sqlite_master WHERE name='alerts'").fetchone():return 0
        inserted=0
        with db:
            for row in source.execute('SELECT * FROM alerts ORDER BY detected_at,alert_id'):
                if row['dot'] not in subscriptions or row['detected_at']<subscriptions[row['dot']]:continue
                cursor=db.execute('INSERT OR IGNORE INTO inbox VALUES (?,?,?,?,NULL)',(row['alert_id'],row['dot'],json.dumps(dict(row)),now()))
                inserted+=cursor.rowcount
    return inserted
