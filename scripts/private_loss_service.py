"""Signed, authenticated single-owner loss intake; no public storage or network.

Owner/session values are supplied by the authenticated local server. A signed,
short-lived preview binds exact input bytes and the complete saved portfolio.
This does not provide multi-tenant authorization or production hosting approval.
"""
from contextlib import closing
import base64
import hashlib
import hmac
import json
import os
import pathlib
import sqlite3
import time

from private_loss_history import (LEDGER_SCHEMA, MAX_BYTES, preview, import_loss_history,
                                  private_path, summarize_batch)
from private_workspace_store import portfolio
from private_operations import private_write_lock

TOKEN_TTL = 600
TOKEN_FIELDS = {'v', 'preview', 'actor', 'session', 'expires'}
POLICY_IDENTITY = ('dot_number', 'currency', 'policy_start', 'policy_end')


def raw_source(body, commit=False):
    expected = {'source_base64', 'expected_preview', 'approval_token', 'approved'} if commit else {'source_base64'}
    if not isinstance(body, dict) or set(body) != expected:
        raise ValueError('UNKNOWN_OR_MISSING_LOSS_REQUEST_FIELDS')
    encoded=body['source_base64']
    if not isinstance(encoded,str) or len(encoded)>4*((MAX_BYTES+2)//3):
        raise ValueError('LOSS_SOURCE_BYTES_REQUIRED')
    try:
        raw=base64.b64decode(encoded,validate=True)
    except (ValueError,UnicodeError):
        raise ValueError('INVALID_SOURCE_BASE64') from None
    if not 0<len(raw)<=MAX_BYTES or base64.b64encode(raw).decode('ascii')!=encoded:
        raise ValueError('INPUT_SIZE_OR_ENCODING_LIMIT')
    if commit and body['approved'] is not True:
        raise ValueError('EXPLICIT_REVIEW_APPROVAL_REQUIRED')
    return raw


def _token(secret, fingerprint, actor, session, now):
    payload = {'v': 1, 'preview': fingerprint, 'actor': actor, 'session': session, 'expires': int(now) + TOKEN_TTL}
    encoded = base64.urlsafe_b64encode(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).decode('ascii').rstrip('=')
    signature = hmac.new(secret, encoded.encode(), hashlib.sha256).hexdigest()
    return encoded + '.' + signature


def _validate_token(token, secret, actor, session, fingerprint, now):
    if not isinstance(token, str) or len(token) > 2048:
        raise ValueError('LOSS_PREVIEW_REQUIRED')
    try:
        encoded, signature = token.split('.')
        expected = hmac.new(secret, encoded.encode('ascii'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        if (not isinstance(payload, dict) or set(payload) != TOKEN_FIELDS or payload['v'] != 1 or
            payload['actor'] != actor or payload['session'] != session or payload['preview'] != fingerprint or
            type(payload['expires']) is not int or not now < payload['expires'] <= now + TOKEN_TTL):
            raise ValueError()
    except (ValueError, UnicodeError, TypeError, KeyError):
        raise ValueError('PREVIEW_EXPIRED_CHANGED_OR_WRONG_SESSION_REVIEW_AGAIN') from None


def preview_request(folder, body, actor, session, secret, clock=time.time):
    folder = private_path(folder)
    plan = preview(raw_source(body), portfolio(folder))
    plan['approval_token'] = (_token(secret, plan['preview_sha256'], actor, session, clock())
                              if plan['status'] == 'READY_FOR_PRIVATE_IMPORT' else None)
    plan['approval_expires_in_seconds'] = TOKEN_TTL if plan['approval_token'] else 0
    plan['workflow_scope'] = 'AUTHENTICATED_SINGLE_OWNER_LOCAL_ONLY'
    plan['ledger_conflicts_checked_at_commit'] = True
    return plan


def _ledger(folder, create=False):
    folder = private_path(folder)
    path = private_path(folder / 'loss-history.sqlite')
    if create and not path.exists():
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
    if not path.exists():
        return None
    if not path.is_file() or (os.name == 'posix' and path.stat().st_mode & 0o077):
        raise ValueError('PRIVATE_DATABASE_PERMISSIONS_REQUIRED')
    if create:
        return sqlite3.connect(path, timeout=30)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=30)
    try:
        if db.execute('SELECT schema FROM loss_ledger_schema').fetchall() != [(LEDGER_SCHEMA,)]:
            raise ValueError('UNSUPPORTED_LEDGER_IDENTITY_SCHEMA')
    except Exception:
        db.close()
        raise ValueError('LOSS_LEDGER_REQUIRES_OPERATOR_REVIEW') from None
    return db


def import_request(folder, body, actor, session, secret, clock=time.time):
    raw = raw_source(body, commit=True)
    folder = private_path(folder)
    with private_write_lock(folder):
        policies = portfolio(folder)
        plan = preview(raw, policies)
        if plan['status'] != 'READY_FOR_PRIVATE_IMPORT':
            raise ValueError('REVIEW_REQUIRED_NO_ROWS_IMPORTED')
        if body['expected_preview'] != plan['preview_sha256']:
            raise ValueError('PREVIEW_CHANGED_REVIEW_AGAIN')
        _validate_token(body['approval_token'], secret, actor, session, plan['preview_sha256'], clock())
        with closing(_ledger(folder, create=True)) as db:
            result = import_loss_history(db, raw, policies, actor, body['expected_preview'])
            result['summary'] = summarize_batch(db, result['batch_id'])
    return result


def list_batches(folder, limit=50, offset=0):
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError('INVALID_HISTORY_PAGE')
    db = _ledger(folder)
    if db is None:
        return {'status': 'NOT_IMPORTED', 'batches': [], 'has_next': False, 'offset': offset,
                'population_complete': False, 'missing_history_is_zero': False}
    with closing(db):
        rows = db.execute('SELECT id, valuation_date, reviewer, created_at, receipt_json FROM loss_batches '
                          'ORDER BY created_at DESC,id LIMIT ? OFFSET ?', (limit + 1, offset)).fetchall()
    batches = []
    for identifier, valuation, reviewer, created, receipt in rows[:limit]:
        counts = json.loads(receipt)
        batches.append({'batch_id': identifier, 'valuation_date': valuation, 'reviewer': reviewer,
                        'created_at': created, **{key: counts[key] for key in ('input_rows', 'imported_rows', 'existing_observation_rows')}})
    return {'status': 'PRIVATE_HISTORY', 'batches': batches, 'has_next': len(rows) > limit, 'offset': offset,
            'population_complete': False, 'missing_history_is_zero': False}


def batch_summary(folder, batch_id):
    if not isinstance(batch_id, str) or len(batch_id) != 64 or any(c not in '0123456789abcdef' for c in batch_id):
        raise ValueError('INVALID_BATCH_ID')
    db = _ledger(folder)
    if db is None:
        raise ValueError('BATCH_NOT_FOUND')
    with closing(db):
        return summarize_batch(db, batch_id, read_only=True)


def guard_policy_changes(folder, records):
    """Called under the shared portfolio/loss write lock, including CLI writes."""
    if not (pathlib.Path(folder) / 'loss-history.sqlite').exists():
        return
    with closing(_ledger(folder)) as db:
        linked = set()
        for (raw,) in db.execute('SELECT record_json FROM loss_observations'):
            row = json.loads(raw)
            linked.add((row['account_id'], row['policy_id']))
    current = {(row['account_id'], row['policy_id']): row for row in portfolio(folder)}
    for row in records:
        key = (row['account_id'], row['policy_id'])
        if key in linked and (key not in current or any(row.get(field) != current[key].get(field) for field in POLICY_IDENTITY)):
            raise ValueError('SAVED_CLAIMS_REQUIRE_POLICY_IDENTITY_REVIEW')
