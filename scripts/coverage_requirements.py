"""Private, versioned document checklists for an existing policy-linked review.

Checklist templates are analyst prompts, not legal requirements, insurance terms,
coverage decisions or a claims record. Only references and notes are stored; no
file is uploaded, fetched, or exposed through the public evidence service.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import urllib.parse

from insurance_reviews import ensure as ensure_reviews
from snapshot_store import digest, now

VERSION = 'COVERAGE_CHECKLIST_1'
TEMPLATES = {
    'auto-liability': [('loss-runs', 'Dated liability loss runs'), ('vehicle-schedule', 'Insured vehicle schedule'),
                       ('driver-schedule', 'Driver schedule'), ('insured-mileage', 'Insured mileage and operations')],
    'physical-damage': [('vehicle-values', 'Vehicle schedule and agreed values'), ('trailer-interchange', 'Trailer interchange agreements'),
                        ('garaging', 'Garaging locations'), ('maintenance', 'Maintenance and prior damage records')],
    'motor-truck-cargo': [('commodity-mix', 'Commodity mix and shipment values'), ('shipping-contracts', 'Shipper and carriage contracts'),
                         ('cargo-loss-runs', 'Dated cargo loss runs'), ('routes-security', 'Verified routes and security controls')],
    'workers-comp': [('payroll-classes', 'Payroll and classification records'), ('workforce', 'Workforce and contractor schedule'),
                     ('injury-loss-runs', 'Dated injury loss runs'), ('jurisdictions', 'Operating jurisdictions')],
    'environmental-hazmat': [('materials', 'Materials and quantities handled'), ('operations-routes', 'Documented operations and routes'),
                             ('incident-history', 'Verified incident and remediation history'), ('pollution-terms', 'Pollution terms and limits')],
    'business-interruption': [('dependencies', 'Documented facilities and logistics dependencies'), ('financial-exposure', 'Revenue and expense exposure'),
                              ('continuity-plan', 'Continuity and recovery plan'), ('interruption-history', 'Interruption history')],
    'broker-surety': [('bond-terms', 'Bond or trust terms'), ('authority-contracts', 'Authority and broker contracts'),
                      ('financials', 'Financial records'), ('surety-history', 'Dated surety claim history')],
    'cargo-theft': [('cargo-values', 'Target commodities and shipment values'), ('security-controls', 'Security and tracking controls'),
                    ('verified-lanes', 'Verified operating lanes and stops'), ('theft-loss-runs', 'Dated theft loss runs')],
}
STATES = {'not_requested', 'requested', 'received', 'reviewed', 'not_applicable'}
FIELDS = {'review_id', 'requirement_key', 'status', 'due_date', 'received_on', 'evidence_url', 'notes', 'expected_revision'}
DDL = '''
CREATE TABLE IF NOT EXISTS coverage_requirements (
 id TEXT PRIMARY KEY, review_id TEXT NOT NULL, requirement_key TEXT NOT NULL,
 template_version TEXT NOT NULL, status TEXT NOT NULL, due_date TEXT, received_on TEXT,
 evidence_url TEXT, notes TEXT NOT NULL, revision INTEGER NOT NULL, reviewer TEXT NOT NULL,
 updated_at TEXT NOT NULL, UNIQUE(review_id,requirement_key)
);
CREATE TABLE IF NOT EXISTS coverage_requirement_history (
 change_id INTEGER PRIMARY KEY AUTOINCREMENT, requirement_id TEXT NOT NULL,
 previous_json TEXT, current_json TEXT NOT NULL, reviewer TEXT NOT NULL, changed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS coverage_requirements_review ON coverage_requirements(review_id);
CREATE INDEX IF NOT EXISTS coverage_requirement_history_ref ON coverage_requirement_history(requirement_id,change_id);
'''


def ensure(db):
    ensure_reviews(db)
    db.executescript(DDL)


def _text(body, key, limit):
    value = body.get(key, '')
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{key} must be text up to {limit} characters')
    if any(ord(c) < 32 and c not in '\n\r\t' for c in value):
        raise ValueError(key + ' contains control characters')
    return value.strip()


def _date(body, key):
    value = _text(body, key, 10)
    if not value:
        return None
    try:
        if not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', value) or dt.date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise ValueError(key + ' must be a valid YYYY-MM-DD date') from None
    return value


def _review(db, review_id):
    if not isinstance(review_id, str) or not re.fullmatch('[a-f0-9]{64}', review_id):
        raise ValueError('Exact saved review ID required')
    row = db.execute('SELECT * FROM insurance_reviews WHERE id=?', (review_id,)).fetchone()
    if row is None or row['line'] not in TEMPLATES:
        raise ValueError('Saved insurance review not found')
    return row


def checklist(db, review_id):
    ensure(db)
    review = _review(db, review_id)
    saved = {r['requirement_key']: dict(r) for r in db.execute('SELECT * FROM coverage_requirements WHERE review_id=?', (review_id,))}
    items = []
    for key, title in TEMPLATES[review['line']]:
        item = saved.get(key, {'id': None, 'review_id': review_id, 'requirement_key': key, 'template_version': VERSION,
                               'status': 'not_requested', 'due_date': None, 'received_on': None, 'evidence_url': None,
                               'notes': '', 'revision': 0, 'reviewer': None, 'updated_at': None})
        items.append({**item, 'title': title})
    closed = sum(item['status'] in ('reviewed', 'not_applicable') for item in items)
    return {'template_version': VERSION, 'review_id': review_id, 'account_id': review['account_id'],
            'policy_id': review['policy_id'], 'dot_number': review['dot'], 'line': review['line'], 'items': items,
            'summary': {'total': len(items), 'reviewed_or_not_applicable': closed, 'outstanding': len(items) - closed},
            'scope': 'PRIVATE_ANALYST_DOCUMENT_CHECKLIST', 'coverage_determined': False,
            'limitation': 'Analyst prompts only. Receipt is not verification; missing loss runs do not mean no claims. No coverage or eligibility decision is made.'}


def save_requirement(db, body, portfolio_rows, reviewer):
    ensure(db)
    if not isinstance(body, dict) or set(body) - FIELDS:
        raise ValueError('Unknown requirement fields or invalid JSON object')
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('Authenticated reviewer required')
    review = _review(db, body.get('review_id'))
    if not any(p['account_id'] == review['account_id'] and p['policy_id'] == review['policy_id'] and p['dot_number'] == review['dot'] for p in portfolio_rows):
        raise ValueError('Review no longer matches a saved account/policy/USDOT')
    key = _text(body, 'requirement_key', 64)
    if key not in dict(TEMPLATES[review['line']]):
        raise ValueError('Requirement does not belong to this insurance line')
    status = _text(body, 'status', 32)
    if status not in STATES:
        raise ValueError('Unsupported document status')
    revision = body.get('expected_revision')
    if type(revision) is not int or revision < 0:
        raise ValueError('Nonnegative expected_revision required')
    notes = _text(body, 'notes', 4000)
    due, received = _date(body, 'due_date'), _date(body, 'received_on')
    url = _text(body, 'evidence_url', 2000) or None
    if url:
        parts = urllib.parse.urlsplit(url)
        if any(c.isspace() for c in url) or parts.scheme != 'https' or not parts.hostname or parts.username or parts.password:
            raise ValueError('Evidence reference must be HTTPS without credentials or whitespace')
    if status == 'requested' and not due:
        raise ValueError('Requested documents require a follow-up due date')
    if status in ('received', 'reviewed') and (not received or not url):
        raise ValueError('Received or reviewed documents require a received date and evidence reference')
    if received and dt.date.fromisoformat(received) > dt.datetime.now(dt.timezone.utc).date():
        raise ValueError('Received date cannot be in the future')
    if status in ('reviewed', 'not_applicable') and len(notes) < 10:
        raise ValueError('Reviewed or not applicable items require a rationale of at least 10 characters')
    identity = digest([VERSION, review['id'], key])
    value = {'id': identity, 'review_id': review['id'], 'requirement_key': key, 'template_version': VERSION,
             'status': status, 'due_date': due, 'received_on': received, 'evidence_url': url, 'notes': notes}
    # BEGIN IMMEDIATE protects both the compare-and-swap revision and append-only
    # history even for callers outside the single-owner service's policy lock.
    db.execute('BEGIN IMMEDIATE')
    try:
        prior = db.execute('SELECT * FROM coverage_requirements WHERE id=?', (identity,)).fetchone()
        actual_revision = prior['revision'] if prior else 0
        if revision != actual_revision:
            raise ValueError('Document changed since it was loaded; refresh before saving')
        if prior and all(prior[k] == v for k, v in value.items()):
            db.commit()
            return {'id': identity, 'changed': False, 'revision': actual_revision, 'status': 'SAVED_LOCALLY'}
        current = {**value, 'revision': actual_revision + 1, 'reviewer': reviewer, 'updated_at': now()}
        keys = tuple(current)
        db.execute('INSERT OR REPLACE INTO coverage_requirements (' + ','.join(keys) + ') VALUES (' + ','.join('?' for _ in keys) + ')', tuple(current.values()))
        db.execute('INSERT INTO coverage_requirement_history(requirement_id,previous_json,current_json,reviewer,changed_at) VALUES (?,?,?,?,?)',
                   (identity, json.dumps(dict(prior), sort_keys=True) if prior else None, json.dumps(current, sort_keys=True), reviewer, current['updated_at']))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'id': identity, 'changed': True, 'revision': current['revision'], 'status': 'SAVED_LOCALLY'}


def history(db, review_id, requirement_key):
    ensure(db)
    review = _review(db, review_id)
    if requirement_key not in dict(TEMPLATES[review['line']]):
        raise ValueError('Requirement does not belong to this insurance line')
    identity = digest([VERSION, review['id'], requirement_key])
    return [dict(r) for r in db.execute('SELECT * FROM coverage_requirement_history WHERE requirement_id=? ORDER BY change_id', (identity,))]
