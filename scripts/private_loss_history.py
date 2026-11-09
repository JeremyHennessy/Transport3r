"""Local-only, explicitly permitted loss-history intake; never a public data feed.

Preview is the default. Commit requires the exact preview fingerprint and rejects
any unmatched/invalid/conflicting row. No claimants, injury narratives or scores.
This CLI is an owner-operated foundation, not authenticated multi-tenant hosting.
"""
from __future__ import annotations
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import sqlite3
from insurance_reviews import LINES
from private_workspace_store import portfolio
from snapshot_store import now, digest
from private_operations import private_write_lock

SCHEMA = 'PRIVATE_LOSS_HISTORY_1'
LEDGER_SCHEMA = 'SOURCE_CLAIM_IDENTITY_1'
MAX_BYTES = 2_000_000
MAX_ROWS = 5000
MAX_MONEY = 9_007_199_254_740_991
ROOT = pathlib.Path(__file__).resolve().parents[1]
ENVELOPE = {'schema','source_id','document_reference','valuation_date','permission_confirmed','amount_basis','claims'}
FIELDS = {'claim_id','account_id','policy_id','dot_number','coverage_line','loss_date',
          'reported_date','status','currency','paid_minor','outstanding_minor'}
MONEY = ('paid_minor','outstanding_minor')
DDL = '''
CREATE TABLE IF NOT EXISTS loss_ledger_schema(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS loss_batches(
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL, valuation_date TEXT NOT NULL,
 source_sha256 TEXT NOT NULL, portfolio_sha256 TEXT NOT NULL,
 metadata_json TEXT NOT NULL, receipt_json TEXT NOT NULL, reviewer TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS loss_observations(
 claim_key TEXT NOT NULL, valuation_date TEXT NOT NULL, record_json TEXT NOT NULL,
 first_batch_id TEXT NOT NULL, PRIMARY KEY(claim_key,valuation_date));
CREATE TABLE IF NOT EXISTS loss_batch_records(
 batch_id TEXT NOT NULL, claim_key TEXT NOT NULL, valuation_date TEXT NOT NULL,
 PRIMARY KEY(batch_id,claim_key,valuation_date));
CREATE TABLE IF NOT EXISTS loss_import_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT, batch_id TEXT NOT NULL, reviewer TEXT NOT NULL,
 action TEXT NOT NULL, created_at TEXT NOT NULL);
'''


def _text(value, field, limit=128):
    # Preserve exact identifiers, including meaningful legacy outer whitespace.
    if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError('INVALID_'+field.upper())
    return value


def _date(value, field):
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}',value):
        raise ValueError('INVALID_'+field.upper())
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValueError('INVALID_'+field.upper()) from None


def _pairs(items):
    result={}
    for key,value in items:
        if key in result:raise ValueError('DUPLICATE_JSON_FIELD')
        result[key]=value
    return result


def _prepare(raw, policies):
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:raise ValueError('INPUT_SIZE_LIMIT')
    try:
        data=json.loads(raw.decode('utf-8-sig'),object_pairs_hook=_pairs,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
    except (UnicodeError,json.JSONDecodeError):
        raise ValueError('INVALID_JSON') from None
    if not isinstance(data,dict) or set(data)!=ENVELOPE or data.get('schema')!=SCHEMA:
        raise ValueError('INVALID_ENVELOPE')
    if data['permission_confirmed'] is not True:raise ValueError('EXPLICIT_PERMISSION_REQUIRED')
    if data['amount_basis']!='GROSS_INDEMNITY_EXCLUDING_EXPENSES_AND_RECOVERIES':raise ValueError('AMOUNT_BASIS_REQUIRES_NORMALIZATION')
    source=_text(data['source_id'],'source_id')
    _text(data['document_reference'],'document_reference',1000)
    valuation=_date(data['valuation_date'],'valuation_date')
    if valuation>dt.datetime.now(dt.timezone.utc).date():raise ValueError('FUTURE_VALUATION')
    records=data['claims']
    if not isinstance(records,list) or not 1<=len(records)<=MAX_ROWS:raise ValueError('NONEMPTY_BOUNDED_CLAIMS_REQUIRED')
    if not isinstance(policies,list):raise ValueError('SAVED_PORTFOLIO_REQUIRED')
    lookup={}
    for p in policies:
        if not isinstance(p,dict):raise ValueError('INVALID_SAVED_PORTFOLIO')
        key=(_text(p.get('account_id'),'account_id'),_text(p.get('policy_id'),'policy_id'))
        lookup.setdefault(key,[]).append(p)
    # Bind the preview to the complete saved portfolio used to check identity.
    portfolio_hash=digest(sorted((json.dumps(p,sort_keys=True,allow_nan=False) for p in policies)))
    source_hash=hashlib.sha256(raw).hexdigest()
    fingerprint=digest([SCHEMA,LEDGER_SCHEMA,source_hash,portfolio_hash])
    rows={};duplicates=0;issues=[]
    for number,row in enumerate(records,1):
        try:
            if not isinstance(row,dict) or set(row)!=FIELDS:raise ValueError('UNKNOWN_OR_MISSING_CLAIM_FIELDS')
            for key in ('claim_id','account_id','policy_id'):_text(row[key],key)
            if not isinstance(row['dot_number'],str) or not re.fullmatch(r'[1-9][0-9]{0,9}',row['dot_number']):raise ValueError('INVALID_USDOT')
            if row['coverage_line'] not in LINES:raise ValueError('UNKNOWN_COVERAGE_LINE')
            if row['status'] not in ('open','closed','reopened'):raise ValueError('UNKNOWN_CLAIM_STATUS')
            loss=_date(row['loss_date'],'loss_date');reported=_date(row['reported_date'],'reported_date')
            if not loss<=reported<=valuation:raise ValueError('LOSS_REPORT_VALUATION_ORDER')
            if not isinstance(row['currency'],str) or not re.fullmatch('[A-Z]{3}',row['currency']):raise ValueError('INVALID_CURRENCY')
            for key in MONEY:
                v=row[key]
                if v is not None and (type(v) is not int or not 0<=v<=MAX_MONEY):raise ValueError('INVALID_'+key.upper())
            if row['status']=='closed' and row['outstanding_minor'] not in (None,0):raise ValueError('CLOSED_WITH_OUTSTANDING_REVIEW')
            matches=lookup.get((row['account_id'],row['policy_id']),[])
            if not matches:raise ValueError('UNMATCHED_POLICY')
            if len(matches)!=1:raise ValueError('AMBIGUOUS_SAVED_POLICY')
            policy=matches[0]
            if policy.get('dot_number')!=row['dot_number']:raise ValueError('USDOT_IDENTITY_MISMATCH')
            if policy.get('currency')!=row['currency']:raise ValueError('POLICY_CURRENCY_UNVERIFIED_OR_DIFFERENT')
            start=_date(policy.get('policy_start'),'policy_start');end=_date(policy.get('policy_end'),'policy_end')
            if not start<=loss<end:raise ValueError('LOSS_OUTSIDE_POLICY_PERIOD_REVIEW')
            # This is an identity/date screen, not a coverage determination.
            # Source and claim number are stable; policy/coverage are validated attributes.
            # A reassignment or multi-line allocation must be reviewed, not become a new claim.
            identity=digest([source,row['claim_id']])
            if identity in rows:
                if rows[identity]!=row:raise ValueError('CONFLICTING_ROWS_IN_BATCH')
                duplicates+=1
            else:rows[identity]=dict(row)
        except (ValueError,TypeError) as error:
            reason=str(error) if isinstance(error,ValueError) else 'INVALID_CLAIM_FIELD_TYPE'
            issues.append({'row':number,'reason':reason})
    status='READY_FOR_PRIVATE_IMPORT' if not issues else 'REVIEW_REQUIRED'
    receipt={'schema':SCHEMA,'ledger_schema':LEDGER_SCHEMA,'status':status,'preview_sha256':fingerprint,'source_sha256':source_hash,
             'portfolio_sha256':portfolio_hash,'valuation_date':data['valuation_date'],
             'input_rows':len(records),'unique_candidate_rows':len(rows),'exact_duplicate_rows':duplicates,
             'review_required_rows':len(issues),'issues':issues,'imported_rows':0,
             'public_upload':False,'coverage_determined':False,'population_complete':False,
             'limitation':'Supplied claim observations only. Missing loss history is not zero claims. No coverage decision or actuarial score.'}
    assert receipt['input_rows']==len(rows)+duplicates+len(issues), 'Count conservation failure'
    return receipt,rows,{k:v for k,v in data.items() if k!='claims'}


def preview(raw, policies):
    """Return counts, fingerprints and row-number reasons, never raw private claims."""
    return _prepare(raw,policies)[0]


def _ensure(db):
    if db.in_transaction:raise ValueError('ACTIVE_TRANSACTION_NOT_ALLOWED')
    paths=[r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main']
    if paths and paths[0]:
        path=private_path(paths[0])
        if os.name=='posix' and path.stat().st_mode & 0o077:raise ValueError('PRIVATE_DATABASE_PERMISSIONS_REQUIRED')
    db.executescript(DDL)
    db.execute('BEGIN IMMEDIATE')
    try:
        versions=db.execute('SELECT schema FROM loss_ledger_schema').fetchall()
        if not versions:
            if any(db.execute('SELECT 1 FROM '+name+' LIMIT 1').fetchone() for name in
                   ('loss_observations','loss_batches','loss_batch_records','loss_import_history')):
                raise ValueError('LEGACY_LEDGER_IDENTITY_REVIEW_REQUIRED')
            db.execute('INSERT INTO loss_ledger_schema VALUES (1,?)',(LEDGER_SCHEMA,))
        elif len(versions)!=1 or versions[0][0]!=LEDGER_SCHEMA:
            raise ValueError('UNSUPPORTED_LEDGER_IDENTITY_SCHEMA')
        db.commit()
    except Exception:
        db.rollback();raise


def private_path(value):
    raw=pathlib.Path(value).expanduser()
    if raw.is_symlink():raise ValueError('PRIVATE_PATH_MUST_NOT_BE_SYMLINK')
    path=raw.resolve()
    if path.is_relative_to(ROOT) or any(part.lower() in ('public','dist') for part in path.parts):
        raise ValueError('PRIVATE_STORAGE_OUTSIDE_REPOSITORY_REQUIRED')
    return path


def import_loss_history(db, raw, policies, reviewer, expected_preview):
    """Atomically append immutable valuation observations after explicit preview approval."""
    _text(reviewer,'reviewer',200)
    receipt,rows,metadata=_prepare(raw,policies)
    if receipt['status']!='READY_FOR_PRIVATE_IMPORT':raise ValueError('REVIEW_REQUIRED_NO_ROWS_IMPORTED')
    if expected_preview!=receipt['preview_sha256']:raise ValueError('PREVIEW_CHANGED_REVIEW_AGAIN')
    _ensure(db)
    batch=receipt['preview_sha256'];valuation=receipt['valuation_date']
    db.execute('BEGIN IMMEDIATE')
    try:
        prior=db.execute('SELECT receipt_json FROM loss_batches WHERE id=?',(batch,)).fetchone()
        if prior:
            result=json.loads(prior[0]);result.update(changed=False,imported_rows=0,existing_observation_rows=len(rows));db.commit();return result
        inserted=0;existing=0
        for identity,row in rows.items():
            payload=json.dumps(row,sort_keys=True,allow_nan=False)
            found=db.execute('SELECT record_json FROM loss_observations WHERE claim_key=? AND valuation_date=?',(identity,valuation)).fetchone()
            if found:
                if found[0]!=payload:raise ValueError('CONFLICTING_SAVED_VALUATION_NO_ROWS_IMPORTED')
                existing+=1
            else:
                # A claim's identity, loss date and currency cannot silently change over valuations.
                old=db.execute('SELECT record_json FROM loss_observations WHERE claim_key=? LIMIT 1',(identity,)).fetchone()
                if old:
                    old=json.loads(old[0])
                    if any(old[k]!=row[k] for k in ('account_id','policy_id','dot_number','coverage_line','loss_date','reported_date','currency')):
                        raise ValueError('CLAIM_IDENTITY_CHANGED_REVIEW_REQUIRED')
                db.execute('INSERT INTO loss_observations VALUES (?,?,?,?)',(identity,valuation,payload,batch));inserted+=1
            db.execute('INSERT INTO loss_batch_records VALUES (?,?,?)',(batch,identity,valuation))
        result={**receipt,'status':'IMPORTED_PRIVATELY','batch_id':batch,'changed':True,
                'imported_rows':inserted,'existing_observation_rows':existing}
        at=now()
        db.execute('INSERT INTO loss_batches VALUES (?,?,?,?,?,?,?,?,?)',
                   (batch,metadata['source_id'],valuation,receipt['source_sha256'],receipt['portfolio_sha256'],
                    json.dumps(metadata,sort_keys=True),json.dumps(result,sort_keys=True),reviewer,at))
        db.execute('INSERT INTO loss_import_history(batch_id,reviewer,action,created_at) VALUES (?,?,?,?)',(batch,reviewer,'IMPORTED',at))
        db.commit();return result
    except Exception:
        db.rollback();raise


def summarize_batch(db,batch_id,read_only=False):
    """Summarize one explicit valuation batch; never sum repeated historical snapshots."""
    if read_only:
        if db.execute('SELECT schema FROM loss_ledger_schema').fetchall()!=[(LEDGER_SCHEMA,)]:
            raise ValueError('UNSUPPORTED_LEDGER_IDENTITY_SCHEMA')
    else:
        _ensure(db)
    batch=db.execute('SELECT valuation_date,source_id,source_sha256,portfolio_sha256,reviewer,created_at FROM loss_batches WHERE id=?',(batch_id,)).fetchone()
    if not batch:raise ValueError('BATCH_NOT_FOUND')
    rows=db.execute('SELECT o.record_json FROM loss_batch_records b JOIN loss_observations o USING(claim_key,valuation_date) WHERE b.batch_id=?',(batch_id,)).fetchall()
    grouped={}
    for item in rows:
        r=json.loads(item[0]);key=(r['currency'],r['coverage_line'])
        g=grouped.setdefault(key,{'currency':key[0],'coverage_line':key[1],'observations':0,
            **{k:{'known_sum':0,'unknown_count':0} for k in MONEY}})
        g['observations']+=1
        for k in MONEY:
            if r[k] is None:g[k]['unknown_count']+=1
            else:g[k]['known_sum']+=r[k]
    # Exact decimal strings avoid silent JavaScript rounding on large aggregates.
    for group in grouped.values():
        for field in MONEY:group[field]['known_sum']=str(group[field]['known_sum'])
    return {'schema':'PRIVATE_LOSS_VALUATION_SUMMARY_1','batch_id':batch_id,
            'scope':'SUPPLIED_ROWS_AT_ONE_VALUATION','valuation_date':batch[0],
            'provenance':{'source_id':batch[1],'source_sha256':batch[2],'portfolio_sha256':batch[3],
                          'reviewer':batch[4],'imported_at':batch[5],
                          'verification_scope':'NORMALIZED_FILE_NOT_UPSTREAM_INSURER_DOCUMENT'},
            'observations':len(rows),'groups':[grouped[k] for k in sorted(grouped)],
            'population_complete':False,'actuarial_score':None,'coverage_determined':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',required=True,help='Existing private workspace outside the repository')
    parser.add_argument('--input',required=True,help='Private normalized JSON loss-history envelope')
    parser.add_argument('--commit',action='store_true',help='Explicitly commit the exact approved preview')
    parser.add_argument('--expected-preview',help='Preview SHA required when committing')
    parser.add_argument('--reviewer',help='Local operator for append-only import history')
    args=parser.parse_args()
    try:
        folder=private_path(args.workspace);source=private_path(args.input)
        with source.open('rb') as handle:raw=handle.read(MAX_BYTES+1)
        if not args.commit:
            result=preview(raw,portfolio(folder))
        else:
            if not args.expected_preview or not args.reviewer:raise ValueError('PREVIEW_AND_REVIEWER_REQUIRED')
            with private_write_lock(folder):
                policies=portfolio(folder)
                path=private_path(folder/'loss-history.sqlite')
                if not path.exists():
                    fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
                with closing(sqlite3.connect(path,timeout=30)) as db:
                    result=import_loss_history(db,raw,policies,args.reviewer,args.expected_preview)
        print(json.dumps(result,indent=2,allow_nan=False))
        return 0 if result['status'] in ('READY_FOR_PRIVATE_IMPORT','IMPORTED_PRIVATELY') else 1
    except (ValueError,OSError,sqlite3.Error) as error:
        # Do not echo source records or private paths to shell/CI logs.
        reason=str(error) if isinstance(error,ValueError) else type(error).__name__
        print(json.dumps({'status':'REJECTED','reason':reason,'imported_rows':0,'public_upload':False}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
